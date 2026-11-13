"""Sentence card data models for Anki."""

from dataclasses import dataclass

from pydantic import BaseModel

from ankinote.collections.editing import Form, Lines, Rows, Text


class PhraseModel(BaseModel):
    """Structured phrase model for AI generation.

    The phrase collection is for translation-style cards:
    front shows the native language phrase, back shows the target language.
    """

    phrase: str
    translation: str
    example: str


class SentenceModel(BaseModel):
    """Structured sentence model for AI generation.

    The sentence collection is for production-style cards. The learner submits
    a target-language sentence; the front shows its native-language translation
    and the back shows the target-language sentence with learning notes.
    """

    target_sentence: str
    native_sentence: str
    notes: list[str] = []
    phrases: list[PhraseModel] = []


# What a user may change before saving, in the order the card shows it.
EDIT_FORM: Form = (
    Text("native_sentence", multiline=True),
    Rows("phrases", ("phrase", "translation", "example")),
    Lines("notes"),
)


@dataclass
class SentenceNoteType:
    """Anki note type for sentence cards (all string fields)."""

    target_sentence: str
    native_sentence: str
    pron_audio: str
    notes: str
    phrases: str
    user_notes: str
    target_language: str
