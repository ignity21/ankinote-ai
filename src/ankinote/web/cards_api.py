"""Generate a card, preview it, then save it to Anki.

Generating doesn't touch Anki: the result is kept as a draft (note fields
plus media, in memory, newest ``_DRAFT_LIMIT``) that the preview renders and
``save`` writes. A draft outlives a failed save, so a blocked AnkiWeb sync or
a closed Anki Desktop never costs a regeneration.

Words, phrases and sentences share this flow; only words have pictures.
"""

import asyncio
import json
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Response
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from ankinote.card_render import media_path, render_card
from ankinote.collections.common import MediaGap, strip_phonetic_annotations
from ankinote.collections.phrase import templates as phrase_templates
from ankinote.collections.phrase.collection import PhraseCollection
from ankinote.collections.sentence import templates as sentence_templates
from ankinote.collections.sentence.collection import SentenceCollection
from ankinote.collections.word import templates as word_templates
from ankinote.collections.word.collection import WordCollection
from ankinote.consts import Language
from ankinote.services import model_check
from ankinote.services.ai import (
    ImageGenerationService,
    LiteLLMTextService,
    TextGenerationService,
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
_DRAFT_LIMIT = 50
_MEDIA_TYPES = {".mp3": "audio/mpeg", ".png": "image/png"}

Kind = Literal["word", "phrase", "sentence"]


class CardCollection(Protocol):
    """What the word, phrase and sentence collections have in common."""

    notetype_name: str
    deck_name: str

    def card_templates(self) -> list[dict[str, str]]: ...

    async def generate_cards(self, text: str, /) -> Sequence[Any]: ...

    def note_fields(self, card: Any, /) -> dict[str, str]: ...

    def media_files(self, card: Any, /) -> dict[str, bytes]: ...

    async def save_card(self, card: Any, /) -> int: ...

    async def ensure_in_anki(self) -> None: ...


_STYLES: dict[Kind, Callable[[], str]] = {
    "word": word_templates.load_card_style,
    "phrase": phrase_templates.load_card_style,
    "sentence": sentence_templates.load_card_style,
}


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
) -> CardCollection:
    """The collection for ``kind``; without services it can only save."""
    text_service = text_service or LiteLLMTextService()
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
    text = model.phrase if kind == "phrase" else model.target_sentence
    return strip_phonetic_annotations(text), ""


@dataclass
class Draft:
    id: str
    kind: Kind
    native: Language
    target: Language
    card: Any
    fields: dict[str, str]
    files: dict[str, bytes]
    note_id: int | None = None


_drafts: OrderedDict[str, Draft] = OrderedDict()


class GenerateIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    image: bool | None = Field(
        default=None,
        description="Words only. Omit to follow the saved default.",
    )
    audio: bool = Field(
        default=True, description="False leaves audio out, without a gap."
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


def _draft_out(draft: Draft, collection: CardCollection) -> dict:
    prefix = _media_prefix(draft.id)

    def url(name: str) -> str:
        return media_path(prefix, name)

    cards = []
    for template in collection.card_templates():
        front = render_card(template["Front"], draft.fields, media_url=url)
        back = render_card(
            template["Back"], draft.fields, front_side=front, answer=True, media_url=url
        )
        cards.append({"name": template["Name"], "front": front, "back": back})
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
        "note_id": draft.note_id,
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
    text = active_profile(settings, "text")
    if text is None:
        raise _fail(409, "no_text_model")
    want_image = kind == "word" and (
        settings.defaults.generate_image if body.image is None else body.image
    )
    image = active_profile(settings, "image") if want_image else None
    gaps = [MediaGap("image", "not_set_up")] if want_image and image is None else []
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
        tts=optional_speech_service(settings, target) if body.audio else None,
    )
    try:
        async with asyncio.timeout(GENERATE_TIMEOUT_SECONDS):
            cards = await collection.generate_cards(body.text.strip())
    except TimeoutError as exc:
        raise _fail(504, "timeout") from exc
    except Exception as exc:
        logger.warning("{} generation failed: {}", kind.capitalize(), exc)
        raise _generation_error(exc, text.model) from exc
    if not cards:
        raise _fail(502, "bad_output", "no notes")

    notes = []
    for card in cards:
        if not body.audio:
            # Turned off on purpose: nothing to report.
            card.media.gaps[:] = [g for g in card.media.gaps if g.kind != "audio"]
        card.media.gaps[:0] = gaps
        draft = Draft(
            id=uuid.uuid4().hex,
            kind=kind,
            native=native,
            target=target,
            card=card,
            fields=collection.note_fields(card),
            files=collection.media_files(card),
        )
        _keep(draft)
        notes.append(_draft_out(draft, collection))
    return {"notes": notes}


def _draft(draft_id: str) -> Draft:
    draft = _drafts.get(draft_id)
    if draft is None:
        raise _fail(404, "draft_gone")
    return draft


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
        collection = _build(
            draft.kind, client, native=draft.native, target=draft.target
        )
        if not await client.models.exists(collection.notetype_name):
            await collection.ensure_in_anki()
        draft.note_id = await collection.save_card(draft.card)
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
