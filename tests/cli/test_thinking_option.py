"""The --thinking CLI flag reaches the typed collection options."""

from contextlib import asynccontextmanager

import pytest
from click.testing import CliRunner

from ankinote.services.ai import DISABLE_REASONING


@pytest.mark.parametrize(
    "command", [["init"], ["add", "topic"], ["batch", "topic", "--rpm", "0"]]
)
@pytest.mark.parametrize("kind", ["auto", "concept", "formula", "procedure", "example"])
def test_stem_type_selection_reaches_collection(monkeypatch, command, kind):
    from ankinote.cli import stem

    captured = _capture_options(monkeypatch, stem)
    result = CliRunner().invoke(stem.stem, [*command, "--type", kind])
    assert result.exit_code == 0, result.output
    assert captured["options"].card_type == (None if kind == "auto" else kind)


def _capture_options(monkeypatch, module):
    """Patch a CLI module's collection_context to record the options it gets."""
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_context(builder, options):
        captured["options"] = options

        class _FakeCollection:
            deck_name = "deck"

            async def generate_and_add_note(self, *args, **kwargs):
                return 1

        yield _FakeCollection()

    monkeypatch.setattr(module, "collection_context", fake_context)
    return captured


def test_stem_add_thinking_off(monkeypatch):
    from ankinote.cli import stem

    captured = _capture_options(monkeypatch, stem)
    result = CliRunner().invoke(
        stem.stem, ["add", "What is a derivative?", "--thinking", "off"]
    )

    assert result.exit_code == 0, result.output
    assert captured["options"].reasoning_effort == DISABLE_REASONING


def test_stem_add_thinking_defaults_to_high(monkeypatch):
    from ankinote.cli import stem

    captured = _capture_options(monkeypatch, stem)
    result = CliRunner().invoke(stem.stem, ["add", "What is a derivative?"])

    assert result.exit_code == 0, result.output
    assert captured["options"].reasoning_effort == "high"


def test_word_add_thinking_high(monkeypatch):
    from ankinote.cli import word

    captured = _capture_options(monkeypatch, word)
    result = CliRunner().invoke(word.word, ["add", "heat", "--thinking", "high"])

    assert result.exit_code == 0, result.output
    assert captured["options"].reasoning_effort == "high"


def test_word_add_thinking_defaults_to_disabled(monkeypatch):
    from ankinote.cli import word

    captured = _capture_options(monkeypatch, word)
    result = CliRunner().invoke(word.word, ["add", "heat"])

    assert result.exit_code == 0, result.output
    assert captured["options"].reasoning_effort == DISABLE_REASONING
