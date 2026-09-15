from enum import StrEnum


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
