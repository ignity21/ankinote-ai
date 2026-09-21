"""Phrase / idiom / sentence card data models for Anki V2."""

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator


class Sense(BaseModel):
    """A compact sense summary used to build learning-oriented cards."""

    target_text: str
    native_text: str


class Example(BaseModel):
    """A high-value example sentence with a concise explanation."""

    sentence: str
    translation: str
    highlights: list[str] = Field(default_factory=list)


class PhraseModel(BaseModel):
    """Structured phrase/idiom model for AI generation.

    Mirrors WordModel's structure: core meaning + supporting meanings,
    example highlights list, usage pattern, production hint, confusions,
    and etymology/memory hook.
    """

    phrase: str
    difficulty: str
    core_meaning: Sense
    supporting_meanings: list[Sense] = Field(default_factory=list, max_length=2)
    examples: list[Example] = Field(default_factory=list, min_length=1, max_length=3)
    usage_pattern: str | None = None
    production_hint: str | None = None
    confusions: list[str] = Field(default_factory=list, max_length=2)
    etymology_or_memory: str | None = None
    associations: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_content(self) -> PhraseModel:
        """Ensure the core sense is not duplicated in supporting meanings."""
        normalized_core = (
            self.core_meaning.target_text.strip(),
            self.core_meaning.native_text.strip(),
        )
        supporting_pairs = {
            (sense.target_text.strip(), sense.native_text.strip())
            for sense in self.supporting_meanings
        }
        if normalized_core in supporting_pairs:
            msg = "supporting_meanings must not duplicate core_meaning"
            raise ValueError(msg)
        return self


@dataclass
class PhraseNoteType:
    """Anki note fields for the phrase V2 note type."""

    phrase: str
    pron_audio: str
    difficulty: str
    core_meaning: str
    sense_notes: str
    translations: str
    examples: str
    example_audio_refs: str
    usage_pattern: str
    confusions: str
    etymology_or_memory: str
    associations: str
    production_hint: str
    user_notes: str
    target_language: str
