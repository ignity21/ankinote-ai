"""Shared AI configuration and provider-backed generation services."""

import base64
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, cast

from litellm import acompletion, aimage_generation

from ankinote.utils.img import resize_to_max_edge

TextMessage = dict[str, str]
REQUEST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class AIServiceConfig:
    """Centralized default AI configuration."""

    text_model_id: str = "deepseek/deepseek-v4-flash"
    image_model_id: str = "gemini/gemini-3.1-flash-lite-image"
    image_size: int = 512


@dataclass(frozen=True, slots=True)
class AIServiceConfigOverrides:
    """Optional AI configuration overrides from the CLI layer."""

    text_model_id: str | None = None
    image_model_id: str | None = None
    image_size: int | None = None

    def resolve(self, defaults: AIServiceConfig) -> AIServiceConfig:
        """Merge overrides onto the provided defaults."""
        config = defaults
        if self.text_model_id is not None:
            config = replace(config, text_model_id=self.text_model_id)
        if self.image_model_id is not None:
            config = replace(config, image_model_id=self.image_model_id)
        if self.image_size is not None:
            config = replace(config, image_size=self.image_size)
        return config


DEFAULT_AI_SERVICE_CONFIG = AIServiceConfig()


class TextGenerationService(Protocol):
    """Text generation service abstraction."""

    async def generate_text(
        self,
        *,
        model_id: str,
        messages: Sequence[TextMessage],
        temperature: float,
    ) -> str:
        """Generate a text response from chat messages."""
        ...


class ImageGenerationService(Protocol):
    """Image generation service abstraction."""

    async def generate_image(self, *, prompt: str) -> bytes:
        """Generate image bytes from a prompt."""
        ...


class LiteLLMTextService:
    """LiteLLM-backed text generation service."""

    def __init__(self, *, api_base: str | None = None, api_key: str | None = None) -> None:
        self._api_base = api_base
        self._api_key = api_key

    def _resolve_model_id(self, model_id: str) -> str:
        """Tell LiteLLM which provider owns models on a custom endpoint.

        LiteLLM infers a provider from an unqualified model id.  For model
        names such as ``Qwen/...`` that inference can select Hugging Face even
        when ``api_base`` points at an OpenAI-compatible server.  The
        ``openai/`` prefix makes the intended routing explicit.  An existing
        ``openai/`` prefix is left unchanged.
        """
        if self._api_base is not None and not model_id.startswith("openai/"):
            return f"openai/{model_id}"
        return model_id

    async def generate_text(
        self,
        *,
        model_id: str,
        messages: Sequence[TextMessage],
        temperature: float,
    ) -> str:
        """Generate text content using LiteLLM chat completion."""
        completion_kwargs: dict[str, object] = {
            "model": self._resolve_model_id(model_id),
            "messages": list(messages),
            "stream": False,
            "temperature": temperature,
            "drop_params": True,
            "timeout": REQUEST_TIMEOUT_SECONDS,
            "num_retries": 0,
        }
        if self._api_base is not None:
            completion_kwargs["api_base"] = self._api_base
        if self._api_key is not None:
            completion_kwargs["api_key"] = self._api_key

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await acompletion(**completion_kwargs)
        except TimeoutError as exc:
            raise RuntimeError(
                f"Text generation timed out after {REQUEST_TIMEOUT_SECONDS} seconds"
            ) from exc
        content = response.choices[0].message.content  # pyright: ignore[reportAttributeAccessIssue]
        if not isinstance(content, str):
            raise RuntimeError("AI returned non-string content")
        return content


class LiteLLMGeminiImageService:
    """LiteLLM-backed Gemini image generation service."""

    def __init__(
        self, *, model_id: str, image_size: int, api_key: str | None = None
    ) -> None:
        self._model_id = model_id
        self._image_size = image_size
        self._api_key = api_key

    async def generate_image(self, *, prompt: str) -> bytes:
        """Generate resized image bytes from a prompt."""
        image_kwargs: dict[str, object] = {
            "model": self._model_id,
            "prompt": prompt,
            "timeout": REQUEST_TIMEOUT_SECONDS,
            "num_retries": 0,
        }
        if self._api_key is not None:
            image_kwargs["api_key"] = self._api_key
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await aimage_generation(**image_kwargs)
        except TimeoutError as exc:
            raise RuntimeError(
                f"Image generation timed out after {REQUEST_TIMEOUT_SECONDS} seconds"
            ) from exc
        data = cast(object, response.data[0])  # pyright: ignore[reportOptionalSubscript]
        b64 = getattr(data, "b64_json", None)
        if not isinstance(b64, str):
            raise RuntimeError("Image generation returned no base64 payload")
        raw = base64.b64decode(b64)
        return resize_to_max_edge(raw, self._image_size)


__all__ = [
    "AIServiceConfig",
    "AIServiceConfigOverrides",
    "DEFAULT_AI_SERVICE_CONFIG",
    "ImageGenerationService",
    "LiteLLMGeminiImageService",
    "LiteLLMTextService",
    "TextGenerationService",
    "TextMessage",
]
