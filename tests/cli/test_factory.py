"""Tests for CLI assembly helpers."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

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
    resolve_thinking,
)
from ankinote.consts import Language
from ankinote.services.ai import (
    DEFAULT_AI_SERVICE_CONFIG,
    DISABLE_REASONING,
    LiteLLMImageService,
)
from ankinote.services.anki import NoteModel


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
        client = FakeCollectionClient()
        options = WordCollectionOptions(
            native_language=Language.CHINESE_S,
            target_language=Language.ENGLISH,
        )

        collection = build_word_collection(client, options)

        assert collection._generator._text_model == DEFAULT_AI_SERVICE_CONFIG.text_model
        image_service = collection._generator._image_service
        assert isinstance(image_service, LiteLLMImageService)
        assert image_service._model == DEFAULT_AI_SERVICE_CONFIG.image_model
        assert image_service._image_size == DEFAULT_AI_SERVICE_CONFIG.image_size

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
