"""Generate a card, preview it, then save it to Anki.

Generating doesn't touch Anki: the result is kept as a draft (note fields
plus media, in memory, newest ``_DRAFT_LIMIT``) that the preview renders and
``save`` writes. A draft outlives a failed save, so a blocked AnkiWeb sync or
a closed Anki Desktop never costs a regeneration.

Words, phrases, sentences and STEM cards share this flow; words have
pictures, STEM cards diagrams, the rest audio. A draft's fields can be edited
before saving (``EDIT_FORM`` per kind says which); an edited example sentence
gets new audio, nothing else is remade. A STEM draft can also be previewed
with unapplied edits (live editing) and rewritten by the model from an
instruction, or have just its broken formulas fixed. Edits and rewrites can
be undone.
"""

import asyncio
import json
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Response
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from ankinote.card_render import media_path, render_card
from ankinote.collections.common import (
    AudioUnavailable,
    MediaGap,
    strip_phonetic_annotations,
)
from ankinote.collections.editing import EditError, Form, describe, revise
from ankinote.collections.phrase import models as phrase_models
from ankinote.collections.phrase import templates as phrase_templates
from ankinote.collections.phrase.collection import PhraseCollection
from ankinote.collections.sentence import models as sentence_models
from ankinote.collections.sentence import templates as sentence_templates
from ankinote.collections.sentence.collection import SentenceCollection
from ankinote.collections.stem import templates as stem_templates
from ankinote.collections.stem.collection import StemCollection
from ankinote.collections.stem.generator import LatexProblem
from ankinote.collections.stem.models import EDIT_FORMS as STEM_FORMS
from ankinote.collections.stem.models import CardType
from ankinote.collections.word import models as word_models
from ankinote.collections.word import templates as word_templates
from ankinote.collections.word.collection import WordCollection
from ankinote.consts import Language
from ankinote.services import model_check
from ankinote.services.ai import (
    ImageGenerationService,
    LiteLLMTextService,
    TextGenerationService,
    TextMessage,
)
from ankinote.services.anki import AnkiCollectionClient
from ankinote.services.anki_factory import create_anki_client, get_shared_runtime
from ankinote.services.provider_factory import (
    build_image_service,
    build_text_service,
    optional_speech_service,
)
from ankinote.services.tts import SpeechService
from ankinote.settings import active_profile, apply_env, load_settings
from ankinote.web import anki_api

# A first card with an image takes 20–60 s; past this something is stuck.
GENERATE_TIMEOUT_SECONDS = 180
# STEM thinks first (classify, then write), and may draw a diagram.
STEM_TIMEOUT_SECONDS = 300
_DRAFT_LIMIT = 50
_UNDO_LIMIT = 20
_MEDIA_TYPES = {".mp3": "audio/mpeg", ".png": "image/png"}
# Words, phrases and sentences; a STEM question or problem may be longer.
_TEXT_LIMIT = 300
_STEM_TEXT_LIMIT = 1000

Kind = Literal["word", "phrase", "sentence", "stem"]


class CardCollection(Protocol):
    """What the word, phrase, sentence and STEM collections have in common."""

    deck_name: str

    @property
    def notetype_name(self) -> str: ...

    def card_templates(self) -> list[dict[str, str]]: ...

    async def generate_cards(self, text: str, /) -> Sequence[Any]: ...

    async def revise_card(self, card: Any, model: Any, /) -> Any: ...

    def note_fields(self, card: Any, /) -> dict[str, str]: ...

    def media_files(self, card: Any, /) -> dict[str, bytes]: ...

    async def save_card(self, card: Any, /) -> int: ...

    async def ensure_in_anki(self) -> None: ...


_STYLES: dict[Kind, Callable[[], str]] = {
    "word": word_templates.load_card_style,
    "phrase": phrase_templates.load_card_style,
    "sentence": sentence_templates.load_card_style,
    "stem": stem_templates.load_card_style,
}

_FORMS: dict[Kind, Form] = {
    "word": word_models.EDIT_FORM,
    "phrase": phrase_models.EDIT_FORM,
    "sentence": sentence_models.EDIT_FORM,
}


def _form(kind: Kind, card: Any) -> Form:
    return STEM_FORMS[card.model.card_type] if kind == "stem" else _FORMS[kind]


