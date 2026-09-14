"""Shared AI configuration and provider-backed generation services."""

import asyncio
import base64
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, cast

import httpx
from litellm import acompletion, aimage_generation

from ankinote.utils.img import resize_to_max_edge

TextMessageContent = str | list[dict[str, object]]
TextMessage = dict[str, TextMessageContent]
TEXT_GENERATION_TIMEOUT_SECONDS = 60
IMAGE_GENERATION_TIMEOUT_SECONDS = 180


class GenerationTimeoutError(RuntimeError):
    """A generation request exceeded its operation-specific timeout."""

    def __init__(self, operation: str, timeout_seconds: int) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{operation} timed out after {timeout_seconds} seconds")


# Sentinel ``reasoning_effort`` value that turns a model's extended "thinking"
# pass off.  Language card types produce short, tightly-specified JSON where
# that pass adds little but costs tokens and latency (and DeepSeek, our default
# provider, silently ignores ``temperature`` while it is on).  DeepSeek enables
# thinking by default; it is disabled through the OpenAI-format ``thinking``
# field rather than ``reasoning_effort``, which LiteLLM's DeepSeek routing drops.
# https://api-docs.deepseek.com/guides/thinking_mode
DISABLE_REASONING = "none"

# Values accepted by callers that expose a "thinking" choice (the ``--thinking``
# CLI option and the STEM generation page).  ``off`` disables the model's
# extended-thinking pass, ``default`` uses the provider default, and the named
# levels are forwarded as ``reasoning_effort``.
THINKING_CHOICES = ("off", "low", "medium", "high", "default")


def resolve_thinking(choice: str | None, *, unset: str | None) -> str | None:
    """Map a "thinking" choice to a ``reasoning_effort`` value.

    ``choice is None`` means no choice was made; the caller's built-in default
    (*unset*) applies. ``"off"`` disables extended thinking, ``"default"``
    requests the provider default, and any other value passes straight through.
    """
    if choice is None:
        return unset
    if choice == "off":
        return DISABLE_REASONING
    if choice == "default":
        return None
    return choice


@dataclass(frozen=True, slots=True)
class AIServiceConfig:
    """Centralized default AI configuration."""

    text_model: str = "gpt-5.6-luna"
    image_model: str = "gpt-image-1.5"
    image_size: int = 512
    image_quality: str = "low"


@dataclass(frozen=True, slots=True)
class AIServiceConfigOverrides:
    """Optional AI configuration overrides from the CLI layer."""

    text_model: str | None = None
    image_model: str | None = None
    image_size: int | None = None

    def resolve(self, defaults: AIServiceConfig) -> AIServiceConfig:
        """Merge overrides onto the provided defaults."""
        config = defaults
        if self.text_model is not None:
            config = replace(config, text_model=self.text_model)
        if self.image_model is not None:
            config = replace(config, image_model=self.image_model)
        if self.image_size is not None:
            config = replace(config, image_size=self.image_size)
        return config


DEFAULT_AI_SERVICE_CONFIG = AIServiceConfig()


