"""Sentence collection management for Anki V2."""

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Self

from loguru import logger

from ankinote.collections.common import convert_to_html_ruby
from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.ai import DISABLE_REASONING, TextGenerationService
from ankinote.services.anki import AnkiCollectionClient, TemplateUpsert
from ankinote.services.anki_batch import anki_write_batch
from ankinote.services.tts import SpeechService

from .generator import SentenceGenerator, SentenceMediaFiles
from .models import PhraseModel, SentenceModel, SentenceNoteType
from .templates import load_card_style, load_template


@dataclass
class SentenceCardData:
    """Complete card data including model and media files."""

    model: SentenceModel
    media: SentenceMediaFiles


@dataclass
class MediaReferences:
    """References to media files stored in Anki."""

    pron_audio: str | None  # Filename: "<hash>.mp3"; None without audio


class SentenceCollection:
    """Manages sentence production notes in Anki (V2)."""

    def __init__(
        self,
        anki_client: AnkiCollectionClient | None,
        *,
        native_language: Language,
        target_language: Language,
        notetype_name: str = "AINote Sentence V2",
        deck_name: str = "AINote::Sentences",
        text_model: str,
        text_service: TextGenerationService,
        reasoning_effort: str | None = DISABLE_REASONING,
        tts_service: SpeechService | None = None,
    ) -> None:
        """Initialize SentenceCollection."""
        self.notetype_name = notetype_name
        self.deck_name = deck_name
        self._native_language = native_language
        self._target_language = target_language
        self._anki_client = anki_client
        self._reasoning_effort = reasoning_effort
        # None: cards are made without audio.
        self._tts_service = tts_service
        self._generator = SentenceGenerator(
            tts_service=self._tts_service,
            text_service=text_service,
            text_model=text_model,
        )

        if target_language in RUBY_ANNOTATION_LANGUAGES:
            self._convert_target_lang_text = convert_to_html_ruby
        else:
            self._convert_target_lang_text = lambda x: x  # No conversion needed

    @property
    def _anki(self) -> AnkiCollectionClient:
        if self._anki_client is None:
            raise RuntimeError("This sentence collection was built without Anki")
        return self._anki_client

    @staticmethod
    def card_templates() -> list[dict[str, str]]:
        """The note type's card templates, as Anki stores them."""
        return [
            {
                "Name": "Production",
                "Front": load_template("front.html"),
                "Back": load_template("back.html"),
            },
        ]

    async def __aenter__(self) -> Self:
        if self._tts_service is not None:
            await self._tts_service.warmup()
        await self._ensure_note_type_exists()
        await self._ensure_deck_exists()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._tts_service is not None:
            self._tts_service.clear_cache()

    async def ensure_in_anki(self) -> None:
        """Create or update this note type and its deck in Anki.

        Idempotent equivalent of the CLI ``init`` command: creates the note
        type with the current fields, templates and styling when missing, or
        refreshes templates, styling and missing fields when it already exists,
        then ensures the deck is present. Does not start TTS or LLM services,
        so it is safe to call from the GUI setup flow.
        """
        async with anki_write_batch(self._anki):
            await self._ensure_note_type_exists()
            await self._ensure_deck_exists()

    async def _ensure_note_type_exists(self) -> None:
        """Ensure the note type exists in Anki, create or update it."""
        fields = [f.name for f in dataclasses.fields(SentenceNoteType)]
        css = load_card_style()
        templates = self.card_templates()
        exists = await self._anki.models.exists(self.notetype_name)
        if not exists:
            await self._anki.models.create(
                model_name=self.notetype_name,
                fields=fields,
                templates=templates,
                css=css,
                is_cloze=False,
            )
            logger.success(f"Created note type: {self.notetype_name}")
            return

        # Ensure new fields (e.g. target_language) are added for existing note types
        await self._anki.models.ensure_fields(self.notetype_name, fields)
        await self._anki.models.update_templates(
            self.notetype_name,
            [
                TemplateUpsert(
                    name=template["Name"],
                    question_format=template["Front"],
                    answer_format=template["Back"],
                )
                for template in templates
            ],
        )
        await self._anki.models.update_styling(self.notetype_name, css)
        logger.success(f"Updated note type: {self.notetype_name}")

    async def _ensure_deck_exists(self) -> int:
        """Ensure the deck exists in Anki, create it if it doesn't."""
        deck_id = await self._anki.decks.create(self.deck_name)
        logger.success(f"Ensured deck exists: {self.deck_name}")
        return deck_id

    async def generate_and_add_note(
        self,
        target_sentence: str,
        tags: list[str] | None = None,
    ) -> int:
        """Generate complete sentence data and add/update note in Anki.

        The *target_sentence* is the sentence in the language being learned.
        The LLM generates its native-language translation and learning notes.
        """
        [card] = await self.generate_cards(target_sentence)
        note_id = await self.save_card(card, tags)
        logger.success(
            f"Completed generation for sentence '{target_sentence}', note {note_id}"
        )
        return note_id

    async def generate_cards(self, target_sentence: str) -> list[SentenceCardData]:
        """Generate the note for ``target_sentence``, unsaved (always one)."""
        logger.info(f"Starting generation for sentence: {target_sentence}")
        sentence_model = await self._generator.generate_sentence_data(
            target_sentence=target_sentence,
            target_lang=self._target_language,
            native_lang=self._native_language,
            reasoning_effort=self._reasoning_effort,
        )
        media = await self._generator.generate_media(
            sentence_model=sentence_model,
            target_lang=self._target_language,
        )
        return [SentenceCardData(model=sentence_model, media=media)]

    async def save_card(
        self, card: SentenceCardData, tags: list[str] | None = None
    ) -> int:
        """Add the card's note, or update the one with the same sentence."""
        return await self._add_or_update_note(
            card_data=card,
            tags=tags or [self._target_language.value, "AI-generated", "Sentence"],
        )

    async def revise_card(
        self, card: SentenceCardData, model: SentenceModel
    ) -> SentenceCardData:
        """``card`` with an edited ``model``; the sentence (and its audio) stay."""
        return SentenceCardData(model=model, media=card.media)

    def note_fields(self, card: SentenceCardData) -> dict[str, str]:
        """The note's fields as Anki will store them."""
        return self._convert_to_note_type(card.model, self.media_names(card))

    def media_files(self, card: SentenceCardData) -> dict[str, bytes]:
        """The card's media under the names its fields refer to."""
        name, audio = self.media_names(card).pron_audio, card.media.sentence_audio
        return {name: audio} if name and audio is not None else {}

    @staticmethod
    def media_names(card: SentenceCardData) -> MediaReferences:
        """The name derives from the sentence, so regenerating reuses it."""
        if card.media.sentence_audio is None:
            return MediaReferences(pron_audio=None)
        digest = hashlib.md5(card.model.target_sentence.encode()).hexdigest()[:12]
        return MediaReferences(pron_audio=f"{digest}.mp3")

    async def _add_or_update_note(
        self,
        card_data: SentenceCardData,
        tags: list[str],
    ) -> int:
        """Add or update a sentence note in Anki."""
        async with anki_write_batch(self._anki):
            sentence_model = card_data.model
            logger.info(
                f"Adding/updating sentence note '{sentence_model.target_sentence}' "
                f"to {self.deck_name}"
            )

            media_refs = await self._store_media_files(card_data)
            note_data = self._convert_to_note_type(sentence_model, media_refs)

            note_id = await self._anki.notes.find(
                deck_name=self.deck_name,
                unique_fields={"target_sentence": sentence_model.target_sentence},
            )

            if note_id is not None:
                await self._anki.notes.update_fields(note_id, note_data)
                await self._anki.notes.update_tags(note_id, tags)
                logger.info(f"Updated sentence note {note_id}")
            else:
                note_id = await self._anki.notes.add(
                    deck_name=self.deck_name,
                    model_name=self.notetype_name,
                    fields=note_data,
                    tags=tags,
                    allow_duplicate=True,
                )
                logger.info(f"Created sentence note {note_id}")

            return note_id

    async def _store_media_files(self, card_data: SentenceCardData) -> MediaReferences:
        """Store the media; the reference uses the name Anki actually gave."""
        stored = {
            name: await self._anki.media.store_file(name, data) or name
            for name, data in self.media_files(card_data).items()
        }
        name = self.media_names(card_data).pron_audio
        return MediaReferences(pron_audio=stored.get(name, name) if name else None)

    def _convert_to_note_type(
        self,
        sentence_model: SentenceModel,
        media_refs: MediaReferences,
    ) -> dict[str, str]:
        """Convert SentenceModel and media references to Anki note fields."""
        return {
            "target_sentence": self._convert_target_lang_text(
                sentence_model.target_sentence
            ),
            "native_sentence": sentence_model.native_sentence,
            "pron_audio": f"[sound:{media_refs.pron_audio}]"
            if media_refs.pron_audio
            else "",
            "notes": self._format_notes_html(sentence_model.notes),
            "phrases": self._format_phrases_html(sentence_model.phrases),
            "user_notes": "",
            "target_language": self._target_language.value,
        }

    def _format_notes_html(self, notes: list[str]) -> str:
        """Format notes as HTML."""
        if not notes:
            return ""
        formatted = [f"• {note}" for note in notes]
        return "<br>".join(formatted)

    def _format_phrases_html(self, phrases: list[PhraseModel]) -> str:
        """Format phrases and their example sentences as HTML."""
        if not phrases:
            return ""
        items = []
        for phrase_model in phrases:
            phrase_ruby = self._convert_target_lang_text(phrase_model.phrase)
            translation = phrase_model.translation
            example_ruby = self._convert_target_lang_text(phrase_model.example)
            items.append(
                "<div class='phrase-entry'>"
                f"<div class='phrase-target'>{phrase_ruby}</div>"
                f"<div class='phrase-translation'>{translation}</div>"
                f"<div class='phrase-example'>{example_ruby}</div>"
                "</div>"
            )
        return "".join(items)
