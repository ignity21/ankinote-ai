"""Tests for the shared AI service layer."""

import io
from types import SimpleNamespace

import pytest
from PIL import Image
from pytest_mock import MockerFixture

from ankinote.services.ai import (
    DISABLE_REASONING,
    IMAGE_GENERATION_TIMEOUT_SECONDS,
    TEXT_GENERATION_TIMEOUT_SECONDS,
    THINKING_CHOICES,
    GenerationTimeoutError,
    LiteLLMImageService,
    LiteLLMTextService,
    resolve_thinking,
)


def test_resolve_thinking_maps_choices() -> None:
    assert resolve_thinking(None, unset=DISABLE_REASONING) == DISABLE_REASONING
    assert resolve_thinking(None, unset=None) is None
    assert resolve_thinking("off", unset=None) == DISABLE_REASONING
    assert resolve_thinking("default", unset=DISABLE_REASONING) is None
    assert resolve_thinking("high", unset=None) == "high"
    assert set(THINKING_CHOICES) == {"off", "low", "medium", "high", "default"}


@pytest.mark.asyncio
async def test_litellm_text_service_forwards_completion_args(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok": true}'),
                )
            ]
        ),
    )

    service = LiteLLMTextService()
    result = await service.generate_text(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert result == '{"ok": true}'
    completion.assert_awaited_once_with(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        temperature=0.2,
        drop_params=True,
        timeout=TEXT_GENERATION_TIMEOUT_SECONDS,
        num_retries=0,
    )


@pytest.mark.asyncio
async def test_litellm_text_service_disables_deepseek_thinking(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService()
    await service.generate_text(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        reasoning_effort=DISABLE_REASONING,
    )

    kwargs = completion.await_args.kwargs
    # DeepSeek discards ``reasoning_effort``; the OpenAI-format ``thinking``
    # field in ``extra_body`` is what turns its default-on thinking off.
    assert "reasoning_effort" not in kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_litellm_text_service_omits_thinking_field_for_openai(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService()
    await service.generate_text(
        model="gpt-5.6-luna",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        reasoning_effort=DISABLE_REASONING,
    )

    kwargs = completion.await_args.kwargs
    # OpenAI's API rejects the DeepSeek-only ``thinking`` field with
    # "Unknown parameter: 'thinking'".
    assert "extra_body" not in kwargs
    assert "reasoning_effort" not in kwargs


@pytest.mark.asyncio
async def test_litellm_text_service_forwards_named_reasoning_effort(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService()
    await service.generate_text(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        reasoning_effort="high",
    )

    kwargs = completion.await_args.kwargs
    assert kwargs["reasoning_effort"] == "high"
    assert "extra_body" not in kwargs


@pytest.mark.asyncio
async def test_litellm_text_service_omits_reasoning_effort_when_unset(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService()
    await service.generate_text(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert "reasoning_effort" not in completion.await_args.kwargs
    assert "extra_body" not in completion.await_args.kwargs


@pytest.mark.asyncio
async def test_litellm_text_service_routes_custom_endpoint_through_openai(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        force_openai_route=True,
    )
    await service.generate_text(
        model="Qwen/Qwen3-8B",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    completion.assert_awaited_once_with(
        model="openai/Qwen/Qwen3-8B",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        temperature=0.2,
        drop_params=True,
        timeout=TEXT_GENERATION_TIMEOUT_SECONDS,
        num_retries=0,
        api_base="http://localhost:8000/v1",
        api_key="test-key",
    )


@pytest.mark.asyncio
async def test_litellm_text_service_keeps_explicit_openai_prefix(
    mocker: MockerFixture,
):
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService(
        api_base="http://localhost:8000/v1", force_openai_route=True
    )
    await service.generate_text(
        model="openai/my-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert completion.await_args.kwargs["model"] == "openai/my-model"


@pytest.mark.asyncio
async def test_litellm_text_service_does_not_prefix_known_vendors_by_default(
    mocker: MockerFixture,
):
    """A known-vendor profile now also carries an explicit ``api_base`` (so
    multiple accounts of the same vendor can coexist), but that must not
    trigger the custom-endpoint ``openai/`` prefix forcing — only a profile
    explicitly flagged ``force_openai_route`` (i.e. vendor == CUSTOM_VENDOR)
    should get it."""
    completion = mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    )

    service = LiteLLMTextService(
        api_base="https://api.anthropic.com/v1", api_key="sk-a"
    )
    await service.generate_text(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert completion.await_args.kwargs["model"] == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_litellm_text_service_rejects_non_string_content(
    mocker: MockerFixture,
):
    mocker.patch(
        "ankinote.services.ai.acompletion",
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        ),
    )

    service = LiteLLMTextService()

    with pytest.raises(RuntimeError, match="non-string"):
        await service.generate_text(
            model="deepseek/deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
        )


@pytest.mark.asyncio
async def test_litellm_image_service_decodes_and_resizes(
    mocker: MockerFixture,
):
    image = Image.new("RGB", (80, 40), color=(10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    image_generation = mocker.patch(
        "ankinote.services.ai.aimage_generation",
        return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json=buffer.getvalue().hex())]
        ),
    )

    service = LiteLLMImageService(model="gemini/gemini-2.5-flash-image", image_size=128)
    mocker.patch(
        "ankinote.services.ai.base64.b64decode", return_value=buffer.getvalue()
    )
    result = await service.generate_image(prompt="draw a cat")

    with Image.open(io.BytesIO(result)) as out:
        assert out.size == (80, 40)
    image_generation.assert_awaited_once_with(
        model="gemini/gemini-2.5-flash-image",
        prompt="draw a cat",
        timeout=IMAGE_GENERATION_TIMEOUT_SECONDS,
        num_retries=0,
    )


@pytest.mark.asyncio
async def test_litellm_image_service_forwards_api_base_and_key(
    mocker: MockerFixture,
):
    """Every image profile now carries its own base URL/key explicitly, so
    multiple accounts of the same vendor can coexist (no env-var reliance)."""
    image_generation = mocker.patch(
        "ankinote.services.ai.aimage_generation",
        return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json="")],
        ),
    )
    mocker.patch("ankinote.services.ai.base64.b64decode", return_value=b"\x00")
    mocker.patch("ankinote.services.ai.resize_to_max_edge", return_value=b"resized")

    service = LiteLLMImageService(
        model="gemini/gemini-2.5-flash-image",
        image_size=128,
        api_key="sk-g",
        api_base="https://generativelanguage.googleapis.com/v1beta",
    )
    result = await service.generate_image(prompt="draw a cat")

    assert result == b"resized"
    image_generation.assert_awaited_once_with(
        model="gemini/gemini-2.5-flash-image",
        prompt="draw a cat",
        timeout=IMAGE_GENERATION_TIMEOUT_SECONDS,
        num_retries=0,
        api_base="https://generativelanguage.googleapis.com/v1beta",
        api_key="sk-g",
    )


@pytest.mark.asyncio
async def test_litellm_image_service_forces_openai_route_for_custom_vendor(
    mocker: MockerFixture,
):
    image_generation = mocker.patch(
        "ankinote.services.ai.aimage_generation",
        return_value=SimpleNamespace(data=[SimpleNamespace(b64_json="")]),
    )
    mocker.patch("ankinote.services.ai.base64.b64decode", return_value=b"\x00")
    mocker.patch("ankinote.services.ai.resize_to_max_edge", return_value=b"resized")

    service = LiteLLMImageService(
        model="my-diffusion-model",
        image_size=128,
        api_base="http://localhost:8000/v1",
        force_openai_route=True,
    )
    await service.generate_image(prompt="draw a cat")

    assert image_generation.await_args.kwargs["model"] == "openai/my-diffusion-model"


@pytest.mark.asyncio
async def test_litellm_image_service_fetches_url_when_no_b64_json(
    mocker: MockerFixture,
):
    """fal.ai (and dall-e-3 in its default mode) return a hosted URL instead
    of inline base64 data."""
    mocker.patch(
        "ankinote.services.ai.aimage_generation",
        return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="https://fal.media/files/foo.png")]
        ),
    )
    fetch_image_url = mocker.patch.object(
        LiteLLMImageService, "_fetch_image_url", return_value=b"\x00"
    )
    mocker.patch("ankinote.services.ai.resize_to_max_edge", return_value=b"resized")

    service = LiteLLMImageService(model="fal_ai/fal-ai/flux/schnell", image_size=128)
    result = await service.generate_image(prompt="draw a cat")

    assert result == b"resized"
    fetch_image_url.assert_awaited_once_with("https://fal.media/files/foo.png")


