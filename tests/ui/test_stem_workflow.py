"""Exercise the real STEM page through NiceGUI's in-process user simulation."""

from contextlib import asynccontextmanager

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from ankinote.collections.stem.models import CARD_ADAPTER, CardType
from ankinote.settings import Settings
from ankinote.ui.pages import stem


@pytest.mark.parametrize("kind", list(CardType))
async def test_every_type_previews_before_save(monkeypatch, kind):
    content = {
        "concept": {"back_brief": "Definition", "back_detail": "Explanation"},
        "formula": {
            "latex": "F=ma",
            "meaning": "Force",
            "variables": [],
            "conditions": "Inertial frame",
            "derivation": "",
        },
        "procedure": {
            "summary": "Method",
            "steps": ["First step"],
            "conditions": "Prerequisites",
        },
        "example": {"answer": "42", "steps": ["Calculate"], "explanation": ""},
    }
    model = CARD_ADAPTER.validate_python(
        {
            "card_type": kind,
            "front": "Question",
            "tags": ["Math"],
            **content[kind],
        }
    )
    saved = []
    selected = []
    settings = Settings()
    settings.defaults.generate_image = False
    monkeypatch.setattr(stem, "load_settings", lambda: settings)
    monkeypatch.setattr(stem, "apply_env", lambda _: None)

    @asynccontextmanager
    async def application():
        yield

    class Collection:
        def __init__(self, *args, **kwargs):
            selected.append(kwargs["card_type"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_model(self, *args, **kwargs):
            return model

        async def add_note(self, edited, **kwargs):
            saved.append(edited)
            return 1

    monkeypatch.setattr(stem, "Application", application)
    monkeypatch.setattr(stem, "StemCollection", Collection)
    async with user_simulation(stem.stem_page) as user:
        await user.open("/")
        user.find("Topic").type("Question")
        user.find("Card type").click()
        user.find(kind.title()).click()
        user.find(kind=ui.button, content="Generate").click()
        await user.should_see(f"{kind.title()} card — review and edit")
        assert saved == []
        assert selected == [kind]
        if kind == CardType.FORMULA:
            user.find("Add variable").click()
            user.find("Symbol").type("F")
            user.find("Description").type("Force")
        user.find("Save to Anki").click()
        await user.should_see("Card saved to Anki")
        assert len(saved) == 1
        assert saved[0].card_type == kind
        if kind == CardType.FORMULA:
            assert saved[0].variables[0].symbol == "F"
        await user.should_not_see("Save to Anki")
