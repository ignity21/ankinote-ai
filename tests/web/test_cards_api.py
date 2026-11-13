"""Generate → preview → save, on a real temp collection with fake models."""

import json
from typing import Any

import httpx
import pytest

from ankinote.model_presets import PRESETS
from ankinote.services.anki_factory import create_anki_client
from ankinote.web import cards_api
from tests.web.anki_fakes import builtin, login

GEMINI = PRESETS["gemini"]

MOON = {
    "lemma": "moon",
    "part_of_speech": "noun",
    "pronunciation": "/muːn/",
    "difficulty": "A1",
    "core_meaning": {
        "target_text": "the natural satellite of the Earth",
        "native_text": "月亮",
        "image_prompt": "A full moon over a quiet lake at night",
        "is_visualizable": True,
    },
    "examples": [
        {
            "sentence": "The moon is bright tonight.",
            "translation": "今晚月亮很亮。",
            "highlights": ["moon"],
        }
    ],
    "collocations": ["full moon"],
}


def _completion(text: str) -> Any:
    message = type("M", (), {"content": text})
    choice = type("C", (), {"message": message})
    return type("R", (), {"choices": [choice]})


class FakeSpeech:
    async def synthesize(self, text: str) -> bytes:
        return f"mp3:{text}".encode()

    async def warmup(self) -> None: ...

    def clear_cache(self) -> None: ...


class FakeImages:
    async def generate_image(self, *, prompt: str) -> bytes:
        return b"png"


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fake text answers; speech and images on unless a test turns them off."""
    state: dict[str, Any] = {"answer": json.dumps([MOON]), "prompts": []}

    async def acompletion(**kwargs: Any) -> Any:
        state["prompts"].append(kwargs["messages"][-1]["content"])
        answer = state["answer"]
        if isinstance(answer, Exception):
            raise answer
        return _completion(answer)

    monkeypatch.setattr("ankinote.services.ai.acompletion", acompletion)
    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: FakeSpeech())
    monkeypatch.setattr(cards_api, "build_image_service", lambda *_, **__: FakeImages())
    monkeypatch.setattr(cards_api, "_drafts", type(cards_api._drafts)())
    return state


async def _gemini(api: httpx.AsyncClient, *, image: bool = True) -> None:
    route = {"provider": "gemini", "api_key": "AIza-test-key-1234"}
    routes: dict[str, Any] = {"text": {**route, "model": GEMINI.models["text"]}}
    if image:
        routes["image"] = {**route, "model": GEMINI.models["image"]}
    response = await api.put("/api/models", json=routes)
    assert response.status_code == 200, response.text


async def test_generate_returns_a_preview_of_every_card(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)

    response = await api.post("/api/cards/word", json={"text": " moon "})

    assert response.status_code == 200, response.text
    [note] = response.json()["notes"]
    assert models["prompts"][0].startswith("Word: moon\n")
    assert (note["lemma"], note["deck"]) == ("moon", "AINote::Words")
    assert note["gaps"] == []
    assert [c["name"] for c in note["cards"]] == ["Recognition", "Recall", "Spelling"]
    recognition = note["cards"][0]
    assert "moon" in recognition["front"] and "replay-button" in recognition["front"]
    assert "月亮" in recognition["back"]
    assert ".stage-card" in note["css"]


async def test_preview_media_is_served_from_the_draft(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    back = note["cards"][0]["back"]
    prefix = f"/api/cards/drafts/{note['id']}/media/"
    names = [part.split('"')[0].split("'")[0] for part in back.split(prefix)[1:]]

    bodies = {(await api.get(prefix + name)).content for name in names}

    assert bodies == {b"mp3:moon", b"mp3:The moon is bright tonight.", b"png"}
    assert (await api.get(prefix + "other.mp3")).status_code == 404


async def test_missing_routes_make_a_card_without_media_and_say_so(
    api: httpx.AsyncClient, models: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _gemini(api, image=False)
    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: None)

    response = await api.post("/api/cards/word", json={"text": "moon"})

    [note] = response.json()["notes"]
    assert {(g["kind"], g["reason"]) for g in note["gaps"]} == {
        ("image", "not_set_up"),
        ("audio", "not_set_up"),
    }
    assert "replay-button" not in note["cards"][0]["front"]
    assert "<img" not in note["cards"][0]["back"]


async def test_media_turned_off_is_left_out_without_a_gap(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)

    response = await api.post(
        "/api/cards/word", json={"text": "moon", "image": False, "audio": False}
    )

    [note] = response.json()["notes"]
    assert note["gaps"] == []
    assert "replay-button" not in note["cards"][0]["front"]
    assert "<img" not in note["cards"][0]["back"]


async def test_unreadable_model_answer_is_bad_output(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    models["answer"] = "Sorry, I can't help with that."

    response = await api.post("/api/cards/word", json={"text": "moon"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "bad_output"


async def test_rejected_key_is_auth(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    models["answer"] = RuntimeError("API key not valid. Please pass a valid API key.")

    response = await api.post("/api/cards/word", json={"text": "moon"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "auth"


async def test_save_writes_the_note_and_saving_again_updates_it(
    api: httpx.AsyncClient, models: dict[str, Any], ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]

    first = await api.post(f"/api/cards/drafts/{note['id']}/save")
    again = await api.post(f"/api/cards/drafts/{note['id']}/save")

    assert first.status_code == 200, first.text
    saved = first.json()
    assert saved["deck"] == "AINote::Words"
    assert saved["sync"]["state"] == "idle"
    assert again.json()["note_id"] == saved["note_id"]
    client = create_anki_client()
    found = await client.notes.find(
        deck_name="AINote::Words",
        unique_fields={"lemma": "moon", "part_of_speech": "noun"},
    )
    assert found == saved["note_id"]


async def test_save_waits_for_the_first_sync(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await builtin(api)
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]

    response = await api.post(f"/api/cards/drafts/{note['id']}/save")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "write_blocked"
    # The draft is still there to save once AnkiWeb is sorted out.
    assert (await api.post(f"/api/cards/drafts/{note['id']}/save")).status_code == 409


async def test_unknown_draft_is_gone(api: httpx.AsyncClient) -> None:
    response = await api.post("/api/cards/drafts/nope/save")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "draft_gone"
