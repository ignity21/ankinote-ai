"""CLI assembly helpers for application and collection wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import click

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
    resolve_thinking,
)
from ankinote.services.anki import AnkiCollectionClient
from ankinote.services.anki_factory import anki_backend_scope, create_anki_client
from ankinote.services.provider_factory import build_image_service, build_text_service
from ankinote.settings import ProviderProfile, Settings, load_settings

# ``THINKING_CHOICES`` / ``resolve_thinking`` moved to ``ankinote.services.ai``
# (shared with the GUI); re-exported here for the CLI modules that import them.
__all__ = ["THINKING_CHOICES", "resolve_thinking"]


def resolve_profile(
    name: str | None, providers: dict[str, ProviderProfile], active: str
) -> ProviderProfile:
    """Look up a named provider profile, defaulting to the active one.

    Raises ``click.UsageError`` listing the available profile names when
    ``name`` does not match any configured profile.
    """
    key = name or active
    try:
        return providers[key]
    except KeyError:
        available = ", ".join(sorted(providers)) or "(none configured)"
        raise click.UsageError(
            f"Unknown provider profile {key!r}. Available profiles: {available}"
        ) from None


@dataclass(frozen=True, slots=True)
class LanguageCollectionOptions:
    """Shared CLI options for language-learning collections."""

    native_language: Language
    target_language: Language
    llm_model: str | None = None
    reasoning_effort: str | None = DISABLE_REASONING
    profile: str | None = None


@dataclass(frozen=True, slots=True)
class WordCollectionOptions(LanguageCollectionOptions):
    """CLI options for the word collection."""

    image_model: str | None = None
    image_size: int | None = None
    image_profile: str | None = None


@dataclass(frozen=True, slots=True)
class StemCollectionOptions:
    """CLI options for the STEM collection."""

    llm_model: str | None = None
    image_model: str | None = None
    image_size: int | None = None
    reasoning_effort: str | None = None
    card_type: CardType | None = None
    profile: str | None = None
    image_profile: str | None = None


def _resolve_text_model(llm_model: str | None, profile: ProviderProfile) -> str:
    """``--llm`` override > the profile's own model > the built-in default."""
    return llm_model or profile.model or DEFAULT_AI_SERVICE_CONFIG.text_model


def _resolve_image_model(image_model: str | None, profile: ProviderProfile) -> str:
    """``--image-model`` override > the profile's own model > the built-in default."""
    return image_model or profile.model or DEFAULT_AI_SERVICE_CONFIG.image_model


def _resolve_image_size(image_size: int | None, settings: Settings) -> int:
    """``--image-size`` override > the shared setting persisted for the GUI."""
    return settings.image_size if image_size is None else image_size


def build_word_collection(
    client: AnkiCollectionClient,
    options: WordCollectionOptions,
) -> WordCollection:
    """Build a word collection from typed CLI options."""
    settings = load_settings()
    text_profile = resolve_profile(
        options.profile, settings.text_providers, settings.active_text_provider
    )
    image_profile = resolve_profile(
        options.image_profile, settings.image_providers, settings.active_image_provider
    )
    image_model = _resolve_image_model(options.image_model, image_profile)
    return WordCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=_resolve_text_model(options.llm_model, text_profile),
        text_service=build_text_service(text_profile),
        image_service=build_image_service(
            image_profile,
            image_size=_resolve_image_size(options.image_size, settings),
            model=image_model,
        ),
        reasoning_effort=options.reasoning_effort,
    )


def build_phrase_collection(
    client: AnkiCollectionClient,
    options: LanguageCollectionOptions,
) -> PhraseCollection:
    """Build a phrase collection from typed CLI options."""
    settings = load_settings()
    text_profile = resolve_profile(
        options.profile, settings.text_providers, settings.active_text_provider
    )
    return PhraseCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=_resolve_text_model(options.llm_model, text_profile),
        text_service=build_text_service(text_profile),
        reasoning_effort=options.reasoning_effort,
    )


def build_sentence_collection(
    client: AnkiCollectionClient,
    options: LanguageCollectionOptions,
) -> SentenceCollection:
    """Build a sentence collection from typed CLI options."""
    settings = load_settings()
    text_profile = resolve_profile(
        options.profile, settings.text_providers, settings.active_text_provider
    )
    return SentenceCollection(
        client,
        native_language=options.native_language,
        target_language=options.target_language,
        text_model=_resolve_text_model(options.llm_model, text_profile),
        text_service=build_text_service(text_profile),
        reasoning_effort=options.reasoning_effort,
    )


def build_stem_collection(
    client: AnkiCollectionClient,
    options: StemCollectionOptions,
) -> StemCollection:
    """Build a STEM collection from typed CLI options."""
    settings = load_settings()
    text_profile = resolve_profile(
        options.profile, settings.text_providers, settings.active_text_provider
    )
    image_profile = resolve_profile(
        options.image_profile, settings.image_providers, settings.active_image_provider
    )
    image_model = _resolve_image_model(options.image_model, image_profile)
    image_service = build_image_service(
        image_profile,
        image_size=_resolve_image_size(options.image_size, settings),
        model=image_model,
    )
    return StemCollection(
        client,
        card_type=options.card_type,
        text_model=_resolve_text_model(options.llm_model, text_profile),
        text_service=build_text_service(text_profile),
        image_service=image_service,
        reasoning_effort=options.reasoning_effort,
    )


@asynccontextmanager
async def anki_client_scope() -> AsyncIterator[AnkiCollectionClient]:
    """Create the application and transport client together."""
    async with Application(), anki_backend_scope():
        yield create_anki_client()
