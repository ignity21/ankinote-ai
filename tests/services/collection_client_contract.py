"""Reusable behavioral contract for an :class:`AnkiCollectionClient`.

Subclass :class:`CollectionClientContract` and provide a ``client`` fixture that
yields a ready-to-use client. Run by both backends: the direct (local
collection) backend in ``test_anki_direct.py`` and the AnkiConnect backend
(against a real, ``anki``-library-backed fake server) in
``test_anki_connect_integration.py``.
"""

from __future__ import annotations

import pytest

from ankinote.services.anki import (
    AnkiCollectionClient,
    ModelAlreadyExists,
    ModelNotFound,
    TemplateUpsert,
)

pytestmark = pytest.mark.asyncio

_FIELDS = ["Front", "Back"]
_TEMPLATES = [
    {"Name": "Card 1", "Front": "{{Front}}", "Back": "{{FrontSide}}<hr>{{Back}}"},
]


class CollectionClientContract:
    """Behavioral cases every collection backend must satisfy."""

    # --- models -----------------------------------------------------------

    async def test_create_then_get_roundtrips(
        self, client: AnkiCollectionClient
    ) -> None:
        assert await client.models.exists("T") is False
        created = await client.models.create("T", _FIELDS, _TEMPLATES, css=".card{}")
        assert created.name == "T"
        assert [f.name for f in created.fields] == _FIELDS

        assert await client.models.exists("T") is True
        fetched = await client.models.get("T")
        assert fetched is not None
        assert fetched.id == created.id
        assert [t.name for t in fetched.templates] == ["Card 1"]
        assert await client.models.get("missing") is None

    async def test_create_existing_raises(self, client: AnkiCollectionClient) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        with pytest.raises(ModelAlreadyExists):
            await client.models.create("T", _FIELDS, _TEMPLATES)

    async def test_ensure_fields_adds_missing_only(
        self, client: AnkiCollectionClient
    ) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        await client.models.ensure_fields("T", ["Front", "Extra", "Notes"])
        model = await client.models.get("T")
        assert model is not None
        assert [f.name for f in model.fields] == ["Front", "Back", "Extra", "Notes"]

    async def test_update_templates_adds_renames_and_edits(
        self, client: AnkiCollectionClient
    ) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        await client.models.update_templates(
            "T",
            [
                TemplateUpsert("Recognition", "{{Front}}?", "{{Back}}!", "Card 1"),
                TemplateUpsert("Recall", "{{Back}}", "{{Front}}"),
            ],
        )
        model = await client.models.get("T")
        assert model is not None
        by_name = {t.name: t for t in model.templates}
        assert set(by_name) == {"Recognition", "Recall"}
        assert by_name["Recognition"].question_format == "{{Front}}?"
        assert by_name["Recall"].answer_format == "{{Front}}"

        # Second identical sync is a no-op that still succeeds.
        await client.models.update_templates(
            "T", [TemplateUpsert("Recognition", "{{Front}}?", "{{Back}}!")]
        )
        model = await client.models.get("T")
        assert model is not None
        assert [t.name for t in model.templates] == ["Recognition", "Recall"]

    async def test_update_styling(self, client: AnkiCollectionClient) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        await client.models.update_styling("T", ".card { color: teal; }")
        model = await client.models.get("T")
        assert model is not None
        assert "teal" in model.css

    async def test_model_ops_on_missing_model_raise(
        self, client: AnkiCollectionClient
    ) -> None:
        with pytest.raises(ModelNotFound):
            await client.models.update_styling("Nope", "x")

    # --- decks ----------------------------------------------------------------

    async def test_deck_create_is_idempotent(
        self, client: AnkiCollectionClient
    ) -> None:
        assert await client.decks.exists("AINote::Words") is False
        first = await client.decks.create("AINote::Words")
        second = await client.decks.create("AINote::Words")
        assert first == second
        assert await client.decks.exists("AINote::Words") is True

    # --- notes --------------------------------------------------------------

    async def test_note_add_find_update(self, client: AnkiCollectionClient) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        await client.decks.create("D")

        assert await client.notes.find("D", {"Front": "hello"}) is None
        note_id = await client.notes.add(
            "D", "T", {"Front": "hello", "Back": "world"}, tags=["x"]
        )
        assert isinstance(note_id, int)

        found = await client.notes.find("D", {"Front": "hello"}, model_name="T")
        assert found == note_id

        await client.notes.update_fields(note_id, {"Back": "changed"})
        await client.notes.update_tags(note_id, ["y", "z"])
        # find still resolves by the unchanged field
        assert await client.notes.find("D", {"Front": "hello"}) == note_id

    async def test_note_add_unknown_model_raises(
        self, client: AnkiCollectionClient
    ) -> None:
        await client.decks.create("D")
        with pytest.raises(ModelNotFound):
            await client.notes.add("D", "Ghost", {"Front": "x"})

    async def test_find_multiple_matches_raises(
        self, client: AnkiCollectionClient
    ) -> None:
        await client.models.create("T", _FIELDS, _TEMPLATES)
        await client.decks.create("D")
        await client.notes.add("D", "T", {"Front": "dup", "Back": "1"})
        await client.notes.add("D", "T", {"Front": "dup", "Back": "2"})
        with pytest.raises(KeyError):
            await client.notes.find("D", {"Front": "dup"})

    # --- media ------------------------------------------------------------

    async def test_media_store_returns_actual_filename(
        self, client: AnkiCollectionClient
    ) -> None:
        stored = await client.media.store_file("audio clip.mp3", b"ID3data")
        assert stored.endswith(".mp3")
        # The returned name is what a [sound:...] reference must use.
        assert stored
