"""Word vocabulary card generator using AI."""

import asyncio
import json
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from typing import cast

from loguru import logger

from ankinote.collections.common import (
    MediaGap,
    create_prompt_loader,
    synthesize_all,
)
from ankinote.consts import Language
from ankinote.services.ai import (
    DISABLE_REASONING,
    ImageGenerationService,
    TextGenerationService,
)
from ankinote.services.tts import SpeechSynthesizer

from .models import Sense, WordModel


@dataclass
class WordMediaFiles:
    """Media files generated for a single WordModel.

    Audio is all or nothing: ``headword_audio`` is None and
    ``example_audios`` empty when speech is off or failed; ``gaps`` says so.
    """

    headword_audio: bytes | None
    example_audios: list[bytes] = field(default_factory=list)
    images: dict[int, bytes] = field(default_factory=dict)
    gaps: list[MediaGap] = field(default_factory=list)


_LANGUAGE_TO_FILENAME: dict[Language, str] = {
    Language.ENGLISH: "latin_alphabet.md",
    Language.FRENCH: "latin_alphabet.md",
    Language.SPANISH: "latin_alphabet.md",
    Language.GERMAN: "latin_alphabet.md",
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


@cache
def _image_style() -> str:
    return (
        files("ankinote.collections.word.prompts")
        .joinpath("image.md")
        .read_text(encoding="utf-8")
        .strip()
    )


def build_image_prompt(sense: Sense) -> str | None:
    """Return the image-model prompt for a sense, or None when it has no scene.

    The prompt is a plain visual description followed by a fixed style suffix.
    Neither the lemma nor any instruction text is included: Flux-style models
    render words they see and cannot follow negations like "no text".
    """
    scene = (sense.image_prompt or "").strip().rstrip(".")
    if not scene:
        return None
    return f"{scene}. {_image_style()}"


async def generate_word_data(
    word: str,
    target_language: Language,
    native_language: Language,
    text_service: TextGenerationService,
    model: str,
    temperature: float = 0.3,
    reasoning_effort: str | None = DISABLE_REASONING,
) -> list[WordModel]:
    """Generate vocabulary card data for a word using AI.

    Extended model "thinking" is disabled by default: the prompt is tightly
    specified and the output is short, so it adds little but costs tokens.
    """
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
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

        logger.debug(content)
        logger.info(f"Raw AI response length: {len(content)} characters")

        try:
            loaded = json.loads(_extract_json_payload(content))
        except json.JSONDecodeError as exc:
            logger.exception("Failed to parse JSON response")
            logger.debug(f"Response content: {content[:500]}...")
            raise RuntimeError(f"AI returned invalid JSON: {exc}") from exc

        # The prompt asks for a JSON array, but the model occasionally returns a
        # single record object; accept both rather than failing the run.
        if isinstance(loaded, dict):
            loaded = [loaded]
        data = cast(list[object], loaded)

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
        tts_service: SpeechSynthesizer | None,
        text_service: TextGenerationService,
        image_service: ImageGenerationService | None,
        text_model: str,
    ) -> None:
        self._text_service = text_service
        self._image_service = image_service
        self._text_model = text_model
        self._tts_service = tts_service

    async def generate_word_data(
        self,
        word: str,
        target_lang: Language,
        native_lang: Language,
        temperature: float = 0.3,
        reasoning_effort: str | None = DISABLE_REASONING,
    ) -> list[WordModel]:
        """Generate structured word data via LLM."""
        return await generate_word_data(
            word=word,
            target_language=target_lang,
            native_language=native_lang,
            text_service=self._text_service,
            model=self._text_model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    async def generate_media(
        self,
        word_model: WordModel,
        target_lang: Language,
    ) -> WordMediaFiles:
        """Generate audio and optional images for a WordModel.

        Media never fails the card: what can't be made is left out and
        recorded in ``gaps``.
        """
        logger.info(
            f"Generating media for '{word_model.lemma}' ({word_model.part_of_speech})"
        )
        texts = [
            word_model.lemma,
            *(example.sentence for example in word_model.examples),
        ]
        (audios, audio_gaps), (images, image_gaps) = await asyncio.gather(
            synthesize_all(self._tts_service, texts, target_lang),
            self._generate_images(word_model),
        )
        logger.success(
            f"Media ready for '{word_model.lemma}': "
            f"{len(audios)} audio clip(s), {len(images)} image(s)"
        )
        return WordMediaFiles(
            headword_audio=audios[0] if audios else None,
            example_audios=audios[1:],
            images=images,
            gaps=[*audio_gaps, *image_gaps],
        )

    async def _generate_images(
        self, word_model: WordModel
    ) -> tuple[dict[int, bytes], list[MediaGap]]:
        image_service = self._image_service
        if image_service is None:
            return {}, []
        prompts: dict[int, str] = {}
        for idx, sense in enumerate([word_model.core_meaning]):
            if not sense.is_visualizable:
                continue
            prompt = build_image_prompt(sense)
            if prompt is None:
                logger.warning(
                    f"Skipping image for '{word_model.lemma}' sense[{idx}]: no image_prompt"
                )
                continue
            prompts[idx] = prompt
        results = await asyncio.gather(
            *(image_service.generate_image(prompt=p) for p in prompts.values()),
            return_exceptions=True,
        )
        images: dict[int, bytes] = {}
        gaps: list[MediaGap] = []
        for idx, result in zip(prompts, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                logger.warning(
                    f"Image failed for '{word_model.lemma}' sense[{idx}]: {result}"
                )
                gap = MediaGap("image", "failed", str(result))
                if gap not in gaps:
                    gaps.append(gap)
            else:
                images[idx] = result
        return images, gaps
