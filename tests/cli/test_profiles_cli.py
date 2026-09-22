"""``ankinote profiles list`` — read-only provider profile discovery."""

import json

from click.testing import CliRunner

from ankinote.cli.main import cli
from ankinote.settings import ProviderProfile, Settings, save_settings


def _settings() -> Settings:
    return Settings(
        text_providers={
            "OpenAI": ProviderProfile(
                vendor="OpenAI", model="gpt-4o", api_key="text-secret"
            ),
            "second": ProviderProfile(
                vendor="Custom / Other",
                model="my-model",
                base_url="https://example.test/v1",
                api_key="text-secret-2",
            ),
        },
        active_text_provider="second",
        image_providers={
            "Gemini": ProviderProfile(
                vendor="Gemini", model="gemini-image", api_key="image-secret"
            ),
        },
        active_image_provider="Gemini",
    )


def test_json_output_marks_active_profile_and_omits_secrets():
    save_settings(_settings())

    result = CliRunner().invoke(cli, ["profiles", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "text_providers": [
            {
                "name": "OpenAI",
                "vendor": "OpenAI",
                "model": "gpt-4o",
                "base_url": "",
                "active": False,
            },
            {
                "name": "second",
                "vendor": "Custom / Other",
                "model": "my-model",
                "base_url": "https://example.test/v1",
                "active": True,
            },
        ],
        "image_providers": [
            {
                "name": "Gemini",
                "vendor": "Gemini",
                "model": "gemini-image",
                "base_url": "",
                "active": True,
            },
        ],
    }
    assert "secret" not in result.output


def test_human_readable_output_marks_active_profile_and_omits_secrets():
    save_settings(_settings())

    result = CliRunner().invoke(cli, ["profiles", "list"])

    assert result.exit_code == 0, result.output
    assert "second (active)" in result.output
    assert "OpenAI —" in result.output
    assert "Gemini (active)" in result.output
    assert "secret" not in result.output


def test_no_configured_profiles_is_reported_instead_of_crashing(monkeypatch):
    save_settings(_settings())
    result = CliRunner().invoke(cli, ["profiles", "list"])
    assert result.exit_code == 0, result.output

    from ankinote.cli import profiles as profiles_module

    monkeypatch.setattr(
        profiles_module,
        "load_settings",
        lambda: Settings(text_providers={}, image_providers={}),
    )
    result = CliRunner().invoke(cli, ["profiles", "list"])
    assert result.exit_code == 0, result.output
    assert "(none configured)" in result.output
