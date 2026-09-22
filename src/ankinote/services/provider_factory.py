"""Build AI services from provider profiles, shared by the CLI and GUI."""

from ankinote.services.ai import (
    ImageGenerationService,
    LiteLLMImageService,
    LiteLLMTextService,
)
from ankinote.services.fal import FalImageService
from ankinote.settings import CUSTOM_VENDOR, ProviderProfile


def build_text_service(profile: ProviderProfile) -> LiteLLMTextService:
    """Assemble a text service from the active text provider profile."""
    return LiteLLMTextService(
        api_base=profile.base_url or None,
        api_key=profile.api_key or None,
        force_openai_route=profile.vendor == CUSTOM_VENDOR,
    )


def build_image_service(
    profile: ProviderProfile, *, image_size: int, model: str | None = None
) -> ImageGenerationService:
    """Use the selected profile and optional page-specific model override."""
    selected_model = model or profile.model
    if profile.vendor == "Fal":
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
