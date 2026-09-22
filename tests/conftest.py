"""Shared fixtures for the test suite."""

import pytest

from ankinote.config import envs


@pytest.fixture(autouse=True)
def _isolate_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset env-derived settings to their defaults before each test.

    ``ankinote.config.envs`` is bound once at import time from the process
    environment / a developer's local ``.env`` file (e.g. ``ANKI_BACKEND``
    set for a personal headless Anki setup). Without this, tests that don't
    explicitly configure a setting silently inherit whatever that developer
    happens to have on disk. Tests that need a specific value still set it
    themselves via ``monkeypatch``, which applies on top of this baseline.
    """
    monkeypatch.setattr(envs, "ANKI_BACKEND", "connect")
    monkeypatch.setattr(envs, "ANKI_COLLECTION_PATH", "")
    monkeypatch.setattr(envs, "ANKI_CONNECT_URL", "http://localhost:8765")
    monkeypatch.setattr(envs, "ANKIWEB_USERNAME", "")
    monkeypatch.setattr(envs, "ANKIWEB_PASSWORD", "")
    monkeypatch.setattr(envs, "GOOGLE_TTS_KEY", "")


@pytest.fixture(autouse=True)
def _isolate_settings_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``settings.json`` reads/writes at a throwaway directory.

    Without this, any test that calls ``load_settings()``/``save_settings()``
    (directly, or via the CLI's profile resolution) would read and write the
    developer's real ``~/.config/ankinote/settings.json``.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
