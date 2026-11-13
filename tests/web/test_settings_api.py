"""Settings, model routes and connection-check endpoints."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import litellm
import pytest
from fastapi.testclient import TestClient

from ankinote import settings as settings_module
from ankinote.model_presets import PRESETS
from ankinote.services import model_check
from ankinote.settings import (
    ProviderProfile,
    Settings,
    load_settings,
    save_settings,
)
from ankinote.web.app import create_app

GEMINI = PRESETS["gemini"]

GEMINI_LIST = {
    "models": [
        {"name": f"models/{name}", "supportedGenerationMethods": methods}
        for name, methods in [
            ("gemini-3.8-flash", ["generateContent"]),
            ("gemini-3.5-flash-lite", ["generateContent"]),
            ("gemini-3.1-flash-lite-image", ["generateContent"]),
            ("gemini-3.8-flash-tts", ["generateContent"]),
            # Speech models are served by the Interactions API.
            ("gemini-3.8-flash-lite-tts", ["createInteraction"]),
            ("text-embedding-005", ["embedContent"]),
        ]
    ]
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "no-dist"))


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A fake provider: completions and model lists, with recorded calls."""
    state: dict[str, Any] = {
        "completion": lambda **_: _completion("OK"),
        "list": GEMINI_LIST,
        "list_status": 200,
        # "host/path" -> (status, json), for providers other than the default.
        "routes": {},
        "requests": [],
        "completions": [],
    }

    async def acompletion(**kwargs: Any) -> Any:
        state["completions"].append(kwargs)
        return state["completion"](**kwargs)

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        override = state["routes"].get(f"{request.url.host}{request.url.path}")
        if override is not None:
            return httpx.Response(override[0], json=override[1])
        return httpx.Response(state["list_status"], json=state["list"])

    real_client = httpx.AsyncClient

    def make_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr("ankinote.services.ai.acompletion", acompletion)
    monkeypatch.setattr(model_check.httpx, "AsyncClient", make_client)
    return state


def _completion(text: str) -> Any:
    message = type("M", (), {"content": text})
    choice = type("C", (), {"message": message})
    return type("R", (), {"choices": [choice]})


def _raise(exc: Exception) -> Callable[..., Any]:
    def fail(**_: Any) -> Any:
        raise exc

    return fail


def _gemini_routes(key: str | None = "AIza-test-key-1234") -> dict:
    route = {"provider": "gemini", "api_key": key}
    return {
        "text": {**route, "model": GEMINI.models["text"]},
        "image": {**route, "model": GEMINI.models["image"]},
        "speech": {**route, "model": GEMINI.models["speech"]},
    }


# ---- settings read / write ------------------------------------------------


def test_fresh_install_needs_setup(client: TestClient) -> None:
    body = client.get("/api/settings").json()

    assert body["needs_setup"] is True
    assert body["models"]["speech"] is None


def test_patch_settings_saves_languages(client: TestClient) -> None:
    response = client.patch(
        "/api/settings",
        json={"native_language": "English", "target_language": "Japanese"},
    )

    assert response.status_code == 200
    saved = load_settings().defaults
    assert (saved.native_language, saved.target_language) == ("English", "Japanese")


