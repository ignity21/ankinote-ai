"""Tests for the note-type specs shared by the web API and the GUI."""

from typing import cast

import pytest

from ankinote import note_types
from ankinote.collections.stem.models import CardType, note_type_name
from ankinote.services.anki import AnkiCollectionClient


async def test_stem_specs_sync_each_independent_type(monkeypatch):
    selected = []

    class FakeStemCollection:
        def __init__(self, client, **kwargs):
            selected.append(kwargs["card_type"])

        async def ensure_in_anki(self):
            pass

    monkeypatch.setattr(note_types, "StemCollection", FakeStemCollection)
    specs = [spec for spec in note_types.build_specs() if spec.key.startswith("stem_")]
    assert len(specs) == 4
    for spec, kind in zip(specs, CardType, strict=True):
        assert spec.notetype_name == note_type_name(kind)
        assert spec.fields[0] == "front"
        assert "card_type" not in spec.fields
        await spec.sync(cast(AnkiCollectionClient, object()))
    assert selected == list(CardType)


@pytest.mark.asyncio
async def test_sentence_note_type_sync_uses_only_sentence_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentence sync does not pass WordCollection's image dependency."""
    captured_kwargs: dict[str, object] = {}

    class FakeSentenceCollection:
        def __init__(self, client: AnkiCollectionClient, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        async def ensure_in_anki(self) -> None:
            return None

    monkeypatch.setattr(note_types, "SentenceCollection", FakeSentenceCollection)
    spec = next(spec for spec in note_types.build_specs() if spec.key == "sentence")

    await spec.sync(cast(AnkiCollectionClient, object()))

    assert "image_service" not in captured_kwargs
    assert captured_kwargs["notetype_name"] == "AINote Sentence V2"
    assert captured_kwargs["deck_name"] == "AINote::Sentences"
