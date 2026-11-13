"""Common utilities for collection modules."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal, TypeVar, cast

from loguru import logger
from pydantic import BaseModel

from ankinote.consts import RUBY_ANNOTATION_LANGUAGES, Language
from ankinote.services.tts import SpeechSynthesizer


@dataclass(frozen=True)
class MediaGap:
    """Media a card goes without, and why; the card is still made.

    ``not_set_up``: no model for it. ``failed``: the model was asked and
    errored; ``detail`` carries its message.
    """

    kind: Literal["audio", "image"]
    reason: Literal["not_set_up", "failed"]
    detail: str = ""


def load_card_style(package: str) -> str:
    """Load the CSS styling for card templates.

    Args:
        package: The full package path containing card_templates
            (e.g., "ankinote.collections.word").

    Returns:
        The CSS content as a string.
    """
    return (
        files(f"{package}.card_templates")
        .joinpath("style.css")
        .read_text(encoding="utf-8")
    )


def load_template(package: str, filename: str) -> str:
    """Load an HTML template for cards.

    Args:
        package: The full package path containing card_templates
            (e.g., "ankinote.collections.word").
        filename: The name of the template file to load
            (e.g., "front.html" or "back.html").

    Returns:
        The template content as a string.
    """
    return (
        files(f"{package}.card_templates")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def load_prompt_template(
    package: str,
    target_language: Language,
    language_to_filename: dict[Language, str],
) -> str:
    """Load prompt template for the target language.

    Args:
        package: The full package path containing prompts
            (e.g., "ankinote.collections.word").
        target_language: The language being learned.
        language_to_filename: Mapping from Language to prompt filename.

    Returns:
        The prompt template content as a string.

    Raises:
        FileNotFoundError: If no prompt template exists for the language.
    """
    filename = language_to_filename.get(target_language)
    if filename is None:
        raise FileNotFoundError(
            f"No prompt template found for language: {target_language.value}. "
            f"Available languages: {list(language_to_filename.keys())}"
        )

    return files(f"{package}.prompts").joinpath(filename).read_text(encoding="utf-8")


# Type variable for Pydantic model types
T = TypeVar("T", bound=BaseModel)


def create_template_loader(
    package: str,
) -> tuple[
    Callable[[], str],
    Callable[[str], str],
]:
    """Create template loader functions for a specific package.

    Args:
        package: The full package path (e.g., "ankinote.collections.word").

    Returns:
        A tuple of (load_card_style, load_template) functions bound to the package.
    """

    def _load_card_style() -> str:
        return load_card_style(package)

    def _load_template(filename: str) -> str:
        return load_template(package, filename)

    return _load_card_style, _load_template


def create_prompt_loader[KT](
    package: str,
    key_to_filename: dict[KT, str],
) -> Callable[[KT], str]:
    """Create a prompt loader function for a specific package.

    Args:
        package: The full package path (e.g., "ankinote.collections.word").
        key_to_filename: Mapping from key (Language, CardType, etc.) to prompt filename.

    Returns:
        A function that loads prompt templates for a given key.
    """

    def _load_prompt(key: KT) -> str:
        filename = key_to_filename.get(key)
        if filename is None:
            raise FileNotFoundError(
                f"No prompt template found for key: {key}. "
                f"Available keys: {list(key_to_filename.keys())}"
            )

        return (
            files(f"{package}.prompts").joinpath(filename).read_text(encoding="utf-8")
        )

    return _load_prompt


_ANGLED_PHONETIC_PATTERN = re.compile(r"<([^:>]+):([^>]+)>")  # <汉:hàn>
_INLINE_PHONETIC_PATTERN = re.compile(r"([一-龯々ヶヵ]+)<([^:>]+)>")  # 漢<かん>


def strip_phonetic_annotations(text: str) -> str:
    """Strip angled-style phonetic annotations to get plain text (e.g., for TTS).

    Examples:
      - Japanese:  <食:た>べる  →  食べる
      - Chinese:   <汉:hàn><字:zì>  →  汉字
      - Bopomofo:  <你:ㄋㄧˇ>  →  你

    Args:
        text: Text containing angled-style phonetic annotations.

    Returns:
        Plain text with all phonetic annotations and brackets removed.
    """
    text = _INLINE_PHONETIC_PATTERN.sub(r"\1", text)
    return _ANGLED_PHONETIC_PATTERN.sub(r"\1", text)


def convert_to_html_ruby(text: str) -> str:
    """Convert angled-style phonetic annotations to HTML ruby tags."""
    text = _INLINE_PHONETIC_PATTERN.sub(r"<ruby>\1<rt>\2</rt></ruby>", text)
    return _ANGLED_PHONETIC_PATTERN.sub(r"<ruby>\1<rt>\2</rt></ruby>", text)


async def synthesize_all(
    tts: SpeechSynthesizer | None, texts: list[str], target_lang: Language
) -> tuple[list[bytes], list[MediaGap]]:
    """Audio for every text, or none and the gap that says why.

    All or nothing: a card with half its audio has example buttons that play
    nothing, which is worse than no buttons.
    """
    if tts is None:
        return [], [MediaGap("audio", "not_set_up")]
    if target_lang in RUBY_ANNOTATION_LANGUAGES:
        texts = [strip_phonetic_annotations(text) for text in texts]
    results = await asyncio.gather(
        *(tts.synthesize(text) for text in texts), return_exceptions=True
    )
    for result in results:
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result
            logger.warning(f"Speech failed, card made without audio: {result}")
            return [], [MediaGap("audio", "failed", str(result))]
    return cast(list[bytes], results), []


class AudioUnavailable(Exception):
    """An edit needs new audio that can't be made; the card is left as it was.

    ``reason`` is ``not_set_up`` (no speech model) or ``failed``.
    """

    def __init__(
        self, reason: Literal["not_set_up", "failed"], detail: str = ""
    ) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


async def respeak(
    tts: SpeechSynthesizer | None,
    clips: dict[str, bytes],
    texts: list[str],
    target_lang: Language,
) -> list[bytes]:
    """Audio for ``texts``, reusing ``clips`` (by text) and making only the rest.

    Raises:
        AudioUnavailable: a text has no clip and none can be made. An edited
            card never silently loses the audio it had.
    """
    missing = [text for text in dict.fromkeys(texts) if text not in clips]
    if missing:
        if tts is None:
            raise AudioUnavailable("not_set_up")
        made, gaps = await synthesize_all(tts, missing, target_lang)
        if gaps:
            raise AudioUnavailable("failed", gaps[0].detail)
        clips = {**clips, **dict(zip(missing, made, strict=True))}
    return [clips[text] for text in texts]
