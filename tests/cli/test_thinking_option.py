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
    """Patch a CLI module's collection builder to record the options it gets."""
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_client_scope():
        yield object()

    class _FakeCollection:
        deck_name = "deck"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def generate_and_add_note(self, *args, **kwargs):
            return 1

    def fake_builder(client, options):
        captured["options"] = options
        return _FakeCollection()

    monkeypatch.setattr(module, "anki_client_scope", fake_client_scope)
    builder_name = next(
        name
        for name in vars(module)
        if name.startswith("build_") and name.endswith("_collection")
    )
    monkeypatch.setattr(module, builder_name, fake_builder)
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
