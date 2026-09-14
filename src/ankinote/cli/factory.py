"""CLI assembly helpers for application and collection wiring."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from ankinote.app import Application
from ankinote.collections.phrase import PhraseCollection
from ankinote.collections.sentence import SentenceCollection
from ankinote.collections.stem import CardType, StemCollection
from ankinote.collections.word import WordCollection
from ankinote.consts import Language
from ankinote.services.ai import (
    DEFAULT_AI_SERVICE_CONFIG,
    DISABLE_REASONING,
    THINKING_CHOICES,
    AIServiceConfigOverrides,
    LiteLLMImageService,
    LiteLLMTextService,
    resolve_thinking,
)
from ankinote.services.anki import AnkiCollectionClient
from ankinote.services.anki_factory import anki_backend_scope, create_anki_client

# ``THINKING_CHOICES`` / ``resolve_thinking`` moved to ``ankinote.services.ai``
# (shared with the GUI); re-exported here for the CLI modules that import them.
__all__ = ["THINKING_CHOICES", "resolve_thinking"]


class AsyncContextManagerLike[TCollection](Protocol):
    """Structural type for async context managers."""

    async def __aenter__(self) -> TCollection:
        """Enter the async context manager."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        ...


@dataclass(frozen=True, slots=True)
class LanguageCollectionOptions:
    """Shared CLI options for language-learning collections."""

    native_language: Language
    target_language: Language
    llm_model: str | None = None
    reasoning_effort: str | None = DISABLE_REASONING


@dataclass(frozen=True, slots=True)
class WordCollectionOptions(LanguageCollectionOptions):
    """CLI options for the word collection."""

    image_model: str | None = None
    image_size: int | None = None


@dataclass(frozen=True, slots=True)
class StemCollectionOptions:
    """CLI options for the STEM collection."""

    llm_model: str | None = None
    image_model: str | None = None
    image_size: int | None = None
    reasoning_effort: str | None = None
    card_type: CardType | None = None


def build_word_collection(
    client: AnkiCollectionClient,
    options: WordCollectionOptions,
) -> WordCollection:
    """Build a word collection from typed CLI options."""
    config = AIServiceConfigOverrides(
        text_model=options.llm_model,
        image_model=options.image_model,
        image_size=options.image_size,
    ).resolve(DEFAULT_AI_SERVICE_CONFIG)
    return WordCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=config.text_model,
        text_service=LiteLLMTextService(),
        image_service=LiteLLMImageService(
            model=config.image_model,
            image_size=config.image_size,
            image_quality=config.image_quality,
        ),
        reasoning_effort=options.reasoning_effort,
    )


def build_phrase_collection(
    client: AnkiCollectionClient,
    options: LanguageCollectionOptions,
) -> PhraseCollection:
    """Build a phrase collection from typed CLI options."""
    config = AIServiceConfigOverrides(
        text_model=options.llm_model,
    ).resolve(DEFAULT_AI_SERVICE_CONFIG)
    return PhraseCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=config.text_model,
        text_service=LiteLLMTextService(),
        reasoning_effort=options.reasoning_effort,
    )


def build_sentence_collection(
    client: AnkiCollectionClient,
    options: LanguageCollectionOptions,
) -> SentenceCollection:
    """Build a sentence collection from typed CLI options."""
    config = AIServiceConfigOverrides(
        text_model=options.llm_model,
    ).resolve(DEFAULT_AI_SERVICE_CONFIG)
    return SentenceCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=config.text_model,
        text_service=LiteLLMTextService(),
        reasoning_effort=options.reasoning_effort,
    )


def build_stem_collection(
    client: AnkiCollectionClient,
    options: StemCollectionOptions,
) -> StemCollection:
    """Build a STEM collection from typed CLI options."""
    config = AIServiceConfigOverrides(
        text_model=options.llm_model,
        image_model=options.image_model,
        image_size=options.image_size,
    ).resolve(DEFAULT_AI_SERVICE_CONFIG)
    image_service = None
    if config.image_model:
        image_service = LiteLLMImageService(
            model=config.image_model,
            image_size=config.image_size,
            image_quality=config.image_quality,
        )
    return StemCollection(
        client,
        card_type=options.card_type,
        text_model=config.text_model,
        text_service=LiteLLMTextService(),
        image_service=image_service,
        reasoning_effort=options.reasoning_effort,
    )


@asynccontextmanager
async def collection_context[TOptions, TCollection](
    builder: Callable[
        [AnkiCollectionClient, TOptions], AsyncContextManagerLike[TCollection]
    ],
    options: TOptions,
) -> AsyncIterator[TCollection]:
    """Create application, transport client, and collection in one place."""
    async with Application(), anki_backend_scope():
        client = create_anki_client()
        async with builder(client, options) as collection:
            yield collection
