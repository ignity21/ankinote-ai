"""Sentence collection management for Anki V2."""

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Self

from loguru import logger

from ankinote.collections.common import convert_to_html_ruby
from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.anki import AnkiCollectionClient, TemplateUpsert
from ankinote.services.ai import TextGenerationService
from ankinote.services.tts import TTS_LANG_CODES, GoogleTTSService

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

    pron_audio: str  # Filename: "sentence_uuid.mp3"


class SentenceCollection:
    """Manages sentence production notes in Anki (V2)."""

    def __init__(
        self,
        anki_client: AnkiCollectionClient,
        *,
        native_language: Language,
        target_language: Language,
        notetype_name: str = "AINote Sentence V2",
        deck_name: str = "AINote::Sentences",
        text_model_id: str,
        text_service: TextGenerationService,
    ) -> None:
        """Initialize SentenceCollection."""
        self.notetype_name = notetype_name
        self.deck_name = deck_name
        self._native_language = native_language
        self._target_language = target_language
        self._anki_client = anki_client
        self._tts_service = GoogleTTSService(TTS_LANG_CODES[target_language])
        self._generator = SentenceGenerator(
            tts_service=self._tts_service,
            text_service=text_service,
            text_model_id=text_model_id,
        )

        if target_language in RUBY_ANNOTATION_LANGUAGES:
            self._convert_target_lang_text = convert_to_html_ruby
        else:
            self._convert_target_lang_text = lambda x: x  # No conversion needed

    async def __aenter__(self) -> Self:
        await self._tts_service.warmup()
        await self._ensure_note_type_exists()
        await self._ensure_deck_exists()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._tts_service.clear_cache()

    async def _ensure_note_type_exists(self) -> None:
        """Ensure the note type exists in Anki, create or update it."""
        fields = [f.name for f in dataclasses.fields(SentenceNoteType)]
        css = load_card_style()
        templates = [
            {
                "Name": "Production",
                "Front": load_template("front.html"),
                "Back": load_template("back.html"),
            },
        ]
        exists = await self._anki_client.models.exists(self.notetype_name)
        if not exists:
            await self._anki_client.models.create(
                model_name=self.notetype_name,
                fields=fields,
                templates=templates,
                css=css,
                is_cloze=False,
            )
            logger.success(f"Created note type: {self.notetype_name}")
            return

        await self._anki_client.models.update_templates(
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
        await self._anki_client.models.update_styling(self.notetype_name, css)
        logger.success(f"Updated note type: {self.notetype_name}")

    async def _ensure_deck_exists(self) -> int:
        """Ensure the deck exists in Anki, create it if it doesn't."""
        deck_id = await self._anki_client.decks.create(self.deck_name)
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
        logger.info(f"Starting generation for sentence: {target_sentence}")

        sentence_model = await self._generator.generate_sentence_data(
            target_sentence=target_sentence,
            target_lang=self._target_language,
            native_lang=self._native_language,
        )

        media = await self._generator.generate_media(
            sentence_model=sentence_model,
            target_lang=self._target_language,
        )

        card_data = SentenceCardData(model=sentence_model, media=media)

        note_id = await self._add_or_update_note(
            card_data=card_data,
            tags=tags or [self._target_language.value, "AI-generated", "Sentence"],
        )

        logger.success(
            f"Completed generation for sentence '{target_sentence}', note {note_id}"
        )
        return note_id

    async def _add_or_update_note(
        self,
        card_data: SentenceCardData,
        tags: list[str],
    ) -> int:
        """Add or update a sentence note in Anki."""
        sentence_model = card_data.model
        logger.info(
            f"Adding/updating sentence note '{sentence_model.target_sentence}' "
            f"to {self.deck_name}"
        )

        media_refs = await self._store_media_files(card_data)
        note_data = self._convert_to_note_type(sentence_model, media_refs)

        note_id = await self._anki_client.notes.find(
            deck_name=self.deck_name,
            unique_fields={"target_sentence": sentence_model.target_sentence},
        )

        if note_id is not None:
            await self._anki_client.notes.update_fields(note_id, note_data)
            await self._anki_client.notes.update_tags(note_id, tags)
            logger.info(f"Updated sentence note {note_id}")
        else:
            note_id = await self._anki_client.notes.add(
                deck_name=self.deck_name,
                model_name=self.notetype_name,
                fields=note_data,
                tags=tags,
                allow_duplicate=True,
            )
            logger.info(f"Created sentence note {note_id}")

        return note_id

    async def _store_media_files(self, card_data: SentenceCardData) -> MediaReferences:
        """Store media files in Anki and return their references."""
        sentence_model = card_data.model
        filename = hashlib.md5(sentence_model.target_sentence.encode()).hexdigest()[:12]
        audio_name = f"{filename}.mp3"
        await self._anki_client.media.store_file(
            audio_name, card_data.media.sentence_audio
        )
        logger.debug(f"Stored sentence audio: {audio_name}")

        return MediaReferences(pron_audio=audio_name)

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
            "pron_audio": f"[sound:{media_refs.pron_audio}]",
            "notes": self._format_notes_html(sentence_model.notes),
            "phrases": self._format_phrases_html(sentence_model.phrases),
            "user_notes": "",
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
