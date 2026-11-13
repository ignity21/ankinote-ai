"""Run the collection-client contract against the direct (local) backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from collection_client_contract import CollectionClientContract

from ankinote.services.anki import TemplateUpsert
from ankinote.services.anki_direct import DirectCollectionClient
from ankinote.services.collection_runtime import CollectionRuntime

pytestmark = pytest.mark.asyncio


class TestDirectCollectionClient(CollectionClientContract):
    @pytest.fixture
    async def client(self, tmp_path: Path) -> AsyncIterator[DirectCollectionClient]:
        runtime = CollectionRuntime(str(tmp_path / "collection.anki2"))
        await runtime.open()
        try:
            yield DirectCollectionClient(runtime)
        finally:
            await runtime.close()


async def test_preserves_existing_notes_and_extra_field_across_sync(
    tmp_path: Path,
) -> None:
    """A note type refresh keeps user notes, review history, and extra fields."""
    runtime = CollectionRuntime(str(tmp_path / "collection.anki2"))
    await runtime.open()
    try:
        client = DirectCollectionClient(runtime)
        await client.models.create(
            "T",
            ["Front", "Back"],
            [{"Name": "Card 1", "Front": "{{Front}}", "Back": "{{Back}}"}],
        )
        await client.decks.create("D")
        note_id = await client.notes.add("D", "T", {"Front": "keep", "Back": "me"})

        # A user adds their own field and a review-log entry outside ankinote.
        def _user_edits(col: Any) -> None:
            mm = col.models
            model = mm.by_name("T")
            mm.add_field(model, mm.new_field("UserField"))
            mm.update_dict(model)
            card_id = col.get_note(note_id).card_ids()[0]
            col.db.execute(
                "insert into revlog values (?,?,?,?,?,?,?,?,?)",
                1,
                card_id,
                -1,
                3,
                1,
                250,
                2500,
                0,
                0,
            )

        await runtime.submit(_user_edits)

        # ankinote re-syncs the note type.
        await client.models.ensure_fields("T", ["Front", "Back"])
        await client.models.update_templates(
            "T", [TemplateUpsert("Card 1", "{{Front}}!", "{{Back}}")]
        )

        refreshed = await client.models.get("T")
        assert refreshed is not None
        assert "UserField" in [f.name for f in refreshed.fields]

        def _check(col: Any) -> tuple[str, int]:
            note = col.get_note(note_id)
            revlog_count = col.db.scalar("select count() from revlog")
            return note["Front"], revlog_count

        front, revlog_count = await runtime.submit(_check)
        assert front == "keep"
        assert revlog_count == 1
    finally:
        await runtime.close()


async def test_restyling_a_note_type_does_not_force_a_full_sync(
    tmp_path: Path,
) -> None:
    """A card theme change edits CSS only, which AnkiWeb syncs normally.

    Anki asks for a one-way full sync when the schema modification time
    moves; a CSS edit must leave it where it was.
    """
    runtime = CollectionRuntime(str(tmp_path / "collection.anki2"))
    await runtime.open()
    try:
        client = DirectCollectionClient(runtime)
        await client.models.create(
            "T",
            ["Front", "Back"],
            [{"Name": "Card 1", "Front": "{{Front}}", "Back": "{{Back}}"}],
            css=".card { color: red; }",
        )

        def _schema(col: Any) -> int:
            return col.db.scalar("select scm from col")

        before = await runtime.submit(_schema)
        await client.models.update_styling("T", ".card { color: blue; }")
        model = await client.models.get("T")
        assert model is not None and model.css == ".card { color: blue; }"
        assert await runtime.submit(_schema) == before
    finally:
        await runtime.close()
