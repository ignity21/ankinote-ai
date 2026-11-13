"""STEM initialization creates four independent note types, without legacy writes."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from ankinote.card_theme import font_files
from ankinote.collections.stem import CardType, StemCollection
from ankinote.collections.stem.models import NOTE_FIELDS, note_type_name
from ankinote.services.ai import TextGenerationService
from ankinote.services.anki import AnkiCollectionClient


@pytest.mark.parametrize("exists", [True, False])
@pytest.mark.parametrize("selected", [None, *CardType])
async def test_stem_sync_types(exists, selected):
    models = SimpleNamespace(
        exists=AsyncMock(return_value=exists),
        create=AsyncMock(),
        ensure_fields=AsyncMock(),
        update_templates=AsyncMock(),
        update_styling=AsyncMock(),
    )
    decks = SimpleNamespace(create=AsyncMock(return_value=1))
    media = SimpleNamespace(store_file=AsyncMock(side_effect=lambda name, _: name))
    client = SimpleNamespace(models=models, decks=decks, media=media)
    collection = StemCollection(
        cast(AnkiCollectionClient, client),
        card_type=selected,
        text_model="test",
        text_service=cast(TextGenerationService, object()),
    )
    await collection.ensure_in_anki()
    kinds = [selected] if selected else list(CardType)
    assert models.exists.await_count == len(kinds)
    for index, kind in enumerate(kinds):
        assert models.exists.await_args_list[index].args == (note_type_name(kind),)
        if exists:
            args = models.ensure_fields.await_args_list[index].args
            assert args == (note_type_name(kind), list(NOTE_FIELDS[kind]))
            assert (
                models.update_templates.await_args_list[index].args[1][0].name
                == "Card 1"
            )
        else:
            kwargs = models.create.await_args_list[index].kwargs
            assert kwargs["model_name"] == note_type_name(kind)
            assert kwargs["fields"][0] == "front"
            assert kwargs["fields"] == list(NOTE_FIELDS[kind])
            assert "{{card_type}}" not in kwargs["templates"][0]["Front"]
    decks.create.assert_awaited_once_with("AINote::STEM")
    # The card fonts go into the collection's media with the note types.
    stored = {call.args[0] for call in media.store_file.await_args_list}
    assert stored == set(font_files())
