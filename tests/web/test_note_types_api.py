"""The Note types page: what each type is, a sample of it, its state in Anki."""

from typing import Any

import httpx
import pytest

from ankinote.services.anki_factory import create_anki_client
from tests.web.anki_fakes import builtin, login

KEYS = [
    "word",
    "phrase",
    "sentence",
    "stem_concept",
    "stem_formula",
    "stem_procedure",
    "stem_example",
]


async def test_note_types_are_listed_without_anki(api: httpx.AsyncClient) -> None:
    listed = (await api.get("/api/note-types")).json()
    assert [item["key"] for item in listed] == KEYS
    word = listed[0]
    assert word["kind"] == "word" and word["stem_type"] is None
    assert word["templates"] == ["Recognition", "Recall", "Spelling"]
    assert "lemma" in word["fields"]
    formula = listed[4]
    assert (formula["kind"], formula["stem_type"]) == ("stem", "formula")
    assert formula["name"] == "AINote STEM Formula"


@pytest.mark.parametrize("key", KEYS)
async def test_each_type_has_a_sample(api: httpx.AsyncClient, key: str) -> None:
    response = await api.get(f"/api/note-types/{key}/sample")
    assert response.status_code == 200, response.text
    note = response.json()
    listed = {item["key"]: item for item in (await api.get("/api/note-types")).json()}
    assert note["note_type"] == listed[key]["name"]
    assert [card["name"] for card in note["cards"]] == listed[key]["templates"]
    assert note["css"]
    for card in note["cards"]:
        assert card["front"].strip() and card["back"].strip()
        # Every field the templates name exists in the sample's note.
        assert "preview-error" not in card["front"] + card["back"]


async def test_samples_show_their_content(api: httpx.AsyncClient) -> None:
    word = (await api.get("/api/note-types/word/sample")).json()
    assert word["headword"] == "lantern"
    assert "灯笼" in word["cards"][0]["back"]
    formula = (await api.get("/api/note-types/stem_formula/sample")).json()
    assert formula["kind"] == "stem" and formula["variant"] == "formula"
    assert "frac{1}{2}" in formula["cards"][0]["back"]


async def test_unknown_type_is_404(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/note-types/nope/sample")).status_code == 404
    assert (await api.post("/api/anki/note-types/nope")).status_code == 404


async def test_one_type_is_set_up_on_its_own(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)

    created = (await api.post("/api/anki/note-types/phrase")).json()
    assert created["result"] == "created"
    assert created["state"] == "synced" and created["deck_exists"]

    listed = {i["key"]: i for i in (await api.get("/api/anki/note-types")).json()}
    assert listed["phrase"]["state"] == "synced"
    assert listed["word"]["state"] == "missing"

    again = (await api.post("/api/anki/note-types/phrase")).json()
    assert again["result"] == "unchanged"


async def test_changed_styling_shows_and_is_updated(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)
    await api.post("/api/anki/note-types/word")
    await create_anki_client().models.update_styling("AINote Word V2", ".card {}")

    listed = {i["key"]: i for i in (await api.get("/api/anki/note-types")).json()}
    word = listed["word"]
    assert word["state"] == "update"
    assert word["css_differs"] is True
    assert word["missing_fields"] == [] and word["missing_templates"] == []

    updated = (await api.post("/api/anki/note-types/word")).json()
    assert updated["result"] == "updated"
    assert updated["state"] == "synced" and updated["css_differs"] is False


async def test_one_type_waits_for_the_first_sync(api: httpx.AsyncClient) -> None:
    await builtin(api)
    response = await api.post("/api/anki/note-types/word")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "write_blocked"
