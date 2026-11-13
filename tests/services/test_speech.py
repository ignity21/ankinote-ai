"""Gemini / OpenAI speech services and building one from the speech route."""

import base64
import io
import json
import wave
from typing import Any

import httpx
import pytest

from ankinote.consts import Language
from ankinote.model_presets import PRESETS
from ankinote.services import speech
from ankinote.services.provider_factory import build_speech_service, speech_service_for
from ankinote.services.speech import (
    GeminiSpeechService,
    OpenAISpeechService,
    SpeechError,
    audio_to_mp3,
)
from ankinote.services.tts import GoogleTTSService
from ankinote.settings import ProviderProfile, Settings

GEMINI = PRESETS["gemini"]
OPENAI = PRESETS["openai"]
SILENCE = b"\x00\x00" * 2400  # 0.1 s of 24 kHz mono 16-bit PCM


def _wav(pcm: bytes, rate: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _is_mp3(data: bytes) -> bool:
    # An MPEG audio frame starts with 11 set sync bits.
    return len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A fake speech endpoint that records requests."""
    state: dict[str, Any] = {"requests": [], "response": httpx.Response(500)}

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return state["response"]

    real_client = httpx.AsyncClient

    def make_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(speech.httpx, "AsyncClient", make_client)
    return state


def _gemini() -> GeminiSpeechService:
    return GeminiSpeechService(
        model=GEMINI.models["speech"], api_key="AIza-key", base_url=GEMINI.base_url
    )


async def test_gemini_speech_sends_an_interaction_and_returns_mp3(
    server: dict[str, Any],
) -> None:
    audio = {"type": "audio", "mime_type": "audio/wav", "data": ""}
    audio["data"] = base64.b64encode(_wav(SILENCE)).decode()
    server["response"] = httpx.Response(
        200, json={"steps": [{"type": "model_output", "content": [audio]}]}
    )

    result = await _gemini().synthesize("hello")

    assert _is_mp3(result)
    request = server["requests"][0]
    assert str(request.url) == f"{GEMINI.base_url}/interactions"
    assert request.headers["x-goog-api-key"] == "AIza-key"
    body = json.loads(request.content)
    assert body["model"] == "gemini-3.8-flash-lite-tts"
    assert body["input"][0]["content"][0]["text"] == "hello"
    assert body["response_format"] == {"type": "audio"}
    assert (
        body["generation_config"]["speech_config"][0]["voice"] in speech.GEMINI_VOICES
    )
    assert body["store"] is False


async def test_gemini_speech_reads_generate_content_pcm(
    server: dict[str, Any],
) -> None:
    part = {
        "inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000",
            "data": base64.b64encode(SILENCE).decode(),
        }
    }
    server["response"] = httpx.Response(
        200, json={"candidates": [{"content": {"parts": [part]}}]}
    )

    assert _is_mp3(await _gemini().synthesize("hello"))


async def test_gemini_speech_without_audio_is_an_error(server: dict[str, Any]) -> None:
    server["response"] = httpx.Response(200, json={"steps": []})

    with pytest.raises(RuntimeError, match="no audio"):
        await _gemini().synthesize("hello")


async def test_speech_error_carries_status_and_body(server: dict[str, Any]) -> None:
    server["response"] = httpx.Response(
        429, json={"error": {"message": "Quota exceeded"}}
    )

    with pytest.raises(SpeechError, match="HTTP 429.*Quota exceeded") as caught:
        await _gemini().synthesize("hello")
    assert caught.value.status_code == 429


async def test_openai_speech_asks_for_mp3(server: dict[str, Any]) -> None:
    mp3 = b"ID3fake-mp3"
    server["response"] = httpx.Response(
        200, content=mp3, headers={"content-type": "audio/mpeg"}
    )
    service = OpenAISpeechService(
        model=OPENAI.models["speech"], api_key="sk-key", base_url=OPENAI.base_url
    )

    assert await service.synthesize("hello") == mp3

    request = server["requests"][0]
    assert str(request.url) == "https://api.openai.com/v1/audio/speech"
    assert request.headers["authorization"] == "Bearer sk-key"
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o-mini-tts"
    assert body["response_format"] == "mp3"
    assert body["voice"] in speech.OPENAI_VOICES


def test_audio_to_mp3_rejects_unknown_formats() -> None:
    with pytest.raises(ValueError, match="audio/ogg"):
        audio_to_mp3(b"OggS", "audio/ogg")


# ---- building from the speech route ---------------------------------------


@pytest.mark.parametrize(
    ("vendor", "expected"),
    [
        ("Gemini", GeminiSpeechService),
        ("OpenAI", OpenAISpeechService),
        ("Custom / Other", OpenAISpeechService),
        ("Google Cloud TTS", GoogleTTSService),
    ],
)
def test_build_speech_service_by_vendor(vendor: str, expected: type) -> None:
    profile = ProviderProfile(vendor, "model", "https://example.test/v1", "key")

    assert isinstance(build_speech_service(profile, Language.JAPANESE), expected)


def test_google_cloud_tts_uses_the_profile_key_and_language() -> None:
    profile = ProviderProfile("Google Cloud TTS", "Neural2", "", "gcloud-key")

    service = build_speech_service(profile, Language.JAPANESE)

    assert isinstance(service, GoogleTTSService)
    assert service._api_key == "gcloud-key"
    assert service._lang_code == "ja-JP"
    assert service._model == "Neural2"


def test_text_only_vendor_has_no_speech() -> None:
    with pytest.raises(ValueError, match="Anthropic has no speech"):
        build_speech_service(ProviderProfile("Anthropic"), Language.ENGLISH)


def test_speech_service_follows_the_active_speech_route() -> None:
    settings = Settings()
    settings.speech_providers = {
        "Gemini": ProviderProfile(
            "Gemini", GEMINI.models["speech"], GEMINI.base_url, "AIza", "gemini"
        )
    }
    settings.active_speech_provider = "Gemini"

    assert isinstance(
        speech_service_for(settings, Language.ENGLISH), GeminiSpeechService
    )


def test_without_a_speech_route_falls_back_to_google_cloud_tts() -> None:
    assert isinstance(
        speech_service_for(Settings(), Language.ENGLISH), GoogleTTSService
    )
