import asyncio
import random
from typing import Protocol, Self

from google.api_core.client_options import ClientOptions
from google.cloud.texttospeech import (
    AudioConfig,
    AudioEncoding,
    SynthesisInput,
    TextToSpeechAsyncClient,
    VoiceSelectionParams,
)

from ankinote.config import envs
from ankinote.consts import Language

TTS_LANG_CODES: dict[Language, str] = {
    Language.ENGLISH: "en-US",
    Language.JAPANESE: "ja-JP",
    Language.CHINESE_S: "cmn-CN",
    Language.CHINESE_T: "cmn-TW",
    Language.FRENCH: "fr-FR",
    Language.SPANISH: "es-ES",
    Language.GERMAN: "de-DE",
    Language.KOREAN: "ko-KR",
}
REQUEST_TIMEOUT_SECONDS = 60


class SpeechSynthesizer(Protocol):
    """Narrow speech synthesis contract used by generators."""

    async def synthesize(self, text: str) -> bytes:
        """Generate speech audio for plain text."""
        ...
class GoogleTTSService:
    def __init__(self, language_code: str = "en-US", model: str = "Neural2"):
        """
        Initialize the Google TTS service with the specified language and model.

        Args:
            language_code: BCP-47 language tag (e.g. "en-US", "ja-JP").
            model: Voice model family to filter by (e.g. "Neural2", "Wavenet").
        """
        self._tts_cli: TextToSpeechAsyncClient | None = None
        self._lang_code = language_code
        self._model = model
        self._available_voices: list[str] = []

    async def __aenter__(self) -> Self:
        """
        Async context manager entry. Pre-fetches and caches the list of
        available voices so that subsequent calls to synthesize are fast.
        """
        await self.warmup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit. Reserved for future cleanup logic."""
        self.clear_cache()

    async def warmup(self) -> None:
        """Prime the voice cache so the first synthesis call is faster."""
        self._available_voices = await self._get_all_voices()

    def clear_cache(self) -> None:
        """Reset the cached voice list."""
        self._available_voices = []

    async def _get_all_voices(self) -> list[str]:
        """
        Fetch and return all voice names that match the configured language
        code and model family.  Results are cached on the instance so the API
        is called at most once per service lifetime.

        Returns:
            A list of voice name strings (e.g. ["en-US-Neural2-A", ...]).
        """
        if self._available_voices:
            return self._available_voices

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self._get_client().list_voices(
                    language_code=self._lang_code
                )
        except TimeoutError as exc:
            raise RuntimeError(
                f"TTS voice lookup timed out after {REQUEST_TIMEOUT_SECONDS} seconds"
            ) from exc
        for voice in response.voices:
            if self._model in voice.name:
                self._available_voices.append(voice.name)

        return self._available_voices

    def _get_client(self) -> TextToSpeechAsyncClient:
        """Create the Google client only when text-to-speech is actually used."""
        if self._tts_cli is None:
            client_options = ClientOptions(api_key=envs.GOOGLE_TTS_KEY)
            self._tts_cli = TextToSpeechAsyncClient(client_options=client_options)
        return self._tts_cli

    async def synthesize_with_random_voice(
        self,
        text: str,
        audio_encoding = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> bytes:
        """
        Synthesize *text* using a voice chosen at random from the available
        voices that match the configured language and model.

        The voice list is populated lazily when the service is used as an async
        context manager (``async with``).  If the service is used without a
        context manager, the list is populated on the first call to this method.

        Args:
            text:           The plain text to synthesize.
            audio_encoding: Output audio format. Defaults to MP3.
                            Other options: LINEAR16, OGG_OPUS, MULAW, ALAW.
            speaking_rate:  Playback speed multiplier in the range [0.25, 4.0].
                            1.0 is normal speed.
            pitch:          Pitch shift in semitones, in the range [-20.0, 20.0].
                            0.0 is the default pitch.

        Returns:
            raw audio content

        Raises:
            RuntimeError: If no voices are available for the configured
                          language code and model family.
        """
        if audio_encoding is None:
            audio_encoding = AudioEncoding.MP3

        # Populate the voice list if this method is called outside a context manager.
        if not self._available_voices:
            await self._get_all_voices()

        if not self._available_voices:
            raise RuntimeError(
                f"No voices found for language '{self._lang_code}' "
                f"and model '{self._model}'."
            )

        voice_name = random.choice(self._available_voices)

        synthesis_input = SynthesisInput(text=text)

        voice_params = VoiceSelectionParams(
            language_code=self._lang_code,
            name=voice_name,
        )

        audio_config = AudioConfig(
            audio_encoding=audio_encoding,
            speaking_rate=speaking_rate,
            pitch=pitch,
        )

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self._get_client().synthesize_speech(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config,
                )
        except TimeoutError as exc:
            raise RuntimeError(
                f"Text-to-speech request timed out after {REQUEST_TIMEOUT_SECONDS} seconds"
            ) from exc

        return response.audio_content

    async def synthesize(self, text: str) -> bytes:
        """Generate speech audio using a random matching voice."""
        return await self.synthesize_with_random_voice(text)
