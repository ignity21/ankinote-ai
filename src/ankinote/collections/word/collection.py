"""Word collection management for Anki."""

import dataclasses
import hashlib
import html
from dataclasses import dataclass
from typing import Self

from loguru import logger

from ankinote.collections.common import convert_to_html_ruby, strip_phonetic_annotations
from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.ai import ImageGenerationService, TextGenerationService
from ankinote.services.anki import AnkiCollectionClient, TemplateUpsert
from ankinote.services.tts import GoogleTTSService, TTS_LANG_CODES

from .generator import WordGenerator, WordMediaFiles
from .models import Example, Sense, WordModel, WordNoteType
from .templates import load_card_style, load_template


@dataclass
class WordCardData:
    """Complete card data including model and generated media."""

    model: WordModel
    media: WordMediaFiles


@dataclass
class MediaReferences:
    """References to media files stored in Anki."""

    headword_audio: str
    example_audios: list[str]
    images: dict[int, str]


class WordCollection:
    """Manages vocabulary word notes in Anki."""

    def __init__(
        self,
        anki_client: AnkiCollectionClient,
        *,
        native_language: Language,
        target_language: Language,
        notetype_name: str = "AINote Word V2",
        deck_name: str = "AINote::Words",
        text_model_id: str,
        text_service: TextGenerationService,
        image_service: ImageGenerationService | None,
    ) -> None:
        self.notetype_name = notetype_name
        self.deck_name = deck_name
        self._native_language = native_language
        self._target_language = target_language
        self._anki_client = anki_client
        self._tts_service = GoogleTTSService(TTS_LANG_CODES[target_language])
        self._generator = WordGenerator(
            tts_service=self._tts_service,
            text_service=text_service,
            image_service=image_service,
            text_model_id=text_model_id,
        )
        if target_language in RUBY_ANNOTATION_LANGUAGES:
            self._convert_target_lang_text = convert_to_html_ruby
        else:
            self._convert_target_lang_text = lambda value: value

    async def __aenter__(self) -> Self:
        await self._tts_service.warmup()
        await self._ensure_note_type_exists()
        await self._ensure_deck_exists()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._tts_service.clear_cache()

    async def _ensure_note_type_exists(self) -> None:
        fields = [field.name for field in dataclasses.fields(WordNoteType)]
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
            {
                "Name": "Spelling",
                "Front": load_template("spelling_front.html"),
                "Back": load_template("spelling_back.html"),
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
        deck_id = await self._anki_client.decks.create(self.deck_name)
        logger.success(f"Ensured deck exists: {self.deck_name}")
        return deck_id

    async def generate_and_add_note(
        self,
        word: str,
        tags: list[str] | None = None,
    ) -> list[int]:
        logger.info(f"Starting generation for word: {word}")
        word_models = await self._generate_word_models(word)

        note_ids: list[int] = []
        for word_model in word_models:
            media = await self._generator.generate_media(
                word_model=word_model,
                target_lang=self._target_language,
            )
            card_data = WordCardData(model=word_model, media=media)
            note_ids.append(
                await self._add_or_update_note(
                    card_data=card_data,
                    tags=tags or [self._target_language.value, "AI-generated", "Word"],
                )
            )

        logger.success(
            f"Completed generation for '{word}': {len(note_ids)} note(s) created/updated"
        )
        return note_ids

    async def _generate_word_models(self, word: str) -> list[WordModel]:
        return await self._generator.generate_word_data(
            word=word,
            target_lang=self._target_language,
            native_lang=self._native_language,
        )

    async def _add_or_update_note(
        self,
        card_data: WordCardData,
        tags: list[str],
    ) -> int:
        word_model = card_data.model
        logger.info(
            f"Adding/updating note {word_model.lemma} "
            f"({word_model.part_of_speech}) to {self.deck_name}"
        )

        media_refs = await self._store_media_files(card_data)
        note_data = self._convert_to_note_type(word_model, media_refs)
        note_id = await self._anki_client.notes.find(
            deck_name=self.deck_name,
            unique_fields={
                "lemma": word_model.lemma,
                "part_of_speech": word_model.part_of_speech,
            },
        )

        if note_id is not None:
            await self._anki_client.notes.update_fields(note_id, note_data)
            await self._anki_client.notes.update_tags(note_id, tags)
            logger.info(f"Updated note {note_id}")
            return note_id

        note_id = await self._anki_client.notes.add(
            deck_name=self.deck_name,
            model_name=self.notetype_name,
            fields=note_data,
            tags=tags,
            allow_duplicate=True,
        )
        logger.info(f"Created note {note_id}")
        return note_id

    async def _store_media_files(self, card_data: WordCardData) -> MediaReferences:
        word_model = card_data.model
        media = card_data.media
        word_base = f"{word_model.lemma}_{word_model.part_of_speech}"
        word_hash = hashlib.md5(word_base.encode()).hexdigest()[:12]

        headword_audio_name = f"{word_hash}.mp3"
        await self._anki_client.media.store_file(
            headword_audio_name, media.headword_audio
        )

        example_audio_names: list[str] = []
        for index, audio in enumerate(media.example_audios):
            name = f"{word_hash}_ex{index}.mp3"
            await self._anki_client.media.store_file(name, audio)
            example_audio_names.append(name)

        image_names: dict[int, str] = {}
        for index, image in media.images.items():
            name = f"{word_hash}_img{index}.png"
            await self._anki_client.media.store_file(name, image)
            image_names[index] = name

        return MediaReferences(
            headword_audio=headword_audio_name,
            example_audios=example_audio_names,
            images=image_names,
        )

    def _convert_to_note_type(
        self,
        word_model: WordModel,
        media_refs: MediaReferences,
    ) -> dict[str, str]:
        senses = [word_model.core_meaning, *word_model.supporting_meanings]
        return {
            "lemma": word_model.lemma,
            "part_of_speech": word_model.part_of_speech,
            "pronunciation": word_model.pronunciation or "",
            "headword_audio": f"[sound:{media_refs.headword_audio}]",
            "difficulty": word_model.difficulty,
            "morphology": self._format_text_block(word_model.morphology),
            "core_meaning": self._format_core_meaning(word_model.core_meaning),
            "sense_notes": self._format_sense_notes(word_model.supporting_meanings),
            "translations": self._format_translations(senses),
            "examples": self._format_examples(
                word_model.examples,
                media_refs.example_audios,
                word_model.lemma,
            ),
            "example_audio_refs": self._format_example_audio_refs(
                media_refs.example_audios
            ),
            "collocations": self._format_chip_list(
                word_model.collocations, "collocation"
            ),
            "confusions": self._format_bullets(word_model.confusions),
            "etymology_or_memory": self._format_text_block(
                word_model.etymology_or_memory
            ),
            "image_refs": self._format_image_refs(senses, media_refs.images),
            "production_hint": self._format_text_block(word_model.production_hint),
            "user_notes": "",
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
        lemma: str,
    ) -> str:
        blocks: list[str] = []
        for index, example in enumerate(examples):
            sentence = self._strip_wrapping_quotes(example.sentence)
            highlights = self._filter_highlights(example.highlights, lemma)
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

    def _format_image_refs(
        self, senses: list[Sense], image_refs: dict[int, str]
    ) -> str:
        blocks: list[str] = []
        for index, image_ref in image_refs.items():
            if index >= len(senses):
                continue
            blocks.append(
                f"<img class='sense-image' src='{image_ref}' alt='sense image {index + 1}'>"
            )
        return "".join(blocks)

    def _format_text_block(self, value: str | None) -> str:
        if not value:
            return ""
        return self._render_target_text(value)

    def _strip_wrapping_quotes(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("「") and stripped.endswith("」"):
            return stripped.removeprefix("「").removesuffix("」")
        return value

    def _filter_highlights(self, highlights: list[str], lemma: str) -> list[str]:
        if self._target_language not in RUBY_ANNOTATION_LANGUAGES:
            return highlights
        return [
            highlight
            for highlight in highlights
            if strip_phonetic_annotations(highlight) != lemma
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
