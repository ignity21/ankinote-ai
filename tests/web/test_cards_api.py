"""Generate → preview → save, on a real temp collection with fake models."""

import copy
import json
import os
import re
from typing import Any

import httpx
import pytest

from ankinote.model_presets import PRESETS
from ankinote.services.anki_factory import create_anki_client, get_shared_runtime
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


TAKE_OFF = {
    "phrase": "take off",
    "difficulty": "B1",
    "core_meaning": {"target_text": "to leave the ground", "native_text": "起飞"},
    "supporting_meanings": [],
    "examples": [
        {
            "sentence": "The plane takes off at six.",
            "translation": "飞机六点起飞。",
            "highlights": ["takes off"],
        }
    ],
    "usage_pattern": None,
    "production_hint": "飞机离开地面",
    "confusions": [],
    "etymology_or_memory": None,
    "associations": ["land"],
}

OVERSLEPT = {
    "target_sentence": "I overslept this morning.",
    "native_sentence": "我今天早上睡过头了。",
    "notes": ["oversleep: 睡过头"],
    "phrases": [],
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
    assert (note["kind"], note["headword"], note["variant"]) == ("word", "moon", "noun")
    assert note["deck"] == "AINote::Words"
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


@pytest.mark.parametrize(
    ("kind", "answer", "text", "deck", "templates", "first_audio"),
    [
        (
            "phrase",
            TAKE_OFF,
            "take off",
            "AINote::Phrases",
            ["Recognition", "Recall"],
            b"mp3:take off",
        ),
        (
            "sentence",
            OVERSLEPT,
            "I overslept this morning.",
            "AINote::Sentences",
            ["Production"],
            b"mp3:I overslept this morning.",
        ),
    ],
)
async def test_phrase_and_sentence_preview_then_save(
    api: httpx.AsyncClient,
    models: dict[str, Any],
    ankiweb: dict[str, Any],
    kind: str,
    answer: dict,
    text: str,
    deck: str,
    templates: list[str],
    first_audio: bytes,
) -> None:
    await builtin(api)
    await login(api)
    await _gemini(api)
    models["answer"] = json.dumps(answer)

    response = await api.post(f"/api/cards/{kind}", json={"text": text})

    assert response.status_code == 200, response.text
    [note] = response.json()["notes"]
    assert (note["kind"], note["headword"], note["variant"]) == (kind, text, "")
    assert note["deck"] == deck
    assert note["gaps"] == []
    assert [c["name"] for c in note["cards"]] == templates
    sides = note["cards"][0]["front"] + note["cards"][0]["back"]
    prefix = f"/api/cards/drafts/{note['id']}/media/"
    first = sides.split(prefix)[1].split('"')[0]
    assert (await api.get(prefix + first)).content == first_audio

    saved = await api.post(f"/api/cards/drafts/{note['id']}/save")

    assert saved.status_code == 200, saved.text
    assert saved.json()["deck"] == deck
    field = "phrase" if kind == "phrase" else "target_sentence"
    found = await create_anki_client().notes.find(
        deck_name=deck, unique_fields={field: text}
    )
    assert found == saved.json()["note_id"]


async def test_sentence_without_speech_says_so_and_never_asks_for_images(
    api: httpx.AsyncClient, models: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _gemini(api, image=False)
    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: None)
    models["answer"] = json.dumps(OVERSLEPT)

    response = await api.post(
        "/api/cards/sentence", json={"text": "I overslept this morning.", "image": True}
    )

    [note] = response.json()["notes"]
    assert note["gaps"] == [{"kind": "audio", "reason": "not_set_up", "detail": ""}]
    assert "replay-button" not in note["cards"][0]["back"]


def _form(note: dict, key: str) -> dict:
    return next(f for f in note["form"] if f["key"] == key)


def _edit(note: dict, **cells: str) -> dict:
    """Form values that change the first example's cells."""
    rows = copy.deepcopy(_form(note, "examples")["value"])
    rows[0]["cells"].update(cells)
    return {"values": {"examples": rows}}


async def _media_bodies(api: httpx.AsyncClient, note: dict) -> set[bytes]:
    back = note["cards"][0]["back"]
    prefix = f"/api/cards/drafts/{note['id']}/media/"
    paths = [part.split('"')[0].split("'")[0] for part in back.split(prefix)[1:]]
    return {(await api.get(prefix + path)).content for path in paths}


async def test_a_draft_comes_with_its_editable_form(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)

    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]

    assert _form(note, "core_meaning.native_text")["value"] == "月亮"
    assert _form(note, "examples")["value"] == [
        {
            "id": 0,
            "cells": {
                "sentence": "The moon is bright tonight.",
                "translation": "今晚月亮很亮。",
            },
        }
    ]
    assert "lemma" not in {f["key"] for f in note["form"]}