class TextGenerationService(Protocol):
    """Text generation service abstraction."""

    async def generate_text(
        self,
        *,
        model: str,
        messages: Sequence[TextMessage],
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        """Generate a text response from chat messages.

        ``reasoning_effort`` is forwarded to the provider when set; use
        :data:`DISABLE_REASONING` to turn extended thinking off.
        """
        ...


class ImageGenerationService(Protocol):
    """Image generation service abstraction."""

    async def generate_image(self, *, prompt: str) -> bytes:
        """Generate image bytes from a prompt."""
        ...


class LiteLLMTextService:
    """LiteLLM-backed text generation service."""

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        force_openai_route: bool = False,
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._force_openai_route = force_openai_route

    def _resolve_model(self, model: str) -> str:
        """Tell LiteLLM which provider owns models on a custom endpoint.

        LiteLLM infers a provider from an unqualified model id.  For model
        names such as ``Qwen/...`` that inference can select Hugging Face even
        when ``api_base`` points at an OpenAI-compatible server.  The
        ``openai/`` prefix makes the intended routing explicit.  An existing
        ``openai/`` prefix is left unchanged.

        Only forced when the caller flags the endpoint as genuinely custom
        (``force_openai_route``) — a known vendor's model id (e.g.
        ``gemini/...``, or an Anthropic id with no prefix at all) already
        routes correctly and must not be rewritten just because ``api_base``
        happens to be set too.
        """
        if (
            self._force_openai_route
            and self._api_base is not None
            and not model.startswith("openai/")
        ):
            return f"openai/{model}"
        return model

    async def generate_text(
        self,
        *,
        model: str,
        messages: Sequence[TextMessage],
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> str:
        """Generate text content using LiteLLM chat completion."""
        completion_kwargs: dict[str, object] = {
            "model": self._resolve_model(model),
            "messages": list(messages),
            "stream": False,
            "temperature": temperature,
            "drop_params": True,
            "timeout": TEXT_GENERATION_TIMEOUT_SECONDS,
            "num_retries": 0,
        }
        if reasoning_effort == DISABLE_REASONING:
            # DeepSeek honours the OpenAI-format ``thinking`` field, not
            # ``reasoning_effort`` (which its LiteLLM routing discards).  Other
            # OpenAI-compatible servers ignore the unknown field.
            completion_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif reasoning_effort is not None:
            completion_kwargs["reasoning_effort"] = reasoning_effort
        if self._api_base is not None:
            completion_kwargs["api_base"] = self._api_base
        if self._api_key is not None:
            completion_kwargs["api_key"] = self._api_key

        try:
            async with asyncio.timeout(TEXT_GENERATION_TIMEOUT_SECONDS):
                response = await acompletion(**completion_kwargs)  # type: ignore[arg-type]
        except TimeoutError as exc:
            raise GenerationTimeoutError(
                "Card content generation", TEXT_GENERATION_TIMEOUT_SECONDS
            ) from exc
        content = response.choices[0].message.content  # pyright: ignore[reportAttributeAccessIssue]
        if not isinstance(content, str):
            raise RuntimeError("AI returned non-string content")  # noqa: TRY004
        return content


class LiteLLMImageService:
    """LiteLLM-backed image generation service.

    Works with any provider LiteLLM routes through its OpenAI-compatible
    ``image_generation`` surface (Gemini, OpenAI, xAI, Vertex, Bedrock, …);
    the provider is selected by ``model``.
    """

    def __init__(
        self,
        *,
        model: str,
        image_size: int,
        image_quality: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        force_openai_route: bool = False,
    ) -> None:
        self._model = model
        self._image_size = image_size
        self._image_quality = image_quality
        self._api_key = api_key
        self._api_base = api_base
        self._force_openai_route = force_openai_route

    def _resolve_model(self, model: str) -> str:
        """Tell LiteLLM which provider owns models on a custom endpoint.

        See :meth:`LiteLLMTextService._resolve_model` — same reasoning,
        forced only for endpoints the caller flags as genuinely custom.
        """
        if (
            self._force_openai_route
            and self._api_base is not None
            and not model.startswith("openai/")
        ):
            return f"openai/{model}"
        return model

    async def generate_image(self, *, prompt: str) -> bytes:
        """Generate resized image bytes from a prompt."""
        image_kwargs: dict[str, object] = {
            "model": self._resolve_model(self._model),
            "prompt": prompt,
            "timeout": IMAGE_GENERATION_TIMEOUT_SECONDS,
            "num_retries": 0,
        }
        if self._api_base is not None:
            image_kwargs["api_base"] = self._api_base
        if self._api_key is not None:
            image_kwargs["api_key"] = self._api_key
        if self._image_quality is not None:
            image_kwargs["quality"] = self._image_quality
        try:
            async with asyncio.timeout(IMAGE_GENERATION_TIMEOUT_SECONDS):
                response = await aimage_generation(**image_kwargs)  # type: ignore[arg-type]
        except TimeoutError as exc:
            raise GenerationTimeoutError(
                "Image generation", IMAGE_GENERATION_TIMEOUT_SECONDS
            ) from exc
        data = cast(object, response.data[0])  # pyright: ignore[reportOptionalSubscript]
        b64 = getattr(data, "b64_json", None)
        if isinstance(b64, str):
            raw = base64.b64decode(b64)
        else:
            url = getattr(data, "url", None)
            if not isinstance(url, str):
                raise RuntimeError(  # noqa: TRY004
                    "Image generation returned neither a base64 payload nor a URL"
                )
            raw = await self._fetch_image_url(url)
        return resize_to_max_edge(raw, self._image_size)

    async def _fetch_image_url(self, url: str) -> bytes:
        """Download image bytes from a provider-hosted URL.

        Some providers (fal.ai, ``dall-e-3`` in its default mode) return a
        hosted URL instead of inline base64 data.
        """
        async with httpx.AsyncClient(
            timeout=IMAGE_GENERATION_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


__all__ = [
    "DEFAULT_AI_SERVICE_CONFIG",
    "DISABLE_REASONING",
    "IMAGE_GENERATION_TIMEOUT_SECONDS",
    "TEXT_GENERATION_TIMEOUT_SECONDS",
    "THINKING_CHOICES",
    "AIServiceConfig",
    "AIServiceConfigOverrides",
    "GenerationTimeoutError",
    "ImageGenerationService",
    "LiteLLMImageService",
    "LiteLLMTextService",
    "TextGenerationService",
    "TextMessage",
    "TextMessageContent",
    "resolve_thinking",
]
