"""Provider routing and Fal HTTP regression tests."""

import io
import json

import httpx
import pytest
from PIL import Image
from pytest_mock import MockerFixture

from ankinote.services.ai import (
    IMAGE_GENERATION_TIMEOUT_SECONDS,
    LiteLLMImageService,
    LiteLLMTextService,
)
from ankinote.services.provider_factory import build_image_service, build_text_service
from ankinote.settings import CUSTOM_VENDOR, PROVIDERS, ProviderProfile


@pytest.mark.parametrize(
    "model",
    ["z-image/turbo", "fal-ai/z-image/turbo", "fal_ai/fal-ai/z-image/turbo"],
)
async def test_fal_profile_generates_and_resizes_image(
    model: str, mocker: MockerFixture
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (1024, 768)).save(buffer, format="PNG")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert str(request.url) == "https://fal.run/fal-ai/z-image/turbo"
            assert request.headers["Authorization"] == "Key test-key"
            assert json.loads(request.content) == {"prompt": "解释一下微分"}
            return httpx.Response(
                200, json={"images": [{"url": "https://fal.media/image.png"}]}
            )
        assert str(request.url) == "https://fal.media/image.png"
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=buffer.getvalue())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client_factory = mocker.patch(
        "ankinote.services.fal.httpx.AsyncClient", return_value=client
    )
    litellm = mocker.patch("ankinote.services.ai.aimage_generation")
    service = build_image_service(
        ProviderProfile(
            vendor="Fal", model=model, base_url="https://fal.run", api_key="test-key"
        ),
        image_size=512,
    )
    result = await service.generate_image(prompt="解释一下微分")
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (512, 384)
    assert len(requests) == 2
    client_factory.assert_called_once_with(timeout=IMAGE_GENERATION_TIMEOUT_SECONDS)
    litellm.assert_not_called()


async def test_fal_model_override_and_empty_response(mocker: MockerFixture) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/fal-ai/z-image/turbo"
        return httpx.Response(200, json={"images": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    mocker.patch("ankinote.services.fal.httpx.AsyncClient", return_value=client)
    service = build_image_service(
        ProviderProfile(
            vendor="Fal",
            model="fal_ai/fal-ai/flux/schnell",
            base_url="https://example.test/",
            api_key="test-key",
        ),
        image_size=512,
        model="z-image/turbo",
    )
    with pytest.raises(RuntimeError, match="returned no images"):
        await service.generate_image(prompt="diagram")


@pytest.mark.parametrize("vendor", ["Gemini", "OpenAI", CUSTOM_VENDOR])
def test_other_image_vendors_keep_litellm_routing(vendor: str) -> None:
    service = build_image_service(
        ProviderProfile(
            vendor=vendor, model="test-model", base_url="https://example.test/v1"
        ),
        image_size=512,
    )
    assert isinstance(service, LiteLLMImageService)
    assert service._force_openai_route == (vendor == CUSTOM_VENDOR)


@pytest.mark.parametrize(
    "model, endpoint",
    [
        ("fal_ai/flux/schnell", "fal-ai/flux/schnell"),
        ("fal_ai/fal-ai/flux/schnell", "fal-ai/flux/schnell"),
        ("bria/text-to-image/3.2", "bria/text-to-image/3.2"),
    ],
)
async def test_fal_preserves_existing_endpoints_and_http_errors(
    model: str, endpoint: str, mocker: MockerFixture
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"https://fal.run/{endpoint}"
        return httpx.Response(401, json={"detail": "Invalid credentials"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    mocker.patch("ankinote.services.fal.httpx.AsyncClient", return_value=client)
    service = build_image_service(
        ProviderProfile(vendor="Fal", model=model, api_key="invalid"), image_size=512
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await service.generate_image(prompt="diagram")
    assert exc.value.response.status_code == 401


def test_build_text_service_passes_builtin_vendor_key_and_base_explicitly() -> None:
    """Every profile — not just custom ones — carries its own api_base/api_key
    explicitly now, so multiple accounts of the same vendor can coexist."""
    profile = ProviderProfile(
        vendor="OpenAI",
        model="gpt-4o",
        base_url=PROVIDERS["OpenAI"]["api_base"],
        api_key="sk-work",
    )
    service = build_text_service(profile)
    assert isinstance(service, LiteLLMTextService)
    assert service._api_base == PROVIDERS["OpenAI"]["api_base"]
    assert service._api_key == "sk-work"
    assert service._force_openai_route is False


def test_build_text_service_forces_openai_route_for_custom_vendor() -> None:
    profile = ProviderProfile(
        vendor=CUSTOM_VENDOR,
        base_url="https://example.test/v1",
        model="llama-3.1-70b",
        api_key="sk-abc",
    )
    service = build_text_service(profile)
    assert service._api_base == "https://example.test/v1"
    assert service._api_key == "sk-abc"
    assert service._force_openai_route is True


def test_build_text_service_falls_back_for_default_profile() -> None:
    service = build_text_service(ProviderProfile())
    assert service._api_base is None
    assert service._api_key is None
    assert service._force_openai_route is False
