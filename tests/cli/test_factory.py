"""Tests for CLI assembly helpers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import click
import pytest
from pytest_mock import MockerFixture

from ankinote.cli.factory import (
    LanguageCollectionOptions,
    StemCollectionOptions,
    WordCollectionOptions,
    anki_client_scope,
    build_phrase_collection,
    build_sentence_collection,
    build_stem_collection,
    build_word_collection,
    resolve_profile,
    resolve_thinking,
)
from ankinote.consts import Language
from ankinote.services.ai import (
    DISABLE_REASONING,
    LiteLLMImageService,
)
from ankinote.services.anki import NoteModel
from ankinote.settings import ProviderProfile, Settings, save_settings


class FakeAsyncContextManager:
    """Simple async context manager wrapper for tests."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class FakeCollectionClient:
    """Minimal client object satisfying the collection client protocol."""

    def __init__(self) -> None:
        self.models = FakeModelService()
        self.decks = FakeDeckService()
        self.notes = FakeNoteService()
        self.media = FakeMediaService()


class FakeModelService:
    """Typed fake model service."""

    async def exists(self, model_name: str) -> bool:
        return False

    async def create(
        self,
        model_name: str,
        fields: list[str],
        templates: list[dict[str, str]],
        css: str = "",
        is_cloze: bool = False,
    ) -> NoteModel:
        return NoteModel(id=1, name=model_name)


class FakeDeckService:
    """Typed fake deck service."""

    async def create(self, deck_name: str) -> int:
        return 1


class FakeNoteService:
    """Typed fake note service."""

    async def find(self, deck_name: str, unique_fields: dict[str, str]) -> int | None:
        return None

    async def add(
        self,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
        tags: list[str] | None = None,
        allow_duplicate: bool = False,
    ) -> int:
        return 1

    async def update_fields(self, note_id: int, fields: dict[str, str]) -> None:
        return None

    async def update_tags(self, note_id: int, tags: list[str]) -> None:
        return None


class FakeMediaService:
    """Typed fake media service."""

    async def store_file(self, filename: str, data: bytes) -> str:
        return filename


class TestCollectionBuilders:
    """Builder tests keep CLI option translation in one place."""

    def test_build_word_collection_uses_overrides(self):
        client = FakeCollectionClient()
        options = WordCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
            llm_model="llm-x",
            image_model="img-y",
            image_size=256,
        )

        collection = build_word_collection(client, options)

        assert collection._anki_client is client
        assert collection._native_language is Language.CHINESE_S
        assert collection._target_language is Language.ENGLISH
        assert collection._generator._text_model == "llm-x"
        image_service = collection._generator._image_service
        assert isinstance(image_service, LiteLLMImageService)
        assert image_service._model == "img-y"
        assert image_service._image_size == 256

    def test_build_word_collection_uses_default_ai_config(self):
        """No overrides and no settings.json -> falls back to the default profiles.

        The active text/image provider profiles created by a fresh
        ``Settings()`` (see ``_isolate_settings_file``) carry their own
        model, which now wins over ``DEFAULT_AI_SERVICE_CONFIG`` — see
        ``resolve_profile``/``_resolve_text_model``.
        """
        client = FakeCollectionClient()
        options = WordCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
        )
        settings = Settings()

        collection = build_word_collection(client, options)

        assert (
            collection._generator._text_model
            == settings.text_providers[settings.active_text_provider].model
        )
        image_service = collection._generator._image_service
        assert isinstance(image_service, LiteLLMImageService)
        assert (
            image_service._model
            == settings.image_providers[settings.active_image_provider].model
        )
        assert image_service._image_size == settings.image_size

    def test_build_phrase_collection(self):
        client = FakeCollectionClient()
        options = LanguageCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
            llm_model="llm-x",
        )

        collection = build_phrase_collection(client, options)

        assert collection._anki_client is client
        assert collection._native_language is Language.CHINESE_S
        assert collection._target_language is Language.ENGLISH
        assert collection._generator._text_model == "llm-x"

    def test_build_sentence_collection(self):
        client = FakeCollectionClient()
        options = LanguageCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
            llm_model="llm-x",
        )

        collection = build_sentence_collection(client, options)

        assert collection._anki_client is client
        assert collection._native_language is Language.CHINESE_S
        assert collection._target_language is Language.ENGLISH
        assert collection._generator._text_model == "llm-x"