@pytest.mark.asyncio
async def test_litellm_image_service_raises_when_no_b64_or_url(
    mocker: MockerFixture,
):
    mocker.patch(
        "ankinote.services.ai.aimage_generation",
        return_value=SimpleNamespace(data=[SimpleNamespace(b64_json=None, url=None)]),
    )

    service = LiteLLMImageService(model="fal_ai/fal-ai/flux/schnell", image_size=128)

    with pytest.raises(RuntimeError, match="neither a base64 payload nor a URL"):
        await service.generate_image(prompt="draw a cat")


@pytest.mark.asyncio
async def test_litellm_text_service_reports_card_content_timeout(
    mocker: MockerFixture,
) -> None:
    async def timeout(**_: object) -> None:
        raise TimeoutError

    mocker.patch("ankinote.services.ai.acompletion", side_effect=timeout)
    service = LiteLLMTextService()

    with pytest.raises(
        GenerationTimeoutError,
        match="Card content generation timed out after 60 seconds",
    ):
        await service.generate_text(
            model="test",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
        )


@pytest.mark.asyncio
async def test_litellm_image_service_reports_its_180_second_timeout(
    mocker: MockerFixture,
) -> None:
    async def timeout(**_: object) -> None:
        raise TimeoutError

    mocker.patch("ankinote.services.ai.aimage_generation", side_effect=timeout)
    service = LiteLLMImageService(model="test", image_size=128)

    with pytest.raises(
        GenerationTimeoutError,
        match="Image generation timed out after 180 seconds",
    ):
        await service.generate_image(prompt="draw a cat")