def _build(
    kind: Kind,
    client: AnkiCollectionClient | None,
    *,
    native: Language,
    target: Language,
    text_model: str = "",
    text_service: TextGenerationService | None = None,
    image_service: ImageGenerationService | None = None,
    tts: SpeechService | None = None,
    card_type: CardType | None = None,
) -> CardCollection:
    """The collection for ``kind``; without services it can only save.

    A STEM collection for a draft has the draft's type; ``None`` (generating
    only) lets the model choose it.
    """
    text_service = text_service or LiteLLMTextService()
    if kind == "stem":
        return StemCollection(
            client,
            card_type=card_type,
            text_model=text_model,
            text_service=text_service,
            image_service=image_service,
        )
    if kind == "word":
        return WordCollection(
            client,
            native_language=native,
            target_language=target,
            text_model=text_model,
            text_service=text_service,
            image_service=image_service,
            tts_service=tts,
        )
    cls = PhraseCollection if kind == "phrase" else SentenceCollection
    return cls(
        client,
        native_language=native,
        target_language=target,
        text_model=text_model,
        text_service=text_service,
        tts_service=tts,
    )


def _headline(kind: Kind, card: Any) -> tuple[str, str]:
    """What the note is about, and which variant (a word's part of speech)."""
    model = card.model
    if kind == "word":
        return model.lemma, model.part_of_speech
    if kind == "stem":
        return model.front, str(model.card_type)
    text = model.phrase if kind == "phrase" else model.target_sentence
    return strip_phonetic_annotations(text), ""


@dataclass(frozen=True)
class _Version:
    """A draft's card as it was before an edit or rewrite, to undo to."""

    card: Any
    fields: dict[str, str]
    files: dict[str, bytes]


@dataclass
class Draft:
    id: str
    kind: Kind
    native: Language
    target: Language
    card: Any
    fields: dict[str, str]
    files: dict[str, bytes]
    # What it was generated from, and whether it may have media it can make
    # (a STEM rewrite draws a new diagram only if pictures were on).
    source: str = ""
    image: bool = False
    note_id: int | None = None
    # The card last written to Anki: saving again updates that note.
    saved: Any = None
    # Bumped by each edit: a re-made clip keeps its name, so its URL changes.
    revision: int = 0
    history: list[_Version] = field(default_factory=list)

    def replace(self, collection: CardCollection, card: Any) -> None:
        """Make ``card`` the draft's card, keeping the old one to undo to."""
        self.history.append(_Version(self.card, self.fields, self.files))
        del self.history[:-_UNDO_LIMIT]
        self.card = card
        self.fields = collection.note_fields(card)
        self.files = collection.media_files(card)
        self.revision += 1


_drafts: OrderedDict[str, Draft] = OrderedDict()


class GenerateIn(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=_STEM_TEXT_LIMIT,
        description=f"Up to {_TEXT_LIMIT} characters except for STEM.",
    )
    image: bool | None = Field(
        default=None,
        description="Words and STEM. Omit to follow the saved default.",
    )
    audio: bool = Field(
        default=True, description="False leaves audio out, without a gap."
    )
    card_type: CardType | None = Field(
        default=None, description="STEM only. Omit to let the model choose."
    )


def _fail(status: int, code: str, detail: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "detail": detail})


def _generation_error(exc: Exception, model: str) -> HTTPException:
    if isinstance(exc, ValidationError) or isinstance(
        exc.__cause__, json.JSONDecodeError
    ):
        return _fail(502, "bad_output", str(exc)[:300])
    check = model_check.classify(exc, model)
    return _fail(502, check.code or "error", check.detail)


def _media_prefix(draft_id: str) -> str:
    return f"/api/cards/drafts/{draft_id}/media"


def _render(
    draft: Draft, collection: CardCollection, card: Any, fields: dict[str, str]
) -> list[dict[str, str]]:
    """Every card of ``card``'s note, both sides, as Anki would show them."""
    prefix = _media_prefix(draft.id)

    def url(name: str) -> str:
        return f"{media_path(prefix, name)}?v={draft.revision}"

    if isinstance(collection, StemCollection):
        # The STEM back shows the note's tags.
        fields = {**fields, "Tags": " ".join(collection.note_tags(card))}
    cards = []
    for template in collection.card_templates():
        front = render_card(template["Front"], fields, media_url=url)
        back = render_card(
            template["Back"], fields, front_side=front, answer=True, media_url=url
        )
        cards.append({"name": template["Name"], "front": front, "back": back})
    return cards


