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
