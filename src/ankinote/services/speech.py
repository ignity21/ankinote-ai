"""Speech from Gemini and OpenAI-style ``/audio/speech`` endpoints.

Cards store audio as MP3. OpenAI returns MP3 directly; Gemini returns 16-bit
PCM (bare or wrapped in WAV), which is encoded to MP3 here.
"""

import asyncio
import base64
import io
import random
import re
import wave
from typing import Any

import httpx
import lameenc

from ankinote.services.ai import GenerationTimeoutError

REQUEST_TIMEOUT_SECONDS = 60
_ERROR_BODY_LIMIT = 300

# Gemini's prebuilt voices; each one speaks every supported language.
GEMINI_VOICES = (
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
)  # fmt: skip
OPENAI_VOICES = ("alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage")
_PCM_RATE = 24_000


class SpeechError(RuntimeError):
    """The provider refused or failed a speech request."""

    def __init__(self, provider: str, response: httpx.Response) -> None:
        self.status_code = response.status_code
        body = " ".join(response.text.split())[:_ERROR_BODY_LIMIT]
        super().__init__(
            f"{provider} speech failed (HTTP {response.status_code}): {body}"
        )


def encode_mp3(pcm: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    """Encode 16-bit little-endian PCM as MP3."""
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm) + encoder.flush())


def audio_to_mp3(data: bytes, mime_type: str) -> bytes:
    """Turn what a speech API returned into MP3 bytes."""
    mime = mime_type.lower()
    if "mp3" in mime or "mpeg" in mime or data[:3] == b"ID3":
        return data
    if "wav" in mime or data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as wav:
            if wav.getsampwidth() != 2:
                raise ValueError(f"Unsupported WAV sample width {wav.getsampwidth()}")
            pcm = wav.readframes(wav.getnframes())
            return encode_mp3(
                pcm, sample_rate=wav.getframerate(), channels=wav.getnchannels()
            )
    if "l16" in mime or "pcm" in mime:
        rate = re.search(r"rate=(\d+)", mime)
        return encode_mp3(data, sample_rate=int(rate.group(1)) if rate else _PCM_RATE)
    raise ValueError(f"Unsupported speech audio format {mime_type!r}")


def _find_audio(node: Any) -> tuple[str, str] | None:
    """Find the first base64 audio item and its MIME type in a response.

    Accepts the Interactions API shape (``{"type": "audio", "data": …,
    "mime_type": …}`` inside ``steps``) and the older ``generateContent``
    shape (``{"inlineData": {"mimeType": …, "data": …}}``).
    """
    if isinstance(node, dict):
        mime = node.get("mime_type") or node.get("mimeType") or ""
        data = node.get("data")
        if isinstance(data, str) and (
            node.get("type") == "audio" or mime.startswith("audio")
        ):
            return data, mime
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find_audio(child)
        if found:
            return found
    return None


class _HttpSpeech:
    """Shared plumbing: no voice cache to warm, one request per synthesis."""

    provider = ""

    async def warmup(self) -> None:
        """Nothing to prefetch."""

    def clear_cache(self) -> None:
        """Nothing cached."""

    async def _post(
        self, url: str, *, headers: dict[str, str], body: dict
    ) -> httpx.Response:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    response = await client.post(url, headers=headers, json=body)
        except TimeoutError as exc:
            raise GenerationTimeoutError(
                "Speech generation", REQUEST_TIMEOUT_SECONDS
            ) from exc
        if response.is_error:
            raise SpeechError(self.provider, response)
        return response


class GeminiSpeechService(_HttpSpeech):
    """Gemini TTS through the Interactions API, with a random voice per clip."""

    provider = "Gemini"

    def __init__(self, *, model: str, api_key: str, base_url: str) -> None:
        self._model = model.removeprefix("gemini/")
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/interactions"

    async def synthesize(self, text: str) -> bytes:
        """Speak ``text``; the model detects its language."""
        body = {
            "model": self._model,
            "input": [
                {"type": "user_input", "content": [{"type": "text", "text": text}]}
            ],
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [{"voice": random.choice(GEMINI_VOICES)}]
            },
            "store": False,
        }
        response = await self._post(
            self._url, headers={"x-goog-api-key": self._api_key}, body=body
        )
        found = _find_audio(response.json())
        if found is None:
            raise RuntimeError("Gemini speech returned no audio")
        data, mime = found
        return audio_to_mp3(base64.b64decode(data), mime)


class OpenAISpeechService(_HttpSpeech):
    """OpenAI's ``/audio/speech``, or any server that copies it."""

    provider = "OpenAI"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        voices: tuple[str, ...] = OPENAI_VOICES,
    ) -> None:
        self._model = model.removeprefix("openai/")
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/audio/speech"
        self._voices = voices

    async def synthesize(self, text: str) -> bytes:
        """Speak ``text`` as MP3 in a random voice."""
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body = {
            "model": self._model,
            "input": text,
            "voice": random.choice(self._voices),
            "response_format": "mp3",
        }
        response = await self._post(self._url, headers=headers, body=body)
        return audio_to_mp3(response.content, response.headers.get("content-type", ""))