def _draft_out(draft: Draft, collection: CardCollection) -> dict:
    cards = _render(draft, collection, draft.card, draft.fields)
    headword, variant = _headline(draft.kind, draft.card)
    return {
        "id": draft.id,
        "kind": draft.kind,
        "headword": headword,
        "variant": variant,
        "note_type": collection.notetype_name,
        "deck": collection.deck_name,
        "gaps": [
            {"kind": g.kind, "reason": g.reason, "detail": g.detail}
            for g in draft.card.media.gaps
        ],
        "css": _STYLES[draft.kind](),
        "cards": cards,
        "form": describe(draft.card.model, _form(draft.kind, draft.card)),
        "note_id": draft.note_id,
        "can_undo": bool(draft.history),
    }


def _keep(draft: Draft) -> None:
    _drafts[draft.id] = draft
    while len(_drafts) > _DRAFT_LIMIT:
        _drafts.popitem(last=False)


router = APIRouter(prefix="/api/cards")


@router.post("/{kind}")
async def generate(kind: Kind, body: GenerateIn) -> dict:
    """Generate the notes for ``text`` (a word: one per part of speech), unsaved."""
    settings = load_settings()
    apply_env(settings)
    native = Language(settings.defaults.native_language)
    target = Language(settings.defaults.target_language)
    source = body.text.strip()
    if kind != "stem" and len(source) > _TEXT_LIMIT:
        raise _fail(422, "too_long", str(_TEXT_LIMIT))
    text = active_profile(settings, "text")
    if text is None:
        raise _fail(409, "no_text_model")
    want_image = kind in ("word", "stem") and (
        settings.defaults.generate_image if body.image is None else body.image
    )
    image = active_profile(settings, "image") if want_image else None
    # A STEM card says so itself, and only if it wanted a diagram.
    gaps = (
        [MediaGap("image", "not_set_up")]
        if kind == "word" and want_image and image is None
        else []
    )
    collection = _build(
        kind,
        None,
        native=native,
        target=target,
        text_model=text.model,
        text_service=build_text_service(text),
        image_service=build_image_service(image, image_size=settings.image_size)
        if image
        else None,
        tts=optional_speech_service(settings, target)
        if body.audio and kind != "stem"
        else None,
        card_type=body.card_type if kind == "stem" else None,
    )
    try:
        async with asyncio.timeout(_timeout(kind)):
            cards = await collection.generate_cards(source)
    except TimeoutError as exc:
        raise _fail(504, "timeout") from exc
    except Exception as exc:
        logger.warning("{} generation failed: {}", kind.capitalize(), exc)
        raise _generation_error(exc, text.model) from exc
    if not cards:
        raise _fail(502, "bad_output", "no notes")

    notes = []
    for card in cards:
        # Turned off on purpose: nothing to report.
        off = {"audio"} if not body.audio else set()
        if not want_image:
            off.add("image")
        card.media.gaps[:] = [g for g in card.media.gaps if g.kind not in off]
        card.media.gaps[:0] = gaps
        draft = Draft(
            id=uuid.uuid4().hex,
            kind=kind,
            native=native,
            target=target,
            card=card,
            fields=collection.note_fields(card),
            files=collection.media_files(card),
            source=source,
            image=want_image,
        )
        _keep(draft)
        notes.append(_draft_out(draft, _for_draft(draft)))
    return {"notes": notes}


