"""The --profile/--image-profile CLI flags reach the typed collection options."""

from contextlib import asynccontextmanager

from click.testing import CliRunner

from ankinote.settings import ProviderProfile, Settings, save_settings


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


def test_word_add_profile_reaches_options(monkeypatch):
    from ankinote.cli import word

    captured = _capture_options(monkeypatch, word)
    result = CliRunner().invoke(
        word.word,
        ["add", "heat", "--profile", "mine", "--image-profile", "images"],
    )

    assert result.exit_code == 0, result.output
    assert captured["options"].profile == "mine"
    assert captured["options"].image_profile == "images"


def test_stem_add_profile_reaches_options(monkeypatch):
    from ankinote.cli import stem

    captured = _capture_options(monkeypatch, stem)
    result = CliRunner().invoke(
        stem.stem,
        ["add", "What is a derivative?", "--profile", "mine"],
    )

    assert result.exit_code == 0, result.output
    assert captured["options"].profile == "mine"


def test_word_add_unknown_profile_lists_available_profiles():
    from ankinote.cli import word

    save_settings(
        Settings(
            text_providers={"OpenAI": ProviderProfile(vendor="OpenAI", model="gpt-4o")}
        )
    )

    result = CliRunner().invoke(word.word, ["add", "heat", "--profile", "bogus"])

    assert result.exit_code == 2
    assert "bogus" in result.output
    assert "OpenAI" in result.output


def test_stem_add_unknown_image_profile_lists_available_profiles():
    from ankinote.cli import stem

    save_settings(
        Settings(
            image_providers={
                "OpenAI": ProviderProfile(vendor="OpenAI", model="gpt-image-1.5")
            }
        )
    )

    result = CliRunner().invoke(
        stem.stem, ["add", "What is a derivative?", "--image-profile", "bogus"]
    )

    assert result.exit_code == 2
    assert "bogus" in result.output
    assert "OpenAI" in result.output
