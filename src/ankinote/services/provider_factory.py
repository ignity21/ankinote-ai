"""Build AI services from provider profiles, shared by the CLI and GUI."""

from ankinote.consts import Language
from ankinote.model_presets import FAL_VENDOR, GOOGLE_TTS_VENDOR
from ankinote.services.ai import (
    ImageGenerationService,
    LiteLLMImageService,
    LiteLLMTextService,
)
from ankinote.services.fal import FalImageService
from ankinote.services.speech import GeminiSpeechService, OpenAISpeechService
from ankinote.services.tts import TTS_LANG_CODES, GoogleTTSService, SpeechService
from ankinote.settings import CUSTOM_VENDOR, ProviderProfile, Settings, active_profile


def _completion_base(profile: ProviderProfile) -> str | None:
    """The ``api_base`` LiteLLM expects for chat completions.

    Stored Anthropic bases end in ``/v1`` (the model-list endpoint needs it),
    but LiteLLM appends ``/v1/messages`` itself.
    """
    base = profile.base_url.rstrip("/")
    if profile.vendor == "Anthropic":
        base = base.removesuffix("/v1")
    return base or None


def build_text_service(profile: ProviderProfile) -> LiteLLMTextService:
    """Assemble a text service from the active text provider profile."""
    return LiteLLMTextService(
        api_base=_completion_base(profile),
        api_key=profile.api_key or None,
        force_openai_route=profile.vendor == CUSTOM_VENDOR,
    )


def build_image_service(
    profile: ProviderProfile, *, image_size: int, model: str | None = None
) -> ImageGenerationService:
    """Use the selected profile and optional page-specific model override."""
    selected_model = model or profile.model
    if profile.vendor == FAL_VENDOR:
        return FalImageService(
            model=selected_model,
            image_size=image_size,
            api_key=profile.api_key or None,
            api_base=profile.base_url or None,
        )
    return LiteLLMImageService(
        model=selected_model,
        image_size=image_size,
        api_key=profile.api_key or None,
        api_base=profile.base_url or None,
        force_openai_route=profile.vendor == CUSTOM_VENDOR,
    )


def build_speech_service(profile: ProviderProfile, language: Language) -> SpeechService:
    """Assemble a speech service from a speech-route profile."""
    match profile.vendor:
        case "Gemini":
            return GeminiSpeechService(
                model=profile.model, api_key=profile.api_key, base_url=profile.base_url
            )
        case "OpenAI":
            return OpenAISpeechService(
                model=profile.model, api_key=profile.api_key, base_url=profile.base_url
            )
        case vendor if vendor == CUSTOM_VENDOR:
            # Self-hosted /audio/speech servers rarely know OpenAI's voice names.
            return OpenAISpeechService(
                model=profile.model,
                api_key=profile.api_key,
                base_url=profile.base_url,
                voices=("alloy",),
            )
        case vendor if vendor == GOOGLE_TTS_VENDOR:
            return GoogleTTSService(
                TTS_LANG_CODES[language],
                model=profile.model or "Chirp3-HD",
                api_key=profile.api_key or None,
            )
        case vendor:
            raise ValueError(f"{vendor or 'This provider'} has no speech models")


def speech_service_for(settings: Settings, language: Language) -> SpeechService:
    """The speech service for the active speech route.

    Without one, fall back to Google Cloud TTS with ``GOOGLE_TTS_KEY``, as
    0.x did.
    """
    profile = active_profile(settings, "speech")
    if profile is None:
        return GoogleTTSService(TTS_LANG_CODES[language])
    return build_speech_service(profile, language)