class _FixedAnswer:
    """A text model that always gives the same answer: sample notes."""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def generate_text(
        self,
        *,
        model: str,
        messages: Sequence[TextMessage],
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        return self._answer


async def sample_note(
    kind: Kind, source: str, answer: Any, card_type: CardType | None = None
) -> dict:
    """A note made from a fixed model ``answer``, shaped like a draft but not kept.

    It goes through the same parsing and field formatting as a generated note,
    with no audio or pictures, and never touches Anki.
    """
    collection = _build(
        kind,
        None,
        native=Language.CHINESE_S,
        target=Language.ENGLISH,
        text_service=_FixedAnswer(json.dumps(answer)),
        card_type=card_type,
    )
    card = (await collection.generate_cards(source))[0]
    draft = Draft(
        id=f"sample-{kind}-{card_type or ''}".rstrip("-"),
        kind=kind,
        native=Language.CHINESE_S,
        target=Language.ENGLISH,
        card=card,
        fields=collection.note_fields(card),
        files={},
    )
    return _draft_out(draft, collection)


def _timeout(kind: Kind) -> int:
    return STEM_TIMEOUT_SECONDS if kind == "stem" else GENERATE_TIMEOUT_SECONDS


def _card_type(draft: Draft) -> CardType | None:
    return draft.card.model.card_type if draft.kind == "stem" else None


def _for_draft(draft: Draft, client: AnkiCollectionClient | None = None, **services):
    """The collection that renders, edits and saves ``draft``."""
    return _build(
        draft.kind,
        client,
        native=draft.native,
        target=draft.target,
        card_type=_card_type(draft),
        **services,
    )


def _draft(draft_id: str) -> Draft:
    draft = _drafts.get(draft_id)
    if draft is None:
        raise _fail(404, "draft_gone")
    return draft


class FieldsIn(BaseModel):
    values: dict[str, Any] = Field(
        description="Edited form values by field key; keys left out stay as they are."
    )


@router.put("/drafts/{draft_id}/fields")
async def edit_fields(draft_id: str, body: FieldsIn) -> dict:
    """Apply edited fields to a draft and return its new preview.

    422 ``blank`` / ``too_few`` / ``too_many`` / ``too_long`` / ``invalid``
    with the field's key as ``detail``; 502 ``audio_not_set_up`` /
    ``audio_failed`` when a changed sentence needs audio that can't be made.
    Either way the draft is left as it was.
    """
    draft = _draft(draft_id)
    model = _revised(draft, body.values)
    settings = load_settings()
    apply_env(settings)
    collection = _for_draft(
        draft,
        tts=optional_speech_service(settings, draft.target)
        if draft.kind != "stem"
        else None,
    )
    try:
        async with asyncio.timeout(GENERATE_TIMEOUT_SECONDS):
            card = await collection.revise_card(draft.card, model)
    except TimeoutError as exc:
        raise _fail(504, "timeout") from exc
    except AudioUnavailable as exc:
        raise _fail(502, f"audio_{exc.reason}", exc.detail) from exc
    draft.replace(collection, card)
    return _draft_out(draft, collection)


def _revised(draft: Draft, values: dict[str, Any]) -> Any:
    try:
        return revise(draft.card.model, _form(draft.kind, draft.card), values)
    except EditError as exc:
        raise _fail(422, exc.code, exc.key) from exc


@router.post("/drafts/{draft_id}/preview")
async def preview_fields(draft_id: str, body: FieldsIn) -> dict:
    """The cards as they'd look with these edits, leaving the draft as it is.

    STEM only (409 ``not_supported`` otherwise): its edits make no media, so
    a preview needs no model. Refused values are 422s, as for an edit.
    """
    draft = _draft(draft_id)
    if draft.kind != "stem":
        raise _fail(409, "not_supported")
    collection = _for_draft(draft)
    card = await collection.revise_card(draft.card, _revised(draft, body.values))
    return {"cards": _render(draft, collection, card, collection.note_fields(card))}


class RewriteIn(BaseModel):
    instruction: str = Field(default="", max_length=500)
    card_type: CardType | None = Field(
        default=None, description="Another type to turn the card into."
    )


@router.post("/drafts/{draft_id}/rewrite")
async def rewrite_draft(draft_id: str, body: RewriteIn) -> dict:
    """Have the text model rewrite a STEM draft as the instruction asks.

    The whole card is replaced (undo brings it back); a new diagram is drawn
    only if the new card asks for a different one and pictures were on.
    409 ``not_supported`` for other kinds; 422 ``blank`` when there is
    neither an instruction nor another type; generation errors as for
    generating.
    """
    draft = _stem_draft(draft_id)
    instruction = body.instruction.strip()
    card_type = body.card_type if body.card_type != _card_type(draft) else None
    if not instruction and card_type is None:
        raise _fail(422, "blank", "instruction")

    async def rewrite(collection: StemCollection) -> Any:
        card = await collection.rewrite_card(
            draft.card, draft.source, instruction, card_type=card_type
        )
        if not draft.image:
            card.media.gaps[:] = []
        return card

    return await _remake(draft, rewrite, draws=draft.image)


class LatexErrorIn(BaseModel):
    tex: str = Field(max_length=2000)
    message: str = Field(
        default="", max_length=500, description="Empty: the formula isn't closed."
    )


class FixLatexIn(BaseModel):
    errors: list[LatexErrorIn] = Field(min_length=1, max_length=20)


@router.post("/drafts/{draft_id}/fix-latex")
async def fix_latex(draft_id: str, body: FixLatexIn) -> dict:
    """Have the text model fix the formulas the preview couldn't typeset.

    ``errors`` are what the preview reported. Only those formulas should
    change; the type and diagram stay. Undo brings the card back. Errors as
    for a rewrite.
    """
    draft = _stem_draft(draft_id)
    problems = [LatexProblem(e.tex, e.message) for e in body.errors]
    return await _remake(
        draft,
        lambda collection: collection.fix_latex(draft.card, draft.source, problems),
        draws=False,
    )


def _stem_draft(draft_id: str) -> Draft:
    draft = _draft(draft_id)
    if draft.kind != "stem":
        raise _fail(409, "not_supported")
    return draft


async def _remake(
    draft: Draft,
    make: Callable[[StemCollection], Awaitable[Any]],
    *,
    draws: bool,
) -> dict:
    """Replace a STEM draft's card with what the text model ``make``s of it.

    ``draws``: whether the collection gets the image model, for a new diagram.
    """
    settings = load_settings()
    apply_env(settings)
    text = active_profile(settings, "text")
    if text is None:
        raise _fail(409, "no_text_model")
    image = active_profile(settings, "image") if draws else None
    collection = _for_draft(
        draft,
        text_model=text.model,
        text_service=build_text_service(text),
        image_service=build_image_service(image, image_size=settings.image_size)
        if image
        else None,
    )
    assert isinstance(collection, StemCollection)
    try:
        async with asyncio.timeout(STEM_TIMEOUT_SECONDS):
            card = await make(collection)
    except TimeoutError as exc:
        raise _fail(504, "timeout") from exc
    except Exception as exc:
        logger.warning("STEM rewrite failed: {}", exc)
        raise _generation_error(exc, text.model) from exc
    draft.replace(collection, card)
    return _draft_out(draft, _for_draft(draft))


@router.post("/drafts/{draft_id}/undo")
async def undo_draft(draft_id: str) -> dict:
    """Put back the card as it was before the last edit or rewrite.

    409 ``nothing_to_undo`` when there is none.
    """
    draft = _draft(draft_id)
    if not draft.history:
        raise _fail(409, "nothing_to_undo")
    version = draft.history.pop()
    draft.card, draft.fields, draft.files = version.card, version.fields, version.files
    draft.revision += 1
    return _draft_out(draft, _for_draft(draft))


@router.get("/drafts/{draft_id}/media/{name}")
async def draft_media(draft_id: str, name: str) -> Response:
    data = _draft(draft_id).files.get(name)
    if data is None:
        raise _fail(404, "no_media")
    media_type = _MEDIA_TYPES.get(
        PurePosixPath(name).suffix, "application/octet-stream"
    )
    return Response(data, media_type=media_type, headers={"Cache-Control": "private"})


@router.post("/drafts/{draft_id}/save")
async def save_draft(draft_id: str) -> dict:
    """Write the draft's note to Anki; saving again updates the same note."""
    draft = _draft(draft_id)
    await anki_api.ready_backend()
    try:
        client = create_anki_client()
        collection = _for_draft(draft, client)
        if not await client.models.exists(collection.notetype_name):
            await collection.ensure_in_anki()
        if isinstance(collection, StemCollection):
            note_id = await collection.save_card(draft.card, replaces=draft.saved)
        else:
            note_id = await collection.save_card(draft.card)
        draft.note_id, draft.saved = note_id, draft.card
    except HTTPException:
        raise
    except Exception as exc:
        raise anki_api.note_type_error(exc) from exc

    runtime = get_shared_runtime()
    service = runtime.sync_service if runtime else None
    return {
        "note_id": draft.note_id,
        "deck": collection.deck_name,
        "sync": anki_api.sync_out(service.status) if service else None,
    }