class TestResolveThinking:
    """--thinking choice -> reasoning_effort mapping."""

    def test_omitted_flag_uses_collection_default(self):
        assert resolve_thinking(None, unset=DISABLE_REASONING) == DISABLE_REASONING
        assert resolve_thinking(None, unset=None) is None

    def test_off_disables_thinking(self):
        assert resolve_thinking("off", unset=None) == DISABLE_REASONING

    def test_default_requests_provider_default(self):
        assert resolve_thinking("default", unset=DISABLE_REASONING) is None

    def test_named_levels_pass_through(self):
        assert resolve_thinking("high", unset=DISABLE_REASONING) == "high"


class TestReasoningEffortPlumbing:
    """Collections forward the resolved reasoning_effort to their generator."""

    def test_word_collection_defaults_to_disabled(self):
        collection = build_word_collection(
            FakeCollectionClient(),
            WordCollectionOptions(
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
            ),
        )
        assert collection._reasoning_effort == DISABLE_REASONING

    def test_word_collection_honours_override(self):
        collection = build_word_collection(
            FakeCollectionClient(),
            WordCollectionOptions(
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                reasoning_effort="high",
            ),
        )
        assert collection._reasoning_effort == "high"

    def test_stem_collection_defaults_to_provider_default(self):
        collection = build_stem_collection(
            FakeCollectionClient(), StemCollectionOptions()
        )
        assert collection._reasoning_effort is None


class TestResolveProfile:
    """``--profile``/``--image-profile`` name lookup."""

    def test_falls_back_to_active_when_no_name_given(self):
        providers = {"a": ProviderProfile(model="model-a")}
        assert resolve_profile(None, providers, "a") is providers["a"]

    def test_named_profile_overrides_active(self):
        providers = {
            "a": ProviderProfile(model="model-a"),
            "b": ProviderProfile(model="model-b"),
        }
        assert resolve_profile("b", providers, "a") is providers["b"]

    def test_unknown_name_lists_available_profiles(self):
        providers = {"a": ProviderProfile(model="model-a")}
        with pytest.raises(click.UsageError, match="bogus.*Available profiles: a"):
            resolve_profile("bogus", providers, "a")


class TestProfileSelection:
    """A named ``--profile``/``--image-profile`` is read from settings.json."""

    def test_named_text_profile_wins_over_active(self):
        settings = Settings(
            text_providers={
                "OpenAI": ProviderProfile(vendor="OpenAI", model="gpt-4o"),
                "second": ProviderProfile(
                    vendor="Custom / Other",
                    model="my-model",
                    base_url="https://example.test/v1",
                    api_key="secret",
                ),
            },
            active_text_provider="OpenAI",
        )
        save_settings(settings)

        collection = build_phrase_collection(
            FakeCollectionClient(),
            LanguageCollectionOptions(
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                profile="second",
            ),
        )

        assert collection._generator._text_model == "my-model"

    def test_llm_override_wins_over_profile_model(self):
        settings = Settings(
            text_providers={
                "OpenAI": ProviderProfile(vendor="OpenAI", model="gpt-4o"),
            },
            active_text_provider="OpenAI",
        )
        save_settings(settings)

        collection = build_phrase_collection(
            FakeCollectionClient(),
            LanguageCollectionOptions(
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                llm_model="explicit-model",
            ),
        )

        assert collection._generator._text_model == "explicit-model"

    def test_unknown_profile_raises_usage_error(self):
        collection_options = LanguageCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
            profile="does-not-exist",
        )
        with pytest.raises(click.UsageError, match="does-not-exist"):
            build_phrase_collection(FakeCollectionClient(), collection_options)


class TestAnkiClientScope:
    """Assembly tests for application + client setup."""

    @pytest.mark.asyncio
    async def test_anki_client_scope_yields_client(self, mocker: MockerFixture):
        built_collection = SimpleNamespace(name="collection")
        builder = mocker.Mock(return_value=FakeAsyncContextManager(built_collection))
        client = object()
        options = object()

        @asynccontextmanager
        async def fake_application():
            yield

        mocker.patch(
            "ankinote.cli.factory.Application", return_value=fake_application()
        )
        mocker.patch("ankinote.cli.factory.create_anki_client", return_value=client)

        async with anki_client_scope() as scoped_client:
            assert scoped_client is client
            async with builder(scoped_client, options) as collection:
                assert collection is built_collection

        builder.assert_called_once_with(client, options)
