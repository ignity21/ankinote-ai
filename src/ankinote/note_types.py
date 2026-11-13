"""The note types and decks ankinote manages in Anki.

Shared by the web API (wizard "Connect Anki", the Note types workspace) and
the NiceGUI Card Types page. Each spec mirrors what its collection's
``ensure_in_anki()`` writes, so a status computed here matches what setting
it up will actually do.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from ankinote.card_theme import CardTheme, current_theme
from ankinote.collections.common import store_card_fonts
from ankinote.collections.phrase import PhraseCollection
from ankinote.collections.phrase.models import PhraseNoteType
from ankinote.collections.phrase.templates import load_card_style as _phrase_style
from ankinote.collections.sentence import SentenceCollection
from ankinote.collections.sentence.models import SentenceNoteType
from ankinote.collections.sentence.templates import load_card_style as _sentence_style
from ankinote.collections.stem import StemCollection
from ankinote.collections.stem.models import NOTE_FIELDS, CardType, note_type_name
from ankinote.collections.stem.templates import load_card_style as _stem_style
from ankinote.collections.word import WordCollection
from ankinote.collections.word.models import WordNoteType
from ankinote.collections.word.templates import load_card_style as _word_style
from ankinote.consts import Language
from ankinote.services.ai import LiteLLMTextService
from ankinote.services.anki import AnkiCollectionClient

State = Literal["synced", "update", "missing"]


@dataclass(frozen=True, slots=True)
class NoteTypeSpec:
    """Static description of one note type ankinote can create/update."""

    key: str
    notetype_name: str  # Anki model name
    deck_name: str  # Anki deck path
    fields: tuple[str, ...]
    templates: tuple[str, ...]
    css: str
    sync: Callable[[AnkiCollectionClient], Awaitable[None]]

    @property
    def css_size_kb(self) -> str:
        """Human-readable size of the note type styling."""
        return f"{len(self.css.encode()) / 1024:.1f} KB"


@dataclass(frozen=True, slots=True)
class TypeStatus:
    """Live status of one note type as seen in Anki."""

    spec: NoteTypeSpec
    exists: bool
    deck_exists: bool
    missing_fields: list[str]
    missing_templates: list[str]
    css_differs: bool

    @property
    def state(self) -> State:
        if not self.exists:
            return "missing"
        if self.missing_fields or self.missing_templates or self.css_differs:
            return "update"
        return "synced"


def _field_names(note_type) -> tuple[str, ...]:
    return tuple(field.name for field in note_type.__dataclass_fields__.values())


def build_specs(theme: CardTheme | None = None) -> list[NoteTypeSpec]:
    """The fixed set of note types managed by ankinote, in display order.

    Their styling uses ``theme``, or the card theme saved in settings.
    """
    theme = theme or current_theme()

    def sync_word(notetype_name: str, deck_name: str):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = WordCollection(
                client,
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                notetype_name=notetype_name,
                deck_name=deck_name,
                text_model="",
                text_service=LiteLLMTextService(),
                image_service=None,
            )
            await collection.ensure_in_anki()

        return _sync

    def sync_language(clazz, notetype_name: str, deck_name: str):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = clazz(
                client,
                native_language=Language.CHINESE_S,
                target_language=Language.ENGLISH,
                notetype_name=notetype_name,
                deck_name=deck_name,
                text_model="",
                text_service=LiteLLMTextService(),
            )
            await collection.ensure_in_anki()

        return _sync

    def sync_stem(card_type: CardType):
        async def _sync(client: AnkiCollectionClient) -> None:
            collection = StemCollection(
                client,
                card_type=card_type,
                text_model="",
                text_service=LiteLLMTextService(),
            )
            await collection.ensure_in_anki()

        return _sync

    return [
        NoteTypeSpec(
            key="word",
            notetype_name="AINote Word V2",
            deck_name="AINote::Words",
            fields=_field_names(WordNoteType),
            templates=("Recognition", "Recall", "Spelling"),
            css=_word_style(theme),
            sync=sync_word("AINote Word V2", "AINote::Words"),
        ),
        NoteTypeSpec(
            key="phrase",
            notetype_name="AINote Phrase V2",
            deck_name="AINote::Phrases",
            fields=_field_names(PhraseNoteType),
            templates=("Recognition", "Recall"),
            css=_phrase_style(theme),
            sync=sync_language(PhraseCollection, "AINote Phrase V2", "AINote::Phrases"),
        ),
        NoteTypeSpec(
            key="sentence",
            notetype_name="AINote Sentence V2",
            deck_name="AINote::Sentences",
            fields=_field_names(SentenceNoteType),
            templates=("Production",),
            css=_sentence_style(theme),
            sync=sync_language(
                SentenceCollection, "AINote Sentence V2", "AINote::Sentences"
            ),
        ),
        *[
            NoteTypeSpec(
                key=f"stem_{kind}",
                notetype_name=note_type_name(kind),
                deck_name="AINote::STEM",
                fields=NOTE_FIELDS[kind],
                templates=("Card 1",),
                css=_stem_style(theme),
                sync=sync_stem(kind),
            )
            for kind in CardType
        ],
    ]


async def load_status(client: AnkiCollectionClient, spec: NoteTypeSpec) -> TypeStatus:
    """Compute one note type's live status from Anki."""
    model = await client.models.get(spec.notetype_name)
    deck_exists = await client.decks.exists(spec.deck_name)
    if model is None:
        return TypeStatus(
            spec=spec,
            exists=False,
            deck_exists=deck_exists,
            missing_fields=[],
            missing_templates=[],
            css_differs=False,
        )

    existing_fields = {f.name for f in model.fields}
    existing_templates = {t.name for t in model.templates}
    return TypeStatus(
        spec=spec,
        exists=True,
        deck_exists=deck_exists,
        missing_fields=[f for f in spec.fields if f not in existing_fields],
        missing_templates=[t for t in spec.templates if t not in existing_templates],
        css_differs=model.css != spec.css,
    )


async def restyle(client: AnkiCollectionClient, specs: list[NoteTypeSpec]) -> list[str]:
    """Give the note types that exist their spec's styling, and nothing else.

    Unlike setting a type up, this never adds fields or card templates (new
    templates would create cards), and types that don't exist stay absent.
    Returns the keys of the types restyled.
    """
    existing = [s for s in specs if await client.models.exists(s.notetype_name)]
    if existing:
        await store_card_fonts(client)
    for spec in existing:
        await client.models.update_styling(spec.notetype_name, spec.css)
    return [spec.key for spec in existing]
