"""What ankinote's note types are, and a sample note of each; no Anki needed.

The Note types page lists these and previews a sample even while Anki is
unreachable; how each one stands in Anki comes from ``/api/anki/note-types``.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from ankinote.card_theme import CardTheme, current_theme
from ankinote.collections.stem.models import CardType
from ankinote.note_types import NoteTypeSpec, build_specs
from ankinote.web import samples
from ankinote.web.cards_api import Kind, card_css, sample_note

router = APIRouter(prefix="/api/note-types")

# Built once per note type: they only change with a new release.
_samples: dict[str, dict] = {}


_LANGUAGE_KINDS: dict[str, Kind] = {
    "word": "word",
    "phrase": "phrase",
    "sentence": "sentence",
}


def _kind(spec: NoteTypeSpec) -> tuple[Kind, CardType | None]:
    if spec.key.startswith("stem_"):
        return "stem", CardType(spec.key.removeprefix("stem_"))
    return _LANGUAGE_KINDS[spec.key], None


def _spec(key: str) -> NoteTypeSpec:
    for spec in build_specs():
        if spec.key == key:
            return spec
    raise HTTPException(status_code=404, detail={"code": "unknown", "detail": key})


@router.get("")
async def list_note_types() -> list[dict]:
    """Every note type ankinote manages, in display order."""
    out = []
    for spec in build_specs():
        kind, card_type = _kind(spec)
        out.append(
            {
                "key": spec.key,
                "kind": kind,
                "stem_type": card_type,
                "name": spec.notetype_name,
                "deck": spec.deck_name,
                "fields": list(spec.fields),
                "templates": list(spec.templates),
            }
        )
    return out


def _sample_answer(kind: Kind, card_type: CardType | None) -> tuple[str, Any]:
    """What the sample is "generated" from, and the model's answer."""
    if card_type is not None:
        answer = samples.STEM[card_type]
        return answer["front"], answer
    if kind == "word":
        return samples.WORD[0]["lemma"], samples.WORD
    if kind == "phrase":
        return samples.PHRASE["phrase"], samples.PHRASE
    return samples.SENTENCE["target_sentence"], samples.SENTENCE


@router.get("/{key}/sample")
async def sample(key: str, light: str | None = None, dark: str | None = None) -> dict:
    """A sample note of this type, rendered like a draft (cards, CSS).

    ``light`` and ``dark`` preview a card theme other than the saved one.
    """
    kind, card_type = _kind(_spec(key))
    if key not in _samples:
        source, answer = _sample_answer(kind, card_type)
        _samples[key] = await sample_note(kind, source, answer, card_type)
    saved = current_theme()
    try:
        theme = CardTheme(light or saved.light, dark or saved.dark)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "unknown_palette"}) from exc
    return {**_samples[key], "css": card_css(kind, theme)}