async def test_edited_fields_show_in_the_preview(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]

    response = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json={
            "values": {
                "core_meaning.native_text": "月球",
                "collocations": ["new moon", "half moon"],
            }
        },
    )

    assert response.status_code == 200, response.text
    edited = response.json()
    assert (edited["id"], edited["headword"]) == (note["id"], "moon")
    back = edited["cards"][0]["back"]
    assert "<div class='meaning-native'>月球</div>" in back
    assert "<div class='meaning-native'>月亮</div>" not in back
    assert "new moon" in back and "full moon" not in back
    assert _form(edited, "collocations")["value"] == ["new moon", "half moon"]
    # Nothing that has audio changed, so no audio was made again.
    assert await _media_bodies(api, edited) == {
        b"mp3:moon",
        b"mp3:The moon is bright tonight.",
        b"png",
    }


async def test_a_changed_example_gets_new_audio(
    api: httpx.AsyncClient, models: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _gemini(api)
    spoken: list[str] = []

    class Speech(FakeSpeech):
        async def synthesize(self, text: str) -> bytes:
            spoken.append(text)
            return await super().synthesize(text)

    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: Speech())
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    before = note["cards"][0]["back"]
    spoken.clear()

    response = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, sentence="The moon rose late."),
    )

    assert response.status_code == 200, response.text
    edited = response.json()
    assert spoken == ["The moon rose late."]
    assert await _media_bodies(api, edited) == {
        b"mp3:moon",
        b"mp3:The moon rose late.",
        b"png",
    }
    # The clip keeps its name, so its address must change for the browser.
    prefix = f"/api/cards/drafts/{note['id']}/media/"
    assert set(edited["cards"][0]["back"].split(prefix)[1:]).isdisjoint(
        before.split(prefix)[1:]
    )


async def test_an_edit_never_costs_the_audio_a_card_has(
    api: httpx.AsyncClient, models: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]

    class Broken(FakeSpeech):
        async def synthesize(self, text: str) -> bytes:
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: Broken())
    failed = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, sentence="The moon rose late."),
    )
    monkeypatch.setattr(cards_api, "optional_speech_service", lambda *_: None)
    unset = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, sentence="The moon rose late."),
    )

    assert failed.status_code == 502
    assert failed.json()["detail"] == {
        "code": "audio_failed",
        "detail": "quota exceeded",
    }
    assert unset.status_code == 502
    assert unset.json()["detail"]["code"] == "audio_not_set_up"
    # The draft is as it was; other fields can still be edited without speech.
    other = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, translation="今晚的月亮很亮。"),
    )
    assert other.status_code == 200, other.text
    assert "is bright tonight." in other.json()["cards"][0]["back"]
    assert b"mp3:The moon is bright tonight." in await _media_bodies(api, other.json())


async def test_a_card_without_audio_is_edited_without_making_any(
    api: httpx.AsyncClient, models: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _gemini(api)
    note = (
        await api.post("/api/cards/word", json={"text": "moon", "audio": False})
    ).json()["notes"][0]

    response = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, sentence="The moon rose late."),
    )

    assert response.status_code == 200, response.text
    # "moon" is highlighted, so look for the rest of the sentence.
    assert "rose late." in response.json()["cards"][0]["back"]
    assert await _media_bodies(api, response.json()) == {b"png"}


