"""Phrase collection management for Anki V2."""

import dataclasses
import hashlib
import html
from dataclasses import dataclass
from typing import Self

from loguru import logger

from ankinote.collections.common import convert_to_html_ruby, strip_phonetic_annotations
from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.ai import DISABLE_REASONING, TextGenerationService
from ankinote.services.anki import AnkiCollectionClient, TemplateUpsert
from ankinote.services.anki_batch import anki_write_batch
from ankinote.services.tts import TTS_LANG_CODES, GoogleTTSService

from .generator import PhraseGenerator, PhraseMediaFiles
from .models import Example, PhraseModel, PhraseNoteType, Sense
from .templates import load_card_style, load_template


@dataclass
class PhraseCardData:
    """Complete card data including model and media files."""

    model: PhraseModel
    media: PhraseMediaFiles


@dataclass
class MediaReferences:
    """References to media files stored in Anki."""

    phrase_audio: str  # Filename: "phrase_uuid.mp3"
    example_audios: list[str]  # Filenames: ["phrase_ex0_uuid.mp3", ...]


class PhraseCollection:
    """Manages phrase / idiom / sentence notes in Anki (V2)."""

    def __init__(
        self,
        anki_client: AnkiCollectionClient,
        *,
        native_language: Language,
        target_language: Language,
        notetype_name: str = "AINote Phrase V2",
        deck_name: str = "AINote::Phrases",
        text_model: str,
        text_service: TextGenerationService,
        reasoning_effort: str | None = DISABLE_REASONING,
    ) -> None:
        """Initialize PhraseCollection."""
        self.notetype_name = notetype_name
        self.deck_name = deck_name
        self._native_language = native_language
        self._target_language = target_language
        self._anki_client = anki_client
        self._reasoning_effort = reasoning_effort
        self._tts_service = GoogleTTSService(TTS_LANG_CODES[target_language])
        self._generator = PhraseGenerator(
            self._tts_service,
            text_service=text_service,
            text_model=text_model,
        )
        if target_language in RUBY_ANNOTATION_LANGUAGES:
            self._convert_target_lang_text = convert_to_html_ruby
        else:
            self._convert_target_lang_text = lambda value: value

    async def __aenter__(self) -> Self:
        """Async context manager entry: ensure note type and deck exist."""
        await self._tts_service.warmup()
        await self._ensure_note_type_exists()
        await self._ensure_deck_exists()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit: clean up TTS service."""
        self._tts_service.clear_cache()

    async def ensure_in_anki(self) -> None:
        """Create or update this note type and its deck in Anki.

        Idempotent equivalent of the CLI ``init`` command: creates the note
        type with the current fields, templates and styling when missing, or
        refreshes templates, styling and missing fields when it already exists,
        then ensures the deck is present. Does not start TTS or LLM services,
        so it is safe to call from the GUI setup flow.
        """
        async with anki_write_batch(self._anki_client):
            await self._ensure_note_type_exists()
            await self._ensure_deck_exists()

    async def _ensure_note_type_exists(self) -> None:
        """Ensure the note type exists in Anki, create or update it."""
        fields = [field.name for field in dataclasses.fields(PhraseNoteType)]
        css = load_card_style()
        templates = [
            {
                "Name": "Recognition",
                "Front": load_template("front.html"),
                "Back": load_template("back.html"),
            },
            {
                "Name": "Recall",
                "Front": load_template("reverse_front.html"),
                "Back": load_template("reverse_back.html"),
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

        # Ensure new fields (e.g. target_language) are added for existing note types
        await self._anki_client.models.ensure_fields(self.notetype_name, fields)
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
        phrase: str,
        tags: list[str] | None = None,
    ) -> int:
        """Generate complete phrase data and add/update note in Anki."""
        logger.info(f"Starting generation for phrase: {phrase}")

        phrase_model = await self._generator.generate_phrase_data(
            phrase=phrase,
            target_lang=self._target_language,
            native_lang=self._native_language,
            reasoning_effort=self._reasoning_effort,
        )

        media = await self._generator.generate_media(
            phrase_model=phrase_model,
            target_lang=self._target_language,
        )

        card_data = PhraseCardData(model=phrase_model, media=media)

        note_id = await self._add_or_update_note(
            card_data=card_data,
            tags=tags or [self._target_language.value, "AI-generated", "Phrase"],
        )

        logger.success(f"Completed generation for phrase '{phrase}', note {note_id}")
        return note_id

    async def _add_or_update_note(
        self,
        card_data: PhraseCardData,
        tags: list[str],
    ) -> int:
        """Add or update a phrase note in Anki."""
        async with anki_write_batch(self._anki_client):
            phrase_model = card_data.model
            logger.info(
                f"Adding/updating phrase note '{phrase_model.phrase}' to {self.deck_name}"
            )

            media_refs = await self._store_media_files(card_data)
            note_data = self._convert_to_note_type(phrase_model, media_refs)

            note_id = await self._anki_client.notes.find(
                deck_name=self.deck_name,
                unique_fields={"phrase": phrase_model.phrase},
            )

            if note_id is not None:
                await self._anki_client.notes.update_fields(note_id, note_data)
                await self._anki_client.notes.update_tags(note_id, tags)
                logger.info(f"Updated phrase note {note_id}")
            else:
                note_id = await self._anki_client.notes.add(
                    deck_name=self.deck_name,
                    model_name=self.notetype_name,
                    fields=note_data,
                    tags=tags,
                    allow_duplicate=True,
                )
                logger.info(f"Created phrase note {note_id}")

            return note_id

    async def _store_media_files(self, card_data: PhraseCardData) -> MediaReferences:
        """Store media files in Anki and return their references."""
        phrase_model = card_data.model
        media = card_data.media
        phrase_hash = hashlib.md5(phrase_model.phrase.encode()).hexdigest()[:12]

        phrase_audio_name = f"{phrase_hash}.mp3"
        await self._anki_client.media.store_file(phrase_audio_name, media.phrase_audio)
        logger.debug(f"Stored phrase audio: {phrase_audio_name}")

        example_audio_names: list[str] = []
        for i, audio in enumerate(media.example_audios):
            name = f"{phrase_hash}_ex{i}.mp3"
            await self._anki_client.media.store_file(name, audio)
            example_audio_names.append(name)
        logger.debug(f"Stored {len(example_audio_names)} example audio(s)")

        return MediaReferences(
            phrase_audio=phrase_audio_name,
            example_audios=example_audio_names,
        )

    def _convert_to_note_type(
        self,
        phrase_model: PhraseModel,
        media_refs: MediaReferences,
    ) -> dict[str, str]:
        """Convert PhraseModel and media references to Anki note fields."""
        senses = [phrase_model.core_meaning, *phrase_model.supporting_meanings]
        return {
            "phrase": phrase_model.phrase,
            "pron_audio": f"[sound:{media_refs.phrase_audio}]",
            "difficulty": phrase_model.difficulty,
            "core_meaning": self._format_core_meaning(phrase_model.core_meaning),
            "sense_notes": self._format_sense_notes(phrase_model.supporting_meanings),
            "translations": self._format_translations(senses),
            "examples": self._format_examples(
                phrase_model.examples,
                media_refs.example_audios,
                phrase_model.phrase,
            ),
            "example_audio_refs": self._format_example_audio_refs(
                media_refs.example_audios
            ),
            "usage_pattern": self._format_text_block(phrase_model.usage_pattern),
            "confusions": self._format_bullets(phrase_model.confusions),
            "etymology_or_memory": self._format_text_block(
                phrase_model.etymology_or_memory
            ),
            "associations": self._format_chip_list(
                phrase_model.associations, "association"
            ),
            "production_hint": self._format_text_block(phrase_model.production_hint),
            "user_notes": "",
            "target_language": self._target_language.value,
        }

    def _format_core_meaning(self, sense: Sense) -> str:
        meaning = self._render_target_text(sense.target_text)
        native = html.escape(sense.native_text)
        return (
            "<div class='meaning-anchor'>"
            f"<div class='meaning-target'>{meaning}</div>"
            f"<div class='meaning-native'>{native}</div>"
            "</div>"
        )

    def _format_sense_notes(self, senses: list[Sense]) -> str:
        if not senses:
            return ""
        items = []
        for sense in senses:
            target = self._render_target_text(sense.target_text)
            native = html.escape(sense.native_text)
            items.append(
                "<div class='sense-note'>"
                f"<span class='sense-target'>{target}</span>"
                f"<span class='sense-native'>{native}</span>"
                "</div>"
            )
        return "".join(items)

    def _format_translations(self, senses: list[Sense]) -> str:
        supporting_senses = senses[1:] or senses[:1]
        entries = [
            html.escape(sense.native_text)
            for sense in supporting_senses
            if sense.native_text
        ]
        if not entries:
            return ""
        unique_entries = list(dict.fromkeys(entries))
        return " / ".join(unique_entries)

    def _format_examples(
        self,
        examples: list[Example],
        audio_refs: list[str],
        phrase: str,
    ) -> str:
        blocks: list[str] = []
        for index, example in enumerate(examples):
            sentence = self._strip_wrapping_quotes(example.sentence)
            # For phrases, highlights typically include the phrase itself;
            # we filter empty / non-matching entries
            highlights = self._filter_highlights(example.highlights, phrase)
            sentence_html = self._render_sentence(sentence, highlights)
            translation_html = html.escape(example.translation)
            audio_html = ""
            if index < len(audio_refs):
                audio_html = (
                    "<span class='example-audio inline-audio'>"
                    f"[sound:{audio_refs[index]}]"
                    "</span>"
                )
            blocks.append(
                "<article class='example-block'>"
                f"<div class='example-sentence'>{sentence_html}{audio_html}</div>"
                f"<div class='example-translation'>{translation_html}</div>"
                "</article>"
            )
        return "".join(blocks)

    def _format_example_audio_refs(self, audio_refs: list[str]) -> str:
        if not audio_refs:
            return ""
        return "".join(
            f"<span class='example-audio-ref'>[sound:{audio_ref}]</span>"
            for audio_ref in audio_refs
        )

    def _format_chip_list(self, items: list[str], css_class: str) -> str:
        if not items:
            return ""
        return "".join(
            f"<span class='{css_class}-chip'>{self._render_target_text(item)}</span>"
            for item in items
        )

    def _format_bullets(self, items: list[str]) -> str:
        if not items:
            return ""
        return "".join(f"<li>{self._render_mixed_text(item)}</li>" for item in items)

    def _format_text_block(self, value: str | None) -> str:
        if not value:
            return ""
        return self._render_target_text(value)

    def _strip_wrapping_quotes(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("「") and stripped.endswith("」"):
            return stripped.removeprefix("「").removesuffix("」")
        return value

    def _filter_highlights(self, highlights: list[str], phrase: str) -> list[str]:
        if self._target_language not in RUBY_ANNOTATION_LANGUAGES:
            return highlights
        return [
            highlight
            for highlight in highlights
            if strip_phonetic_annotations(highlight) != phrase
        ]

    def _render_target_text(self, value: str) -> str:
        if self._target_language in RUBY_ANNOTATION_LANGUAGES:
            return self._convert_target_lang_text(value)
        return html.escape(value)

    def _render_mixed_text(self, value: str) -> str:
        if (
            self._target_language in RUBY_ANNOTATION_LANGUAGES
            and "<" in value
            and ":" in value
        ):
            return self._convert_target_lang_text(value)
        return html.escape(value)

    def _render_sentence(self, sentence: str, highlights: list[str]) -> str:
        if self._target_language in RUBY_ANNOTATION_LANGUAGES:
            rendered = sentence
            for phrase in highlights:
                rendered = rendered.replace(
                    phrase,
                    f"<span class='example-highlight'>{phrase}</span>",
                )
            return self._convert_target_lang_text(rendered)

        rendered = html.escape(sentence)
        for phrase in highlights:
            escaped_phrase = html.escape(phrase)
            rendered = rendered.replace(
                escaped_phrase,
                f"<span class='example-highlight'>{escaped_phrase}</span>",
            )
        return rendered
