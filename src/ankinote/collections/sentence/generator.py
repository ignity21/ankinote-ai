"""Sentence card generator using AI."""

import json
from dataclasses import dataclass, field

from loguru import logger

from ankinote.collections.common import MediaGap, create_prompt_loader, synthesize_all
from ankinote.consts import Language
from ankinote.services.ai import DISABLE_REASONING, TextGenerationService
from ankinote.services.tts import SpeechSynthesizer

from .models import SentenceModel


@dataclass
class SentenceMediaFiles:
    """Media files generated for a single SentenceModel.

    Attributes:
        sentence_audio: MP3 bytes of the sentence; None without audio.
        gaps: why audio is missing, when it is.
    """

    sentence_audio: bytes | None
    gaps: list[MediaGap] = field(default_factory=list)


_LANGUAGE_TO_FILENAME: dict[Language, str] = {
    Language.ENGLISH: "latin_alphabet.md",
    Language.FRENCH: "latin_alphabet.md",
    Language.SPANISH: "latin_alphabet.md",
    Language.GERMAN: "latin_alphabet.md",
    Language.JAPANESE: "japanese.md",
    Language.CHINESE_S: "chinese.md",
    Language.CHINESE_T: "chinese.md",
    Language.KOREAN: "korean.md",
}

_load_prompt_template = create_prompt_loader(
    "ankinote.collections.sentence",
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


async def generate_sentence_data(
    target_sentence: str,
    target_language: Language,
    native_language: Language,
    text_service: TextGenerationService,
    model: str,
    temperature: float = 0.3,
    reasoning_effort: str | None = DISABLE_REASONING,
) -> SentenceModel:
    """Generate sentence card data via LLM.

    The *target_sentence* is provided in the language being learned; the model
    generates its native-language translation and useful learning notes.

    Extended model "thinking" is disabled by default to save tokens; the prompt
    is tightly specified and the output is short.
    """

    system_prompt = _load_prompt_template(target_language)
    user_message = (
        f"Target sentence: {target_sentence}\n"
        f"Target language: {target_language.value}\n"
        f"Native language: {native_language.value}"
    )

    logger.info(
        f"Generating sentence data for '{target_sentence}' "
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
            data = json.loads(_extract_json_payload(content))
        except json.JSONDecodeError as e:
            logger.exception("Failed to parse JSON response")
            logger.debug(f"Response content: {content[:500]}...")
            raise RuntimeError(f"AI returned invalid JSON: {e}") from e

        sentence_model = SentenceModel.model_validate(data)
        logger.success(f"Generated sentence model for '{target_sentence}'")
        return sentence_model

    except Exception as e:
        logger.error(f"Failed to generate sentence data for '{target_sentence}': {e}")
        raise


class SentenceGenerator:
    """Generator for sentence text data and associated audio."""

    def __init__(
        self,
        tts_service: SpeechSynthesizer | None,
        text_service: TextGenerationService,
        text_model: str,
    ) -> None:
        # None: cards are made without audio.
        self._text_service = text_service
        self._text_model = text_model
        self._tts_service = tts_service

    async def generate_sentence_data(
        self,
        target_sentence: str,
        target_lang: Language,
        native_lang: Language,
        temperature: float = 0.3,
        reasoning_effort: str | None = DISABLE_REASONING,
    ) -> SentenceModel:
        """Generate structured sentence data via LLM."""
        return await generate_sentence_data(
            target_sentence=target_sentence,
            target_language=target_lang,
            native_language=native_lang,
            text_service=self._text_service,
            model=self._text_model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    async def generate_media(
        self,
        sentence_model: SentenceModel,
        target_lang: Language,
    ) -> SentenceMediaFiles:
        """Generate the sentence's audio; without it, ``gaps`` says why."""
        target_sentence = sentence_model.target_sentence
        logger.info(f"Generating media for sentence '{target_sentence}'")
        audios, gaps = await synthesize_all(
            self._tts_service, [target_sentence], target_lang
        )
        return SentenceMediaFiles(
            sentence_audio=audios[0] if audios else None, gaps=gaps
        )
