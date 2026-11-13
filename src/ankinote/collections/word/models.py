"""Vocabulary card data models for the word v2 collection."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from ankinote.collections.editing import Form, Lines, Rows, Text


class Sense(BaseModel):
    """A compact sense summary used to build learning-oriented cards."""

    target_text: str
    native_text: str
    image_prompt: str | None = None
    is_visualizable: bool = False


class Example(BaseModel):
    """A high-value example sentence with a concise explanation."""

    sentence: str
    translation: str
    highlights: list[str] = Field(default_factory=list)


class WordModel(BaseModel):
    """Structured data returned by the LLM for a single lemma + POS note."""

    lemma: str
    part_of_speech: str
    pronunciation: str | None = None
    difficulty: str
    morphology: str | None = None
    core_meaning: Sense
    examples: list[Example] = Field(default_factory=list, min_length=1, max_length=2)
    collocations: list[str] = Field(default_factory=list, max_length=4)
    confusions: list[str] = Field(default_factory=list, max_length=2)
    etymology_or_memory: str | None = None


# What a user may change before saving, in the order the card shows it.
EDIT_FORM: Form = (
    Text("pronunciation"),
    Text("difficulty"),
    Text("core_meaning.target_text", multiline=True),
    Text("core_meaning.native_text"),
    Text("morphology"),
    Rows("examples", ("sentence", "translation")),
    Lines("collocations"),
    Lines("confusions"),
    Text("etymology_or_memory", multiline=True),
)


@dataclass
class WordNoteType:
    """Anki note fields for the word v2 note type."""

    lemma: str
    part_of_speech: str
    pronunciation: str
    headword_audio: str
    difficulty: str
    morphology: str
    core_meaning: str
    examples: str
    example_audio_refs: str
    collocations: str
    confusions: str
    etymology_or_memory: str
    image_refs: str
    user_notes: str
    target_language: str
