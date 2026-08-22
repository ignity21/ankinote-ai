"""Tests for the shared AI service layer."""

import io
from types import SimpleNamespace

import pytest
from PIL import Image
from pytest_mock import MockerFixture

from ankinote.services.ai import LiteLLMGeminiImageService, LiteLLMTextService


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
        model_id="deepseek/deepseek-v4-flash",
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
        timeout=60,
        num_retries=0,
    )


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
    )
    await service.generate_text(
        model_id="Qwen/Qwen3-8B",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    completion.assert_awaited_once_with(
        model="openai/Qwen/Qwen3-8B",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        temperature=0.2,
        drop_params=True,
        timeout=60,
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

    service = LiteLLMTextService(api_base="http://localhost:8000/v1")
    await service.generate_text(
        model_id="openai/my-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert completion.await_args.kwargs["model"] == "openai/my-model"


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
            model_id="deepseek/deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
        )


@pytest.mark.asyncio
async def test_litellm_gemini_image_service_decodes_and_resizes(
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

    service = LiteLLMGeminiImageService(
        model_id="gemini/gemini-2.5-flash-image", image_size=128
    )
    mocker.patch(
        "ankinote.services.ai.base64.b64decode", return_value=buffer.getvalue()
    )
    result = await service.generate_image(prompt="draw a cat")

    with Image.open(io.BytesIO(result)) as out:
        assert out.size == (80, 40)
    image_generation.assert_awaited_once_with(
        model="gemini/gemini-2.5-flash-image",
        prompt="draw a cat",
        timeout=60,
        num_retries=0,
    )