def test_patch_settings_rejects_unsupported_target(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"target_language": "Korean"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_target"


def test_patch_settings_rejects_learning_your_own_language(client: TestClient) -> None:
    response = client.patch(
        "/api/settings",
        json={"native_language": "Japanese", "target_language": "Japanese"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "same_language"


def test_patch_checks_the_pair_against_the_saved_half(client: TestClient) -> None:
    # The saved target is English; making English the native would pair it
    # with itself even though the patch names only one side.
    response = client.patch("/api/settings", json={"native_language": "English"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "same_language"
    assert load_settings().defaults.native_language == "Chinese(Simplified)"


def test_patch_settings_rejects_other_as_native(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"native_language": "other"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_native"


def test_languages_lists_choices_and_the_saved_pair(client: TestClient) -> None:
    body = client.get("/api/languages").json()

    assert body["native"] == "Chinese(Simplified)"
    assert body["target"] == "English"
    assert "other" not in body["natives"]
    assert {"English", "Chinese(Traditional)", "Korean"} <= set(body["natives"])
    assert [t["id"] for t in body["targets"]] == [
        "English",
        "French",
        "Spanish",
        "German",
        "Japanese",
    ]
    assert all(t["beta"] is False for t in body["targets"])


def test_providers_lists_presets_with_recommended_first(client: TestClient) -> None:
    body = client.get("/api/models/providers").json()

    assert body[0]["id"] == "gemini"
    assert body[0]["recommended"] is True
    deepseek = next(p for p in body if p["id"] == "deepseek")
    assert set(deepseek["models"]) == {"text"}


# ---- saving routes --------------------------------------------------------


def test_put_models_saves_one_key_for_every_route(client: TestClient) -> None:
    response = client.put("/api/models", json=_gemini_routes())

    assert response.status_code == 200
    body = response.json()
    assert body["needs_setup"] is False
    for route in ("text", "image", "speech"):
        view = body["models"][route]
        assert view["provider"] == "gemini"
        assert view["model"] == GEMINI.models[route]
        assert view["follows_preset"] is True
        assert view["key_hint"] == "…1234"
    saved = load_settings()
    assert saved.text_providers["Gemini"].api_key == "AIza-test-key-1234"
    assert saved.speech_providers["Gemini"].preset == "gemini"


def test_put_models_never_returns_the_key(client: TestClient) -> None:
    response = client.put("/api/models", json=_gemini_routes())

    assert "AIza-test-key-1234" not in response.text


def test_put_models_drops_keyless_default_profiles(client: TestClient) -> None:
    # A fresh install ships an "OpenAI" text profile with no key.
    assert "OpenAI" in load_settings().text_providers

    client.put("/api/models", json=_gemini_routes())

    assert set(load_settings().text_providers) == {"Gemini"}


def test_put_models_turns_routes_off(client: TestClient) -> None:
    routes = {
        "text": {"provider": "deepseek", "model": "deepseek-flash", "api_key": "sk-ds"},
        "image": None,
        "speech": None,
    }

    body = client.put("/api/models", json=routes).json()

    assert body["models"]["image"] is None
    assert body["models"]["speech"] is None
    saved = load_settings()
    assert saved.text_providers["DeepSeek"].base_url == "https://api.deepseek.com"


def test_image_route_turned_off_stays_off_after_reload(client: TestClient) -> None:
    """Turning images off kept the Gemini image profile, which loading revived."""
    client.put("/api/models", json=_gemini_routes())
    routes = _gemini_routes(key=None)
    routes["image"] = None

    client.put("/api/models", json=routes)

    assert "Gemini" in load_settings().image_providers
    assert client.get("/api/settings").json()["models"]["image"] is None


def test_route_from_a_text_only_provider_is_rejected(client: TestClient) -> None:
    routes = {
        "text": {"provider": "deepseek", "model": "deepseek-flash", "api_key": "sk"},
        "image": {"provider": "deepseek", "model": "x", "api_key": "sk"},
    }

    response = client.put("/api/models", json=routes)

    assert response.status_code == 422
    assert response.json()["detail"]["route"] == "image"


def test_missing_key_without_a_saved_one_is_422(client: TestClient) -> None:
    response = client.put("/api/models", json=_gemini_routes(key=None))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "key_missing"


def test_omitted_key_reuses_the_saved_key(client: TestClient) -> None:
    client.put("/api/models", json=_gemini_routes())
    routes = _gemini_routes(key=None)
    routes["text"]["model"] = "gemini/gemini-3.5-flash-lite"

    client.put("/api/models", json=routes)

    text = load_settings().text_providers["Gemini"]
    assert text.api_key == "AIza-test-key-1234"
    assert text.model == "gemini/gemini-3.5-flash-lite"


def test_edited_model_stops_following_the_preset(client: TestClient) -> None:
    routes = _gemini_routes()
    routes["text"]["model"] = "gemini/gemini-3.5-flash-lite"

    body = client.put("/api/models", json=routes).json()

    assert body["models"]["text"]["follows_preset"] is False
    assert body["models"]["image"]["follows_preset"] is True


def test_route_can_use_a_second_provider(client: TestClient) -> None:
    routes = {
        "text": {"provider": "deepseek", "model": "deepseek-flash", "api_key": "sk-ds"},
        "image": {
            "provider": "gemini",
            "model": GEMINI.models["image"],
            "api_key": "AIza-image-key",
        },
    }

    client.put("/api/models", json=routes)

    saved = load_settings()
    assert saved.active_image_provider == "Gemini"
    assert saved.image_providers["Gemini"].api_key == "AIza-image-key"


def test_custom_endpoint_without_key_is_allowed(client: TestClient) -> None:
    routes = {
        "text": {
            "provider": "custom",
            "model": "qwen3",
            "base_url": "http://localhost:11434/v1",
        }
    }

    body = client.put("/api/models", json=routes).json()

    assert body["needs_setup"] is False
    assert body["models"]["text"]["profile"] == "localhost"


# ---- preset-following on upgrade ------------------------------------------


def test_untouched_route_moves_to_new_preset_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.put("/api/models", json=_gemini_routes())
    routes = _gemini_routes(key=None)
    routes["image"]["model"] = "gemini/gemini-3-pro-image"
    client.put("/api/models", json=routes)

    newer = {**GEMINI.models, "text": "gemini/gemini-9-flash", "image": "gemini/x"}
    monkeypatch.setitem(
        settings_module.PRESETS,
        "gemini",
        type(GEMINI)(**{**_preset_fields(GEMINI), "models": newer}),
    )

    saved = load_settings()
    assert saved.text_providers["Gemini"].model == "gemini/gemini-9-flash"
    assert saved.image_providers["Gemini"].model == "gemini/gemini-3-pro-image"


def _preset_fields(preset: Any) -> dict[str, Any]:
    return {name: getattr(preset, name) for name in preset.__slots__}


# ---- 0.x settings.json ----------------------------------------------------


def test_0x_google_tts_key_shows_as_speech_route(tmp_path: Path) -> None:
    path = tmp_path / "ankinote" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "text_providers": {
                    "DeepSeek": {
                        "vendor": "Custom / Other",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "sk-old-deepseek",
                    }
                },
                "active_text_provider": "DeepSeek",
                "image_providers": {},
                "api_keys": {"GOOGLE_TTS_KEY": "google-tts-key-9876"},
            }
        )
    )
    client = TestClient(create_app(tmp_path / "no-dist"))

    body = client.get("/api/settings").json()

    assert body["needs_setup"] is False
    text = body["models"]["text"]
    assert (text["provider"], text["model"]) == ("deepseek", "deepseek-chat")
    assert text["follows_preset"] is False
    assert body["models"]["speech"]["model"] == "Chirp3-HD"
    assert load_settings().api_keys["GOOGLE_TTS_KEY"] == "google-tts-key-9876"


def test_saved_settings_round_trip_speech_routes() -> None:
    settings = Settings()
    settings.speech_providers = {
        "OpenAI": ProviderProfile("OpenAI", "gpt-4o-mini-tts", "", "sk", "openai")
    }
    settings.active_speech_provider = "OpenAI"

    save_settings(settings)

    loaded = load_settings()
    assert loaded.active_speech_provider == "OpenAI"
    assert loaded.speech_providers["OpenAI"].base_url == PRESETS["openai"].base_url


# ---- test connection ------------------------------------------------------


def test_connection_check_reports_every_route(
    client: TestClient, provider: dict[str, Any]
) -> None:
    body = client.post("/api/models/test", json=_gemini_routes()).json()

    assert body["text"] == {
        "status": "ok",
        "model": GEMINI.models["text"],
        "checked": "generated",
        "code": "",
        "detail": "",
    }
    assert body["image"]["status"] == "ok"
    assert body["image"]["checked"] == "listed"
    assert body["speech"]["status"] == "ok"
    # Testing never saves.
    assert "Gemini" not in load_settings().text_providers


def test_connection_check_uses_the_pasted_key(
    client: TestClient, provider: dict[str, Any]
) -> None:
    client.post("/api/models/test", json=_gemini_routes())

    assert provider["completions"][0]["api_key"] == "AIza-test-key-1234"
    assert provider["completions"][0]["model"] == GEMINI.models["text"]
    listed = provider["requests"][0]
    assert listed.url.path == "/v1beta/models"
    assert listed.url.params["key"] == "AIza-test-key-1234"


def test_off_routes_are_reported_off(
    client: TestClient, provider: dict[str, Any]
) -> None:
    routes = {
        "text": {"provider": "deepseek", "model": "deepseek-flash", "api_key": "k"}
    }

    body = client.post("/api/models/test", json=routes).json()

    assert body["text"]["status"] == "ok"
    assert body["image"] == {
        "status": "off",
        "model": "",
        "checked": "",
        "code": "",
        "detail": "",
    }


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (litellm.AuthenticationError("bad key", "gemini", "m"), "auth"),
        (
            litellm.BadRequestError(
                "API key not valid. Please pass a valid API key.", "m", "gemini"
            ),
            "auth",
        ),
        (litellm.NotFoundError("no such model", "gemini", "m"), "model_not_found"),
        (litellm.RateLimitError("quota", "gemini", "m"), "quota"),
        (
            litellm.RateLimitError(
                "Quota exceeded for metric: generate_content_free_tier_requests,"
                " limit: 0",
                "gemini",
                "m",
            ),
            "billing",
        ),
        (TimeoutError(), "timeout"),
    ],
)
def test_text_failures_are_classified(
    client: TestClient, provider: dict[str, Any], error: Exception, code: str
) -> None:
    provider["completion"] = _raise(error)

    body = client.post("/api/models/test", json=_gemini_routes()).json()

    assert body["text"]["status"] == "failed"
    assert body["text"]["code"] == code


def test_unlisted_image_model_fails_by_name(
    client: TestClient, provider: dict[str, Any]
) -> None:
    routes = _gemini_routes()
    routes["image"]["model"] = "gemini/retired-image-model"

    body = client.post("/api/models/test", json=routes).json()

    assert body["image"]["status"] == "failed"
    assert body["image"]["code"] == "model_not_found"
    assert body["image"]["model"] == "gemini/retired-image-model"


def test_gemini_bad_key_on_list_is_auth(
    client: TestClient, provider: dict[str, Any]
) -> None:
    provider["list_status"] = 400
    provider["list"] = {
        "error": {"message": "API key not valid.", "status": "INVALID_ARGUMENT"}
    }

    body = client.post("/api/models/test", json=_gemini_routes()).json()

    assert body["image"]["code"] == "auth"


def test_custom_endpoint_without_model_list_is_unverified(
    client: TestClient, provider: dict[str, Any]
) -> None:
    provider["list_status"] = 404
    custom = {"provider": "custom", "model": "m", "base_url": "http://local.test/v1"}

    body = client.post(
        "/api/models/test", json={"text": custom, "image": custom}
    ).json()

    assert body["image"]["status"] == "unverified"


# ---- model lists ----------------------------------------------------------


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("text", ["gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash-lite"]),
        ("image", ["gemini/gemini-3.1-flash-lite-image"]),
        (
            "speech",
            ["gemini/gemini-3.8-flash-lite-tts", "gemini/gemini-3.8-flash-tts"],
        ),
    ],
)
def test_list_models_filters_by_route(
    client: TestClient, provider: dict[str, Any], route: str, expected: list[str]
) -> None:
    body = client.post(
        "/api/models/list",
        json={"route": route, "target": {"provider": "gemini", "api_key": "k"}},
    ).json()

    assert body["models"] == expected


