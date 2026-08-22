"""Tests for the Google TTS service wrapper."""

import asyncio
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from ankinote.services.tts import GoogleTTSService


class TestGoogleTTSService:
    """Behavior tests for warmup and synthesis."""

    @pytest.mark.asyncio
    async def test_warmup_populates_matching_voices(self, mocker: MockerFixture):
        mock_client = SimpleNamespace(
            list_voices=mocker.AsyncMock(
                return_value=SimpleNamespace(
                    voices=[
                        SimpleNamespace(name="en-US-Neural2-A"),
                        SimpleNamespace(name="en-US-Standard-B"),
                    ]
                )
            )
        )
        mocker.patch(
            "ankinote.services.tts.TextToSpeechAsyncClient", return_value=mock_client
        )

        service = GoogleTTSService("en-US", "Neural2")
        await service.warmup()

        assert service._available_voices == ["en-US-Neural2-A"]
        mock_client.list_voices.assert_awaited_once_with(language_code="en-US")

    @pytest.mark.asyncio
    async def test_synthesize_works_without_prior_warmup(self, mocker: MockerFixture):
        mock_client = SimpleNamespace(
            list_voices=mocker.AsyncMock(
                return_value=SimpleNamespace(
                    voices=[SimpleNamespace(name="en-US-Neural2-A")]
                )
            ),
            synthesize_speech=mocker.AsyncMock(
                return_value=SimpleNamespace(audio_content=b"audio")
            ),
        )
        mocker.patch(
            "ankinote.services.tts.TextToSpeechAsyncClient", return_value=mock_client
        )
        mocker.patch(
            "ankinote.services.tts.random.choice", return_value="en-US-Neural2-A"
        )

        service = GoogleTTSService("en-US", "Neural2")

        assert await service.synthesize("hello") == b"audio"
        mock_client.list_voices.assert_awaited_once()
        mock_client.synthesize_speech.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_synthesize_raises_when_no_matching_voice(
        self, mocker: MockerFixture
    ):
        mock_client = SimpleNamespace(
            list_voices=mocker.AsyncMock(
                return_value=SimpleNamespace(
                    voices=[SimpleNamespace(name="en-US-Standard-A")]
                )
            )
        )
        mocker.patch(
            "ankinote.services.tts.TextToSpeechAsyncClient", return_value=mock_client
        )

        service = GoogleTTSService("en-US", "Neural2")

        with pytest.raises(RuntimeError, match="No voices found"):
            await service.synthesize("hello")

    @pytest.mark.asyncio
    async def test_synthesize_reuses_warmed_cache(self, mocker: MockerFixture):
        mock_client = SimpleNamespace(
            list_voices=mocker.AsyncMock(
                return_value=SimpleNamespace(
                    voices=[SimpleNamespace(name="en-US-Neural2-A")]
                )
            ),
            synthesize_speech=mocker.AsyncMock(
                return_value=SimpleNamespace(audio_content=b"audio")
            ),
        )
        mocker.patch(
            "ankinote.services.tts.TextToSpeechAsyncClient", return_value=mock_client
        )
        mocker.patch(
            "ankinote.services.tts.random.choice", return_value="en-US-Neural2-A"
        )

        service = GoogleTTSService("en-US", "Neural2")
        await service.warmup()

        await service.synthesize("hello")
        await service.synthesize("world")

        mock_client.list_voices.assert_awaited_once()
        assert mock_client.synthesize_speech.await_count == 2

    @pytest.mark.asyncio
    async def test_synthesize_times_out(self, mocker: MockerFixture):
        async def never_returns(*args, **kwargs):
            await asyncio.Event().wait()

        mock_client = SimpleNamespace(
            synthesize_speech=mocker.AsyncMock(side_effect=never_returns)
        )
        service = GoogleTTSService("en-US", "Neural2")
        service._tts_cli = mock_client
        service._available_voices = ["en-US-Neural2-A"]
        mocker.patch("ankinote.services.tts.REQUEST_TIMEOUT_SECONDS", 0.01)

        with pytest.raises(RuntimeError, match="Text-to-speech request timed out"):
            await service.synthesize("hello")
