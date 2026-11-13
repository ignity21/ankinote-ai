"""The editable form of a generated card: what it offers and what it accepts."""

import pytest

from ankinote.collections.editing import EditError, describe, revise
from ankinote.collections.phrase.models import EDIT_FORM as PHRASE_FORM
from ankinote.collections.phrase.models import PhraseModel
from ankinote.collections.sentence.models import EDIT_FORM as SENTENCE_FORM
from ankinote.collections.sentence.models import SentenceModel
from ankinote.collections.word.models import EDIT_FORM as WORD_FORM
from ankinote.collections.word.models import WordModel


def _moon() -> WordModel:
    return WordModel.model_validate(
        {
            "lemma": "moon",
            "part_of_speech": "noun",
            "pronunciation": "/muːn/",
            "difficulty": "A1",
            "core_meaning": {
                "target_text": "the natural satellite of the Earth",
                "native_text": "月亮",
                "image_prompt": "A full moon over a lake",
                "is_visualizable": True,
            },
            "examples": [
                {
                    "sentence": "The moon is bright tonight.",
                    "translation": "今晚月亮很亮。",
                    "highlights": ["moon"],
                },
                {
                    "sentence": "We walked under the moon.",
                    "translation": "我们在月光下散步。",
                    "highlights": ["moon"],
                },
            ],
            "collocations": ["full moon"],
        }
    )


def _field(model: WordModel, key: str) -> dict:
    return next(f for f in describe(model, WORD_FORM) if f["key"] == key)


def test_the_form_carries_values_and_limits_from_the_model() -> None:
    model = _moon()

    assert _field(model, "pronunciation") == {
        "key": "pronunciation",
        "type": "text",
        "required": False,
        "value": "/muːn/",
    }
    assert _field(model, "core_meaning.target_text") == {
        "key": "core_meaning.target_text",
        "type": "area",
        "required": True,
        "value": "the natural satellite of the Earth",
    }
    assert _field(model, "etymology_or_memory")["value"] == ""
    assert _field(model, "collocations") == {
        "key": "collocations",
        "type": "lines",
        "min": 0,
        "max": 4,
        "value": ["full moon"],
    }
    examples = _field(model, "examples")
    assert (examples["min"], examples["max"]) == (1, 2)
    assert examples["columns"] == ["sentence", "translation"]
    assert examples["value"][1] == {
        "id": 1,
        "cells": {
            "sentence": "We walked under the moon.",
            "translation": "我们在月光下散步。",
        },
    }


def test_what_names_the_note_is_not_offered() -> None:
    keys = {f["key"] for f in describe(_moon(), WORD_FORM)}

    assert not keys & {"lemma", "part_of_speech", "core_meaning.image_prompt"}


def test_every_form_matches_its_model() -> None:
    phrase = PhraseModel.model_validate(
        {
            "phrase": "take off",
            "difficulty": "B1",
            "core_meaning": {
                "target_text": "to leave the ground",
                "native_text": "起飞",
            },
            "examples": [
                {"sentence": "It takes off at six.", "translation": "六点起飞。"}
            ],
        }
    )
    sentence = SentenceModel(
        target_sentence="I overslept.", native_sentence="我睡过头了。", notes=["a"]
    )

    assert [f["key"] for f in describe(phrase, PHRASE_FORM)][:2] == [
        "difficulty",
        "core_meaning.target_text",
    ]
    assert {f["key"] for f in describe(sentence, SENTENCE_FORM)} == {
        "native_sentence",
        "phrases",
        "notes",
    }
    # Applying a form's own values changes nothing.
    for model, form in ((phrase, PHRASE_FORM), (sentence, SENTENCE_FORM)):
        values = {f["key"]: f["value"] for f in describe(model, form)}
        assert revise(model, form, values) == model


def test_revise_applies_text_lines_and_rows() -> None:
    revised = revise(
        _moon(),
        WORD_FORM,
        {
            "pronunciation": "  ",
            "core_meaning.native_text": " 月球 ",
            "collocations": ["new moon", "", "  half moon "],
            "examples": [
                {
                    "id": 1,
                    "cells": {
                        "sentence": "We sat under the moon.",
                        "translation": "月下",
                    },
                },
                {"cells": {"sentence": "A new one.", "translation": "新的"}},
                {"id": 0, "cells": {"sentence": " ", "translation": ""}},
            ],
        },
    )

    assert revised.pronunciation is None
    assert revised.core_meaning.native_text == "月球"
    # What the form doesn't show stays with its record.
    assert revised.core_meaning.image_prompt == "A full moon over a lake"
    assert revised.collocations == ["new moon", "half moon"]
    assert [(e.sentence, e.highlights) for e in revised.examples] == [
        ("We sat under the moon.", ["moon"]),
        ("A new one.", []),
    ]
    assert (revised.lemma, revised.difficulty) == ("moon", "A1")


