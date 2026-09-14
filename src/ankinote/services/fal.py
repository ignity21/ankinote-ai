"""Fal image generation using model endpoints directly."""

import asyncio
import os
from typing import cast

import httpx

from ankinote.services.ai import (
    IMAGE_GENERATION_TIMEOUT_SECONDS,
    GenerationTimeoutError,
)
from ankinote.utils.img import resize_to_max_edge


class FalImageService:
    """Generate images through Fal's synchronous HTTP API."""

    def __init__(
        self,
        *,
        model: str,
        image_size: int,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        endpoint = model.removeprefix("fal_ai/")
        if endpoint in {"flux/schnell", "flux-schnell"}:
            endpoint = "fal-ai/flux/schnell"
        # Accept the short Z-Image name as well as full Fal endpoint IDs.
        if endpoint.startswith("z-image/"):
            endpoint = f"fal-ai/{endpoint}"
        self._url = f"{(api_base or 'https://fal.run').rstrip('/')}/{endpoint}"
        self._api_key = api_key or os.getenv("FAL_AI_API_KEY")
        self._image_size = image_size

    async def generate_image(self, *, prompt: str) -> bytes:
        """Generate an image, download it, and resize it for the card."""
        if not self._api_key:
            raise ValueError("Fal image generation requires an API key")
        try:
            async with asyncio.timeout(IMAGE_GENERATION_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(
                    timeout=IMAGE_GENERATION_TIMEOUT_SECONDS
                ) as client:
                    response = await client.post(
                        self._url,
                        headers={"Authorization": f"Key {self._api_key}"},
                        json={"prompt": prompt},
                    )
                    response.raise_for_status()
                    payload = cast(dict[str, object], response.json())
                    images = payload.get("images")
                    if not isinstance(images, list) or not images:
                        raise RuntimeError("Fal image generation returned no images")
                    first = images[0]
                    url = (
                        cast(dict[str, object], first).get("url")
                        if isinstance(first, dict)
                        else first
                    )
                    if not isinstance(url, str) or not url:
                        raise RuntimeError("Fal image generation returned no image URL")
                    image = await client.get(url)
                    image.raise_for_status()
        except TimeoutError as exc:
            raise GenerationTimeoutError(
                "Image generation", IMAGE_GENERATION_TIMEOUT_SECONDS
            ) from exc
        return resize_to_max_edge(image.content, self._image_size)
