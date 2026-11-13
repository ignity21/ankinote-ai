"""Independent STEM generation schemas and their Anki storage fields."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ankinote.collections.editing import Form, Lines, Rows, Text


class CardType(StrEnum):
    CONCEPT = "concept"
    FORMULA = "formula"
    PROCEDURE = "procedure"
    EXAMPLE = "example"


class CardContent(BaseModel):
    """Common generation metadata, not an Anki note type."""

    model_config = ConfigDict(
        extra="forbid", coerce_numbers_to_str=True, str_strip_whitespace=True
    )
    front: str = Field(min_length=1)
    tags: list[str]
    image_description: str | None = None


class Variable(BaseModel):
    symbol: str
    description: str


class ConceptModel(CardContent):
    card_type: Literal[CardType.CONCEPT] = CardType.CONCEPT
    back_brief: str = Field(min_length=1)
    back_detail: str = ""


class FormulaModel(CardContent):
    card_type: Literal[CardType.FORMULA] = CardType.FORMULA
    latex: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    variables: list[Variable] = Field(default_factory=list)
    conditions: str = ""
    derivation: str = ""


class ProcedureModel(CardContent):
    card_type: Literal[CardType.PROCEDURE] = CardType.PROCEDURE
    summary: str = Field(min_length=1)
    steps: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    conditions: str = ""


class ExampleModel(CardContent):
    card_type: Literal[CardType.EXAMPLE] = CardType.EXAMPLE
    answer: str = Field(min_length=1)
    steps: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    explanation: str = ""


type StemCard = ConceptModel | FormulaModel | ProcedureModel | ExampleModel

CARD_ADAPTER: TypeAdapter[StemCard] = TypeAdapter(
    Annotated[StemCard, Field(discriminator="card_type")]
)
MODEL_TYPES: dict[
    CardType, type[ConceptModel | FormulaModel | ProcedureModel | ExampleModel]
] = {
    CardType.CONCEPT: ConceptModel,
    CardType.FORMULA: FormulaModel,
    CardType.PROCEDURE: ProcedureModel,
    CardType.EXAMPLE: ExampleModel,
}

# Structured lists render into their own fields. Tags use Anki's native store.
NOTE_FIELDS: dict[CardType, tuple[str, ...]] = {
    CardType.CONCEPT: ("front", "back_brief", "back_detail", "image"),
    CardType.FORMULA: (
        "front",
        "latex",
        "meaning",
        "variables",
        "conditions",
        "derivation",
        "image",
    ),
    CardType.PROCEDURE: ("front", "summary", "steps", "conditions", "image"),
    CardType.EXAMPLE: ("front", "answer", "steps", "explanation", "image"),
}


# What a user may change before saving, in the order the card shows it. The
# image prompt isn't offered: a new diagram means rewriting the card.
EDIT_FORMS: dict[CardType, Form] = {
    CardType.CONCEPT: (
        Text("front", multiline=True),
        Text("back_brief", multiline=True),
        Text("back_detail", multiline=True),
        Lines("tags"),
    ),
    CardType.FORMULA: (
        Text("front", multiline=True),
        Text("latex", multiline=True),
        Text("meaning", multiline=True),
        Rows("variables", ("symbol", "description")),
        Text("conditions", multiline=True),
        Text("derivation", multiline=True),
        Lines("tags"),
    ),
    CardType.PROCEDURE: (
        Text("front", multiline=True),
        Text("summary", multiline=True),
        Lines("steps"),
        Text("conditions", multiline=True),
        Lines("tags"),
    ),
    CardType.EXAMPLE: (
        Text("front", multiline=True),
        Text("answer", multiline=True),
        Lines("steps"),
        Text("explanation", multiline=True),
        Lines("tags"),
    ),
}


def note_type_name(card_type: CardType) -> str:
    """Return the stable, unversioned Anki note type name."""
    return f"AINote STEM {card_type.title()}"
