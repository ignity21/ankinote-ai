"""Word vocabulary card generator using AI."""

import asyncio
import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import cast

from loguru import logger

from ankinote.collections.common import create_prompt_loader, strip_phonetic_annotations
from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.ai import ImageGenerationService, TextGenerationService
from ankinote.services.tts import SpeechSynthesizer

from .models import Sense, WordModel


@dataclass
class WordMediaFiles:
    """Media files generated for a single WordModel."""

    headword_audio: bytes
    example_audios: list[bytes] = field(default_factory=list)
    images: dict[int, bytes] = field(default_factory=dict)


_LANGUAGE_TO_FILENAME: dict[Language, str] = {
    Language.ENGLISH: "english_us.md",
    Language.JAPANESE: "japanese.md",
}

_load_prompt_template = create_prompt_loader(
    "ankinote.collections.word",
    _LANGUAGE_TO_FILENAME,
)


def _extract_json_payload(content: str) -> str:
    """Extract a JSON payload from common fenced LLM output."""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _build_image_user_prompt(lemma: str, sense: Sense) -> str:
    return (
        f"Lemma: {lemma}\n"
        f"Target-language meaning: {sense.target_text}\n"
        f"Native-language meaning: {sense.native_text}"
    )


async def generate_word_data(
    word: str,
    target_language: Language,
    native_language: Language,
    text_service: TextGenerationService,
    model_id: str,
    temperature: float = 0.3,
) -> list[WordModel]:
    """Generate vocabulary card data for a word using AI."""
    system_prompt = _load_prompt_template(target_language)
    user_message = (
        f"Word: {word}\n"
        f"Target language: {target_language.value}\n"
        f"Native language: {native_language.value}\n"
        "Goal: Create concise Anki cards optimized for recognition, recall, and spelling."
    )

    logger.info(
        f"Generating word data for '{word}' "
        f"(target: {target_language.value}, native: {native_language.value})"
    )

    try:
        content = await text_service.generate_text(
            model_id=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
        )
        content = cast(str, content)

        logger.debug(content)
        logger.info(f"Raw AI response length: {len(content)} characters")

        try:
            loaded = json.loads(_extract_json_payload(content))
            data = cast(list[object], loaded)
        except json.JSONDecodeError as exc:
            logger.exception("Failed to parse JSON response")
            logger.debug(f"Response content: {content[:500]}...")
            raise RuntimeError(f"AI returned invalid JSON: {exc}") from exc

        word_models = [WordModel.model_validate(item) for item in data]

        logger.success(
            f"Generated {len(word_models)} word model(s) for '{word}' "
            f"with part(s) of speech: {[m.part_of_speech for m in word_models]}"
        )
        return word_models
    except Exception as exc:
        logger.error(f"Failed to generate word data for '{word}': {exc}")
        raise


class WordGenerator:
    """Unified generator for word text data and associated media."""

    def __init__(
        self,
        tts_service: SpeechSynthesizer,
        text_service: TextGenerationService,
        image_service: ImageGenerationService | None,
        text_model_id: str,
    ) -> None:
        self._text_service = text_service
        self._image_service = image_service
        self._text_model_id = text_model_id
        self._tts_service = tts_service

    async def generate_word_data(
        self,
        word: str,
        target_lang: Language,
        native_lang: Language,
        temperature: float = 0.3,
    ) -> list[WordModel]:
        """Generate structured word data via LLM."""
        return await generate_word_data(
            word=word,
            target_language=target_lang,
            native_language=native_lang,
            text_service=self._text_service,
            model_id=self._text_model_id,
            temperature=temperature,
        )

    async def generate_media(
        self,
        word_model: WordModel,
        target_lang: Language,
    ) -> WordMediaFiles:
        """Generate audio and optional images for a WordModel."""
        logger.info(
            f"Generating media for '{word_model.lemma}' ({word_model.part_of_speech})"
        )

        headword_audio = await self._generate_audio(word_model.lemma, target_lang)
        senses = [word_model.core_meaning, *word_model.supporting_meanings]

        try:
            async with asyncio.TaskGroup() as tg:
                example_tasks = [
                    tg.create_task(self._generate_audio(example.sentence, target_lang))
                    for example in word_model.examples
                ]
                image_tasks: dict[int, asyncio.Task[bytes]] = {}
                if self._image_service is not None:
                    image_tasks = {
                        idx: tg.create_task(self._generate_image(word_model.lemma, sense))
                        for idx, sense in enumerate(senses)
                        if sense.is_visualizable
                    }
        except* Exception as exc_group:
            for sub_exc in exc_group.exceptions:
                logger.error(
                    f"Error during media generation for '{word_model.lemma}': {sub_exc}",
                    exc_info=sub_exc,
                )
            raise RuntimeError(f"Media generation failed: {exc_group}") from exc_group

        example_audios = [task.result() for task in example_tasks]
        images: dict[int, bytes] = {}

        for idx, task in image_tasks.items():
            try:
                images[idx] = task.result()
                logger.debug(f"Generated image for sense[{idx}]")
            except Exception as exc:
                logger.warning(
                    f"Image generation failed for '{word_model.lemma}' sense[{idx}]: {exc}"
                )

        logger.success(
            f"Media ready for '{word_model.lemma}': "
            f"1 headword audio, {len(example_audios)} example(s), {len(images)} image(s)"
        )

        return WordMediaFiles(
            headword_audio=headword_audio,
            example_audios=example_audios,
            images=images,
        )

    async def _generate_audio(self, text: str, target_lang: Language) -> bytes:
        if target_lang in RUBY_ANNOTATION_LANGUAGES:
            text = strip_phonetic_annotations(text)
        return await self._tts_service.synthesize(text)

    async def _generate_image(self, lemma: str, sense: Sense) -> bytes:
        system_prompt = (
            files("ankinote.collections.word.prompts")
            .joinpath("image.md")
            .read_text(encoding="utf-8")
        )
        user_prompt = _build_image_user_prompt(lemma, sense)
        return await self._image_service.generate_image(
            prompt=f"{system_prompt}\n\n{user_prompt}",
        )