def test_surrounding_spaces_alone_are_not_a_change() -> None:
    model = _moon().model_copy(deep=True)
    model.examples[0].sentence = "The moon is bright tonight. "

    revised = revise(
        model,
        WORD_FORM,
        {
            "examples": [
                {
                    "id": 0,
                    "cells": {
                        "sentence": "The moon is bright tonight.",
                        "translation": "今晚月亮很亮。",
                    },
                }
            ]
        },
    )

    assert revised.examples[0].sentence == "The moon is bright tonight. "


@pytest.mark.parametrize(
    ("values", "code", "key"),
    [
        ({"difficulty": " "}, "blank", "difficulty"),
        ({"core_meaning.native_text": ""}, "blank", "core_meaning.native_text"),
        ({"examples": []}, "too_few", "examples"),
        (
            {"examples": [{"cells": {"sentence": "Only this.", "translation": ""}}]},
            "blank",
            "examples",
        ),
        (
            {
                "examples": [
                    {"cells": {"sentence": str(i), "translation": "x"}}
                    for i in range(3)
                ]
            },
            "too_many",
            "examples",
        ),
        ({"collocations": ["a", "b", "c", "d", "e"]}, "too_many", "collocations"),
        ({"pronunciation": "x" * 2001}, "too_long", "pronunciation"),
        ({"lemma": "sun"}, "invalid", "lemma"),
        ({"collocations": "full moon"}, "invalid", "collocations"),
        ({"examples": [{"cells": {"sentence": 3}}]}, "invalid", "examples"),
    ],
)
def test_revise_refuses_what_the_card_cannot_hold(
    values: dict, code: str, key: str
) -> None:
    with pytest.raises(EditError) as raised:
        revise(_moon(), WORD_FORM, values)

    assert (raised.value.code, raised.value.key) == (code, key)


def test_a_models_own_rule_is_an_invalid_edit() -> None:
    phrase = PhraseModel.model_validate(
        {
            "phrase": "take off",
            "difficulty": "B1",
            "core_meaning": {
                "target_text": "to leave the ground",
                "native_text": "起飞",
            },
            "examples": [
                {"sentence": "It takes off at six.", "translation": "六点起飞。"}
            ],
        }
    )

    with pytest.raises(EditError) as raised:
        revise(
            phrase,
            PHRASE_FORM,
            {
                "supporting_meanings": [
                    {
                        "cells": {
                            "target_text": "to leave the ground",
                            "native_text": "起飞",
                        }
                    }
                ]
            },
        )

    assert raised.value.code == "invalid"
    assert "duplicate" in raised.value.detail


def _formula():
    from ankinote.collections.stem.models import FormulaModel

    return FormulaModel(
        front="Newton's second law?",
        latex="F = ma",
        meaning="Force is mass times acceleration.",
        variables=[{"symbol": "F", "description": "force"}],
        conditions="Inertial frame.",
        derivation="From momentum.",
        tags=["Physics"],
    )


def test_a_stem_form_offers_its_own_type_fields() -> None:
    from ankinote.collections.stem.models import EDIT_FORMS, CardType

    form = {f["key"]: f for f in describe(_formula(), EDIT_FORMS[CardType.FORMULA])}

    assert list(form) == [
        "front",
        "latex",
        "meaning",
        "variables",
        "conditions",
        "derivation",
        "tags",
    ]
    assert form["latex"]["required"] and not form["derivation"]["required"]
    assert form["variables"]["value"] == [
        {"id": 0, "cells": {"symbol": "F", "description": "force"}}
    ]
    assert form["tags"] == {
        "key": "tags",
        "type": "lines",
        "min": 0,
        "max": None,
        "value": ["Physics"],
    }


def test_a_blank_optional_stem_field_is_kept_empty() -> None:
    from ankinote.collections.stem.models import EDIT_FORMS, CardType

    form = EDIT_FORMS[CardType.FORMULA]
    revised = revise(_formula(), form, {"derivation": "  ", "variables": []})

    assert revised.derivation == ""
    assert revised.variables == []
    with pytest.raises(EditError) as raised:
        revise(_formula(), form, {"latex": " "})
    assert (raised.value.code, raised.value.key) == ("blank", "latex")
