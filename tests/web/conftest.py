"""Fixtures for the web API tests: the app with its lifespan, fake AnkiWeb."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from anki.collection import Collection
from anki.errors import NetworkError, SyncError, SyncErrorKind
from anki.sync_pb2 import (
    MediaSyncStatusResponse,
    SyncAuth,
    SyncCollectionResponse,
)

from ankinote.services.anki_factory import get_shared_runtime
from ankinote.web import anki_api
from ankinote.web.app import create_app
from tests.web.anki_fakes import PASSWORD, TOKEN


@pytest.fixture
def ankiweb(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace Anki's network calls; ``required`` is what the next sync says."""
    state: dict[str, Any] = {
        "required": SyncCollectionResponse.NO_CHANGES,
        "network_down": False,
        "full": [],
        "logins": 0,
    }

    def sync_login(self, username: str, password: str, endpoint=None) -> SyncAuth:
        state["logins"] += 1
        if state["network_down"]:
            raise NetworkError("down", None, None, None)
        if password != PASSWORD:
            raise SyncError("bad", None, None, None, SyncErrorKind.AUTH)
        return SyncAuth(hkey=TOKEN)

    def sync_collection(self, auth, sync_media) -> SyncCollectionResponse:
        if state["network_down"]:
            raise NetworkError("down", None, None, None)
        return SyncCollectionResponse(required=state["required"])

    def full_upload_or_download(self, *, auth, server_usn, upload) -> None:
        state["full"].append("upload" if upload else "download")
        state["required"] = SyncCollectionResponse.NO_CHANGES

    monkeypatch.setattr(Collection, "sync_login", sync_login)
    monkeypatch.setattr(Collection, "sync_collection", sync_collection)
    monkeypatch.setattr(Collection, "full_upload_or_download", full_upload_or_download)
    monkeypatch.setattr(Collection, "sync_media", lambda self, auth: None)
    monkeypatch.setattr(
        Collection, "media_sync_status", lambda self: MediaSyncStatusResponse()
    )
    return state


@pytest.fixture
async def api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """The app with its lifespan, served in the test's event loop."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    # apply_env writes these; setting them here makes monkeypatch undo that.
    for name in ("ANKI_BACKEND", "ANKI_COLLECTION_PATH"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    monkeypatch.setattr(anki_api, "_open_error", None)
    monkeypatch.setattr(anki_api, "_full_sync", None)
    app = create_app(tmp_path / "no-dist")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        yield client
    assert get_shared_runtime() is None