async def test_an_edit_the_card_cannot_hold_is_refused(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    url = f"/api/cards/drafts/{note['id']}/fields"

    blank = await api.put(url, json={"values": {"difficulty": " "}})
    none = await api.put(url, json={"values": {"examples": []}})
    gone = await api.put(
        "/api/cards/drafts/nope/fields", json={"values": {"difficulty": "A2"}}
    )

    assert blank.status_code == 422
    assert blank.json()["detail"] == {"code": "blank", "detail": "difficulty"}
    assert none.json()["detail"] == {"code": "too_few", "detail": "examples"}
    assert (gone.status_code, gone.json()["detail"]["code"]) == (404, "draft_gone")


async def test_phrase_and_sentence_drafts_are_edited_too(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    models["answer"] = json.dumps(TAKE_OFF)
    [phrase] = (await api.post("/api/cards/phrase", json={"text": "take off"})).json()[
        "notes"
    ]
    models["answer"] = json.dumps(OVERSLEPT)
    [sentence] = (
        await api.post(
            "/api/cards/sentence", json={"text": "I overslept this morning."}
        )
    ).json()["notes"]

    phrase_edit = await api.put(
        f"/api/cards/drafts/{phrase['id']}/fields",
        json={
            "values": {
                "associations": ["land", "touch down"],
                **_edit(phrase, sentence="Our flight took off late.")["values"],
            }
        },
    )
    sentence_edit = await api.put(
        f"/api/cards/drafts/{sentence['id']}/fields",
        json={"values": {"native_sentence": "我今早睡过头了。", "notes": []}},
    )

    assert phrase_edit.status_code == 200, phrase_edit.text
    back = phrase_edit.json()["cards"][0]["back"]
    assert "touch down" in back and "Our flight took off late." in back
    assert await _media_bodies(api, phrase_edit.json()) == {
        b"mp3:take off",
        b"mp3:Our flight took off late.",
    }
    assert sentence_edit.status_code == 200, sentence_edit.text
    card = sentence_edit.json()["cards"][0]
    assert "我今早睡过头了。" in card["front"]
    assert "oversleep" not in card["back"]


async def test_saving_an_edited_note_again_replaces_its_audio_in_anki(
    api: httpx.AsyncClient, models: dict[str, Any], ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    first = (await api.post(f"/api/cards/drafts/{note['id']}/save")).json()

    edited = await api.put(
        f"/api/cards/drafts/{note['id']}/fields",
        json=_edit(note, sentence="The moon rose late.", translation="月亮升得很晚。"),
    )
    again = await api.post(f"/api/cards/drafts/{note['id']}/save")

    assert edited.status_code == 200, edited.text
    assert edited.json()["note_id"] == first["note_id"]
    assert again.json()["note_id"] == first["note_id"]
    runtime = get_shared_runtime()
    assert runtime is not None

    def stored(col: Any) -> tuple[str, bytes]:
        examples = col.get_note(first["note_id"])["examples"]
        name = examples.split("[sound:")[1].split("]")[0]
        with open(os.path.join(col.media.dir(), name), "rb") as file:
            return examples, file.read()

    examples, audio = await runtime.submit(stored)
    assert "rose late." in examples and "月亮升得很晚。" in examples
    assert audio == b"mp3:The moon rose late."


# -- STEM -------------------------------------------------------------------

NEWTON = {
    "card_type": "formula",
    "front": "Newton's second law?",
    "latex": "F = ma",
    "meaning": "Net force equals mass times acceleration.",
    "variables": [{"symbol": "F", "description": "net force"}],
    "conditions": "Inertial frame.",
    "derivation": "",
    "tags": ["Physics", "Classical Mechanics"],
    "image_description": "A block pushed by an arrow labelled F",
}

ENTROPY = {
    "card_type": "concept",
    "front": "What is entropy?",
    "back_brief": "A measure of disorder.",
    "back_detail": "",
    "tags": ["Physics"],
    "image_description": None,
}


def _unversioned(note: dict) -> str:
    """The note's cards without media revisions (each change bumps them)."""
    return re.sub(r"\?v=\d+", "", json.dumps(note["cards"]))


async def _stem(api: httpx.AsyncClient, models: dict[str, Any], **body: Any) -> dict:
    models["answer"] = json.dumps(body.pop("answer", NEWTON))
    response = await api.post("/api/cards/stem", json={"text": "F=ma", **body})
    assert response.status_code == 200, response.text
    [note] = response.json()["notes"]
    return note


async def test_a_stem_card_previews_its_type_with_math_tags_and_diagram(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)

    note = await _stem(api, models)

    # Auto: one call to classify, one to write the card.
    assert len(models["prompts"]) == 2
    assert (note["kind"], note["headword"], note["variant"]) == (
        "stem",
        "Newton's second law?",
        "formula",
    )
    assert (note["note_type"], note["deck"]) == ("AINote STEM Formula", "AINote::STEM")
    assert note["gaps"] == [] and note["can_undo"] is False
    [card] = note["cards"]
    assert card["name"] == "Card 1"
    assert "Newton's second law?" in card["front"]
    assert r"\[F = ma\]" in card["back"]
    assert "Physics Classical_Mechanics AI-generated" in card["back"]
    assert ".stage-card" in note["css"]
    assert [f["key"] for f in note["form"]][:2] == ["front", "latex"]
    assert await _media_bodies(api, note) == {b"png"}


async def test_a_chosen_stem_type_skips_classifying(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)

    note = await _stem(api, models, card_type="formula")

    assert len(models["prompts"]) == 1
    assert note["variant"] == "formula"


async def test_a_stem_diagram_says_when_it_cannot_be_drawn_unless_turned_off(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api, image=False)

    missing = await _stem(api, models)
    off = await _stem(api, models, image=False)

    assert missing["gaps"] == [{"kind": "image", "reason": "not_set_up", "detail": ""}]
    assert off["gaps"] == []
    assert "<img" not in missing["cards"][0]["back"] + off["cards"][0]["back"]


async def test_a_stem_question_may_be_longer_than_a_word(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    problem = "A block of mass 2 kg is pushed. " * 15

    word = await api.post("/api/cards/word", json={"text": problem})
    stem = await _stem(api, models, text=problem)

    assert word.status_code == 422
    assert word.json()["detail"] == {"code": "too_long", "detail": "300"}
    assert stem["kind"] == "stem"


async def test_a_live_preview_shows_unapplied_edits_and_keeps_the_draft(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = await _stem(api, models)
    url = f"/api/cards/drafts/{note['id']}"

    live = await api.post(f"{url}/preview", json={"values": {"latex": "E = mc^2"}})
    blank = await api.post(f"{url}/preview", json={"values": {"latex": " "}})
    unchanged = await api.post(f"{url}/preview", json={"values": {}})

    assert live.status_code == 200, live.text
    [card] = live.json()["cards"]
    assert r"\[E = mc^2\]" in card["back"]
    assert "<img" in card["back"]  # the diagram stays
    assert blank.status_code == 422
    assert blank.json()["detail"] == {"code": "blank", "detail": "latex"}
    assert unchanged.json()["cards"] == note["cards"]


async def test_only_stem_drafts_have_a_live_preview_and_rewrite(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    url = f"/api/cards/drafts/{note['id']}"

    preview = await api.post(f"{url}/preview", json={"values": {}})
    rewrite = await api.post(f"{url}/rewrite", json={"instruction": "shorter"})

    assert preview.status_code == rewrite.status_code == 409
    assert preview.json()["detail"]["code"] == "not_supported"


async def test_a_rewrite_replaces_the_card_and_undo_brings_it_back(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = await _stem(api, models)
    url = f"/api/cards/drafts/{note['id']}"
    models["answer"] = json.dumps(ENTROPY)

    rewritten = await api.post(
        f"{url}/rewrite", json={"instruction": "讲概念", "card_type": "concept"}
    )

    assert rewritten.status_code == 200, rewritten.text
    out = rewritten.json()
    assert (out["id"], out["variant"], out["note_type"]) == (
        note["id"],
        "concept",
        "AINote STEM Concept",
    )
    assert out["can_undo"] is True
    assert "Instruction: 讲概念" in models["prompts"][-1]
    assert '"latex": "F = ma"' in models["prompts"][-1]
    assert "<img" not in out["cards"][0]["back"]

    undone = await api.post(f"{url}/undo")
    again = await api.post(f"{url}/undo")

    assert undone.json()["variant"] == "formula"
    assert _unversioned(undone.json()) == _unversioned(note)
    assert undone.json()["can_undo"] is False
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "nothing_to_undo"


async def test_a_rewrite_needs_an_instruction_or_another_type(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = await _stem(api, models)
    url = f"/api/cards/drafts/{note['id']}/rewrite"

    blank = await api.post(url, json={"instruction": "  "})
    same = await api.post(url, json={"card_type": "formula"})

    assert blank.status_code == same.status_code == 422
    assert blank.json()["detail"] == {"code": "blank", "detail": "instruction"}


async def test_a_failed_rewrite_leaves_the_draft_as_it_was(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = await _stem(api, models)
    models["answer"] = "not json"

    response = await api.post(
        f"/api/cards/drafts/{note['id']}/rewrite", json={"instruction": "x"}
    )
    undo = await api.post(f"/api/cards/drafts/{note['id']}/undo")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "bad_output"
    assert undo.status_code == 409


async def test_fix_latex_sends_the_preview_errors_and_can_be_undone(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = await _stem(api, models, answer={**NEWTON, "latex": r"F = m\frac{dv}{dt"})
    url = f"/api/cards/drafts/{note['id']}"
    models["answer"] = json.dumps({**NEWTON, "latex": r"F = m\frac{dv}{dt}"})

    fixed = await api.post(
        f"{url}/fix-latex",
        json={"errors": [{"tex": r"\[F = m\frac{dv}{dt", "message": ""}]},
    )

    assert fixed.status_code == 200, fixed.text
    out = fixed.json()
    assert out["id"] == note["id"] and out["variant"] == "formula"
    assert r"\[F = m\frac{dv}{dt}\]" in out["cards"][0]["back"]
    assert "<img" in out["cards"][0]["back"]  # the diagram stays
    assert "- `\\[F = m\\frac{dv}{dt` (not closed" in models["prompts"][-1]
    assert out["can_undo"] is True
    undone = await api.post(f"{url}/undo")
    assert _unversioned(undone.json()) == _unversioned(note)


async def test_fix_latex_needs_errors_and_a_stem_draft(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    word = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    stem = await _stem(api, models)
    errors = {"errors": [{"tex": "x", "message": "m"}]}

    none = await api.post(
        f"/api/cards/drafts/{stem['id']}/fix-latex", json={"errors": []}
    )
    other = await api.post(f"/api/cards/drafts/{word['id']}/fix-latex", json=errors)

    assert none.status_code == 422
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "not_supported"


async def test_an_edit_can_be_undone_for_every_kind(
    api: httpx.AsyncClient, models: dict[str, Any]
) -> None:
    await _gemini(api)
    note = (await api.post("/api/cards/word", json={"text": "moon"})).json()["notes"][0]
    url = f"/api/cards/drafts/{note['id']}"

    edited = await api.put(f"{url}/fields", json={"values": {"difficulty": "A2"}})
    undone = await api.post(f"{url}/undo")

    assert edited.json()["can_undo"] is True
    assert _unversioned(undone.json()) == _unversioned(note)


async def test_a_saved_stem_card_with_a_new_front_updates_the_same_note(
    api: httpx.AsyncClient, models: dict[str, Any], ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)
    await _gemini(api, image=False)
    note = await _stem(api, models)
    url = f"/api/cards/drafts/{note['id']}"
    first = (await api.post(f"{url}/save")).json()

    edited = await api.put(
        f"{url}/fields", json={"values": {"front": "State Newton's second law."}}
    )
    again = await api.post(f"{url}/save")

    assert edited.status_code == 200, edited.text
    assert first["deck"] == "AINote::STEM"
    assert again.json()["note_id"] == first["note_id"]
    runtime = get_shared_runtime()
    assert runtime is not None
    stored = await runtime.submit(lambda col: col.get_note(first["note_id"]))
    assert stored["front"] == "State Newton's second law."
    assert sorted(stored.tags) == ["AI-generated", "Classical_Mechanics", "Physics"]
