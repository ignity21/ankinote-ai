"""Round-trip and tamper tests for the encrypted config bundle."""

from __future__ import annotations

import json

import pytest

from ankinote.settings import DefaultsConfig, ProviderProfile, Settings
from ankinote.ui.config_transfer import (
    ConfigImportError,
    ConfigTransferError,
    export_config,
    import_config,
    merge_bundle,
)

PASSPHRASE = "correct horse battery"


def _settings() -> Settings:
    return Settings(
        text_providers={
            "OpenAI": ProviderProfile(
                "OpenAI", "gpt-4o", "https://api.openai.com/v1", "sk-text"
            ),
            "Local": ProviderProfile(
                "Custom / Other", "llama", "http://localhost:1234/v1", ""
            ),
        },
        active_text_provider="Local",
        image_providers={
            "Gemini": ProviderProfile("Gemini", "imagen", "https://g.example", "g-key"),
        },
        active_image_provider="Gemini",
        image_size=768,
        api_keys={"GOOGLE_TTS_KEY": "tts-secret"},
        defaults=DefaultsConfig(native_language="French", target_language="German"),
        ui_language="zh-CN",
    )


def test_export_import_round_trips_providers_and_tts_key() -> None:
    bundle = import_config(export_config(_settings(), PASSPHRASE), PASSPHRASE)

    assert set(bundle.text_providers) == {"OpenAI", "Local"}
    assert bundle.text_providers["OpenAI"].api_key == "sk-text"
    assert bundle.text_providers["Local"].base_url == "http://localhost:1234/v1"
    assert bundle.image_providers["Gemini"].api_key == "g-key"
    assert bundle.google_tts_key == "tts-secret"
    assert bundle.profile_count == 3


def test_bundle_file_holds_no_plaintext_secret() -> None:
    blob = export_config(_settings(), PASSPHRASE)
    assert b"sk-text" not in blob
    assert b"tts-secret" not in blob
    document = json.loads(blob)
    assert document["format"] == "ankinote-config"
    assert document["kdf"]["name"] == "scrypt"


def test_wrong_passphrase_is_rejected() -> None:
    blob = export_config(_settings(), PASSPHRASE)
    with pytest.raises(ConfigImportError, match="passphrase"):
        import_config(blob, "not the passphrase")


def test_tampered_ciphertext_is_rejected() -> None:
    document = json.loads(export_config(_settings(), PASSPHRASE))
    document["ciphertext"] = "A" + document["ciphertext"][1:]
    with pytest.raises(ConfigImportError):
        import_config(json.dumps(document).encode(), PASSPHRASE)


def test_tampered_kdf_parameters_are_rejected() -> None:
    document = json.loads(export_config(_settings(), PASSPHRASE))
    document["kdf"]["n"] = 1024  # header is authenticated as AAD
    with pytest.raises(ConfigImportError):
        import_config(json.dumps(document).encode(), PASSPHRASE)


def test_foreign_file_is_rejected() -> None:
    with pytest.raises(ConfigImportError, match="not an ankinote"):
        import_config(b'{"hello": "world"}', PASSPHRASE)
    with pytest.raises(ConfigImportError, match="not an ankinote"):
        import_config(b"not json at all", PASSPHRASE)


def test_short_passphrase_is_refused_on_export() -> None:
    with pytest.raises(ConfigTransferError, match="at least"):
        export_config(_settings(), "short")


def test_merge_overwrites_by_name_and_adds_new_and_keeps_the_rest() -> None:
    base = Settings(
        text_providers={
            "OpenAI": ProviderProfile("OpenAI", "gpt-3.5", "https://old", "old-key"),
            "Keep": ProviderProfile("Keep", "m", "u", "keep-key"),
        },
        active_text_provider="Keep",
        image_providers={},
        active_image_provider="",
        image_size=512,
        api_keys={"GOOGLE_TTS_KEY": "existing-tts", "OTHER": "leave-me"},
        defaults=DefaultsConfig(native_language="Japanese"),
        ui_language="en",
    )
    bundle = import_config(export_config(_settings(), PASSPHRASE), PASSPHRASE)

    merged = merge_bundle(base, bundle)

    assert merged.text_providers["OpenAI"].model == "gpt-4o"  # overwritten
    assert merged.text_providers["OpenAI"].api_key == "sk-text"
    assert merged.text_providers["Keep"].api_key == "keep-key"  # untouched
    assert "Local" in merged.text_providers  # added
    assert merged.image_providers["Gemini"].api_key == "g-key"  # added
    assert merged.api_keys["GOOGLE_TTS_KEY"] == "tts-secret"  # bundle non-empty wins
    assert merged.api_keys["OTHER"] == "leave-me"
    assert merged.active_text_provider == "Keep"  # not touched by import
    assert merged.ui_language == "en"
    assert merged.defaults.native_language == "Japanese"
    assert merged.image_size == 512


def test_merge_keeps_existing_tts_key_when_bundle_has_none() -> None:
    source = _settings()
    source.api_keys = {"GOOGLE_TTS_KEY": ""}
    bundle = import_config(export_config(source, PASSPHRASE), PASSPHRASE)

    base = _settings()
    base.api_keys = {"GOOGLE_TTS_KEY": "keep-this"}
    merged = merge_bundle(base, bundle)

    assert merged.api_keys["GOOGLE_TTS_KEY"] == "keep-this"
