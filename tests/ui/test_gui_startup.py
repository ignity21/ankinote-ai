"""The web app's startup hook opens the backend chosen on the Settings page."""

import pytest

from ankinote.config import envs
from ankinote.settings import Settings, save_settings
from ankinote.ui import main


async def test_startup_opens_backend_saved_in_settings(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # apply_env also writes os.environ; register both so monkeypatch restores them.
    monkeypatch.delenv("ANKI_BACKEND", raising=False)
    monkeypatch.delenv("ANKI_COLLECTION_PATH", raising=False)
    collection = str(tmp_path / "collection.anki2")
    save_settings(Settings(anki_backend="collection", anki_collection_path=collection))

    seen: list[tuple[str, str]] = []

    async def fake_start() -> None:
        seen.append((envs.ANKI_BACKEND, envs.ANKI_COLLECTION_PATH))

    monkeypatch.setattr(main, "start_anki_backend", fake_start)

    await main._open_anki_backend()

    assert seen == [("collection", collection)]
