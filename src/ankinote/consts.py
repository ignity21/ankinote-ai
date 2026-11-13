from enum import StrEnum
from typing import Literal


class Language(StrEnum):
    """Supported languages for translations and definitions."""

    ENGLISH = "English"
    CHINESE_S = "Chinese(Simplified)"
    CHINESE_T = "Chinese(Traditional)"
    JAPANESE = "Japanese"
    FRENCH = "French"
    SPANISH = "Spanish"
    GERMAN = "German"
    KOREAN = "Korean"
    OTHER = "other"


RUBY_ANNOTATION_LANGUAGES = {
    Language.JAPANESE,
    Language.CHINESE_S,
    Language.CHINESE_T,
    Language.KOREAN,
}

# Languages selectable as the "target" (language being learned): every
# collection's prompt templates must cover each of these. Keep in sync with
# the `_LANGUAGE_TO_FILENAME` maps in collections/{word,sentence,phrase}/generator.py.
TARGET_LANGUAGES = (
    Language.ENGLISH,
    Language.FRENCH,
    Language.SPANISH,
    Language.GERMAN,
    Language.JAPANESE,
)

# Languages selectable as "native" (the one cards explain in).
NATIVE_LANGUAGES = tuple(lang for lang in Language if lang is not Language.OTHER)

# Targets shown as beta until a competent reader has reviewed sample output
# (docs/plans/productization.md, Phase 2). Only members of TARGET_LANGUAGES
# are offered.
BETA_TARGET_LANGUAGES = frozenset({Language.KOREAN})

_CHINESE = frozenset({Language.CHINESE_S, Language.CHINESE_T})

type PairError = Literal["not_native", "not_target", "same_language"]


def language_pair_error(native: Language, target: Language) -> PairError | None:
    """Why ``native`` can't learn ``target``, or None if it can.

    Simplified and Traditional Chinese are distinct natives, but one language
    to learn: a reader of either doesn't learn the other here.
    """
    if native not in NATIVE_LANGUAGES:
        return "not_native"
    if native == target or {native, target} <= _CHINESE:
        return "same_language"
    if target not in TARGET_LANGUAGES:
        return "not_target"
    return None