def test_list_models_reports_auth_failure(
    client: TestClient, provider: dict[str, Any]
) -> None:
    provider["list_status"] = 401
    provider["list"] = {"error": "invalid key"}

    body = client.post(
        "/api/models/list",
        json={"route": "text", "target": {"provider": "openai", "api_key": "k"}},
    ).json()

    assert body == {"models": [], "code": "auth", "detail": '{"error":"invalid key"}'}


# ---- single-route providers ----------------------------------------------

VOICES = {
    "voices": [
        {"name": "en-US-Chirp3-HD-Aoede"},
        {"name": "ja-JP-Chirp3-HD-Kore"},
        {"name": "en-US-Neural2-A"},
        {"name": "Kore"},
    ]
}
GOOGLE_TTS = {"provider": "google_tts", "model": "Chirp3-HD", "api_key": "gc-key"}
FAL = {"provider": "fal", "model": "fal_ai/fal-ai/flux/schnell", "api_key": "fal-key"}


def _with_text(**routes: dict) -> dict:
    return {"text": _gemini_routes()["text"], "image": None, "speech": None, **routes}


def test_providers_include_fal_and_google_cloud_tts(client: TestClient) -> None:
    providers = {p["id"]: p for p in client.get("/api/models/providers").json()}

    assert providers["fal"]["models"] == {"image": "fal_ai/fal-ai/flux/schnell"}
    assert providers["google_tts"]["models"] == {"speech": "Chirp3-HD"}
    assert providers["openai"]["models"]["text"] == "gpt-6-luna"


