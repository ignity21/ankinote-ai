"""Provider presets: one pasted key fills the text, image and speech routes.

The wizard recommends Gemini: one AI Studio key serves all three routes. The
other presets are offered under "Advanced", per route, matching what 0.x
offered (plus DeepSeek and the OpenAI/Gemini speech models).

Recommended models are the cheapest that make a good card. The ids are
release data, checked against each provider's model page on 2026-11-13. A saved route whose profile names a preset (see
``ProviderProfile.preset``) follows that preset's model on every load, so an
upgrade moves users who never edited the route to the new recommended model.
Editing the model clears the marker and the route is left alone from then on.
"""

from dataclasses import dataclass, field
from typing import Literal

type Route = Literal["text", "image", "speech"]
ROUTES: tuple[Route, ...] = ("text", "image", "speech")

# Vendor of a user-supplied OpenAI-compatible endpoint (custom base URL and
# model id): a local server, a third-party API, or DeepSeek.
CUSTOM_VENDOR = "Custom / Other"
CUSTOM_PRESET = "custom"
# Google Cloud Text-to-Speech: its own API and key, unlike Gemini's speech
# models, which take the AI Studio key.
GOOGLE_TTS_VENDOR = "Google Cloud TTS"
FAL_VENDOR = "Fal"


@dataclass(frozen=True, slots=True)
class Preset:
    """One provider the wizard offers, with its recommended model per route.

    A route missing from ``models`` is one the provider cannot serve with the
    same key; the wizard says so up front.
    """

    id: str
    label: str
    vendor: str
    base_url: str
    litellm_provider: str
    model_prefix: str = ""
    models: dict[Route, str] = field(default_factory=dict)
    key_url: str = ""
    recommended: bool = False


PRESETS: dict[str, Preset] = {
    preset.id: preset
    for preset in (
        Preset(
            id="gemini",
            label="Gemini",
            vendor="Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            litellm_provider="gemini",
            model_prefix="gemini/",
            models={
                "text": "gemini/gemini-3.8-flash",
                "image": "gemini/gemini-3.1-flash-lite-image",
                "speech": "gemini/gemini-3.8-flash-lite-tts",
            },
            key_url="https://aistudio.google.com/apikey",
            recommended=True,
        ),
        Preset(
            id="openai",
            label="OpenAI",
            vendor="OpenAI",
            base_url="https://api.openai.com/v1",
            litellm_provider="openai",
            models={
                "text": "gpt-6-luna",
                # Same token price as sunburst; flare is the faster one.
                "image": "gpt-image-2.6-flare",
                # The only model /v1/audio/speech serves; OpenAI lists it as
                # deprecated with shutdown 2027-01-06 and no replacement yet.
                "speech": "gpt-4o-mini-tts",
            },
            key_url="https://platform.openai.com/api-keys",
        ),
        Preset(
            id="deepseek",
            label="DeepSeek",
            vendor=CUSTOM_VENDOR,
            base_url="https://api.deepseek.com",
            litellm_provider="openai",
            models={"text": "deepseek-flash"},
            key_url="https://platform.deepseek.com/api_keys",
        ),
        Preset(
            id="anthropic",
            label="Claude",
            vendor="Anthropic",
            base_url="https://api.anthropic.com/v1",
            litellm_provider="anthropic",
            models={"text": "claude-haiku-5-5"},
            key_url="https://console.anthropic.com/settings/keys",
        ),
        Preset(
            id="fal",
            label="FAL.AI",
            vendor=FAL_VENDOR,
            base_url="https://fal.run",
            litellm_provider="fal_ai",
            model_prefix="fal_ai/",
            models={"image": "fal_ai/fal-ai/flux/schnell"},
            key_url="https://fal.ai/dashboard/keys",
        ),
        Preset(
            id="google_tts",
            label="Google Cloud TTS",
            vendor=GOOGLE_TTS_VENDOR,
            base_url="https://texttospeech.googleapis.com/v1",
            litellm_provider="",
            # A voice family; each synthesis picks a random voice in it.
            models={"speech": "Chirp3-HD"},
            key_url="https://console.cloud.google.com/apis/library/texttospeech.googleapis.com",
        ),
        Preset(
            id=CUSTOM_PRESET,
            label="OpenAI-compatible",
            vendor=CUSTOM_VENDOR,
            base_url="",
            litellm_provider="openai",
        ),
    )
}


def get_preset(preset_id: str) -> Preset:
    """Return a preset by id; raise ``KeyError`` for an unknown one."""
    return PRESETS[preset_id]


def preset_for(vendor: str, base_url: str) -> Preset:
    """Find the preset a saved profile belongs to.

    Profiles saved by 0.x carry no preset id, so match by vendor, and for
    OpenAI-compatible endpoints by base URL (DeepSeek is one of those).
    """
    base = base_url.rstrip("/")
    for preset in PRESETS.values():
        if preset.id == CUSTOM_PRESET:
            continue
        if preset.vendor == vendor and (
            vendor != CUSTOM_VENDOR or preset.base_url.rstrip("/") == base
        ):
            return preset
    return PRESETS[CUSTOM_PRESET]
