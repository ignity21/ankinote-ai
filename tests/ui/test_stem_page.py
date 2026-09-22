"""Tests for the STEM generation page helpers."""

import pytest
from pydantic import ValidationError

from ankinote.collections.stem.models import ExampleModel, FormulaModel
from ankinote.ui.pages.stem import _edited_card


def test_formula_editor_validates_and_rebuilds_variable_rows():
    model = FormulaModel(
        front="Law?",
        latex="F=ma",
        meaning="Force",
        variables=[],
        conditions="",
        derivation="",
        tags=["Physics"],
    )
    edited = _edited_card(
        model,
        {
            "latex": " E=mc^2 ",
            "variable_2_symbol": "E",
            "variable_2_description": "Energy",
            "tags": "Physics, Relativity",
            "image_description": " mass and energy ",
        },
    )
    assert edited.latex == "E=mc^2"
    assert edited.variables[0].description == "Energy"
    assert edited.tags == ["Physics", "Relativity"]
    assert edited.image_description == "mass and energy"
    assert model.variables == []


def test_example_editor_preserves_steps_and_rejects_empty_answer():
    model = ExampleModel(
        front="Solve x+1=2",
        answer="1",
        steps=["Subtract one."],
        explanation="",
        tags=["Math"],
    )
    edited = _edited_card(model, {"steps": "Subtract one.\nCheck x=1."})
    assert edited.steps == ["Subtract one.", "Check x=1."]
    with pytest.raises(ValidationError):
        _edited_card(model, {"answer": "  "})
    with pytest.raises(ValidationError):
        _edited_card(model, {"steps": "  "})