def test_google_cloud_tts_checks_the_voice_family(
    client: TestClient, provider: dict[str, Any]
) -> None:
    provider["routes"]["texttospeech.googleapis.com/v1/voices"] = (200, VOICES)

    body = client.post("/api/models/test", json=_with_text(speech=GOOGLE_TTS)).json()

    assert body["speech"]["status"] == "ok"
    assert body["speech"]["checked"] == "listed"
    voices = next(r for r in provider["requests"] if r.url.path == "/v1/voices")
    assert voices.url.params["key"] == "gc-key"


def test_google_cloud_tts_with_the_api_disabled(
    client: TestClient, provider: dict[str, Any]
) -> None:
    disabled = {
        "error": {
            "code": 403,
            "message": "Cloud Text-to-Speech API has not been used in project 1 "
            "before or it is disabled.",
            "status": "PERMISSION_DENIED",
            "details": [{"reason": "SERVICE_DISABLED"}],
        }
    }
    provider["routes"]["texttospeech.googleapis.com/v1/voices"] = (403, disabled)

    body = client.post("/api/models/test", json=_with_text(speech=GOOGLE_TTS)).json()

    assert body["speech"]["code"] == "api_disabled"


def test_google_cloud_tts_lists_voice_families(
    client: TestClient, provider: dict[str, Any]
) -> None:
    provider["routes"]["texttospeech.googleapis.com/v1/voices"] = (200, VOICES)

    body = client.post(
        "/api/models/list", json={"route": "speech", "target": GOOGLE_TTS}
    ).json()

    assert body["models"] == ["Chirp3-HD", "Neural2"]


def test_fal_image_model_is_checked_against_its_list(
    client: TestClient, provider: dict[str, Any]
) -> None:
    fal_models = {"models": [{"endpoint_id": "fal-ai/flux/schnell"}]}
    provider["routes"]["api.fal.ai/v1/models"] = (200, fal_models)

    body = client.post("/api/models/test", json=_with_text(image=FAL)).json()

    assert body["image"]["status"] == "ok"
    listed = next(r for r in provider["requests"] if r.url.host == "api.fal.ai")
    assert listed.headers["authorization"] == "Key fal-key"


def test_fal_is_saved_with_its_own_key(client: TestClient) -> None:
    response = client.put("/api/models", json=_with_text(image=FAL))

    assert response.status_code == 200
    saved = load_settings()
    fal = saved.image_providers[saved.active_image_provider]
    assert (fal.vendor, fal.api_key, fal.base_url) == (
        "Fal",
        "fal-key",
        "https://fal.run",
    )
    assert fal.preset == "fal"


def test_fal_cannot_serve_text(client: TestClient) -> None:
    response = client.put("/api/models", json={"text": {**FAL, "model": "m"}})

    assert response.status_code == 422
