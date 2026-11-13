"""Anki connection endpoints, on a real temp collection; AnkiWeb is faked."""

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from anki.sync_pb2 import (
    SyncCollectionResponse,
)

from ankinote.config import envs
from ankinote.services.anki_factory import (
    start_anki_backend,
    stop_anki_backend,
)
from ankinote.services.collection_runtime import CollectionRuntime
from ankinote.settings import load_settings, save_settings, saved_anki_backend
from ankinote.web import anki_api
from tests.services.fake_anki_connect_server import fake_anki_connect_server
from tests.web.anki_fakes import PASSWORD, TOKEN, builtin, login


async def test_fresh_install_recommends_builtin(api: httpx.AsyncClient) -> None:
    status = (await api.get("/api/anki")).json()
    assert status["backend"] == "connect"
    assert status["choice"] == "collection"
    assert status["builtin_available"] is True
    assert status["sync"] is None


async def test_saving_other_settings_keeps_recommending_builtin(
    api: httpx.AsyncClient,
) -> None:
    """Saving step 1 mustn't record AnkiConnect as if the user had chosen it."""
    save_settings(load_settings())
    status = (await api.get("/api/anki")).json()
    assert saved_anki_backend() == ""
    assert status["choice"] == "collection"


async def test_choosing_builtin_creates_collection_and_waits_for_login(
    api: httpx.AsyncClient, tmp_path: Path
) -> None:
    status = await builtin(api)
    expected = tmp_path / "data" / "ankinote" / "collection.anki2"
    assert status["backend"] == status["choice"] == "collection"
    assert status["collection_path"] == str(expected)
    assert expected.exists()
    assert status["sync"]["state"] == "not_logged_in"
    assert status["writable"] is False
    assert saved_anki_backend() == "collection"
    assert load_settings().anki_collection_path == str(expected)


async def test_login_then_download_from_ankiweb(
    api: httpx.AsyncClient, ankiweb: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    await builtin(api)
    ankiweb["required"] = SyncCollectionResponse.FULL_DOWNLOAD

    response = await login(api)
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["account"] == "user@example.com"
    assert status["sync"]["state"] == "needs_full_sync_choice"
    assert status["sync"]["directions"] == ["download"]
    assert status["local_cards"] == 0
    assert status["writable"] is False

    response = await api.post("/api/anki/full-sync", json={"direction": "download"})
    assert response.status_code == 200, response.text
    while (status := (await api.get("/api/anki")).json())["busy"]:
        await asyncio.sleep(0.05)
    assert ankiweb["full"] == ["download"]
    assert status["sync"]["state"] == "idle"
    assert status["writable"] is True

    exposed = str(status) + caplog.text
    assert TOKEN not in exposed and PASSWORD not in exposed


async def test_wrong_password_is_auth_error(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    response = await login(api, "wrong")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "auth"
    assert (await api.get("/api/anki")).json()["account"] is None


async def test_network_down_at_login_is_network_error(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    ankiweb["network_down"] = True
    response = await login(api)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "network"


async def test_full_sync_rejects_a_direction_anki_did_not_offer(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    ankiweb["required"] = SyncCollectionResponse.FULL_DOWNLOAD
    await login(api)
    response = await api.post("/api/anki/full-sync", json={"direction": "upload"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_choice"
    assert ankiweb["full"] == []


async def test_note_types_wait_for_the_first_sync(api: httpx.AsyncClient) -> None:
    await builtin(api)
    response = await api.post("/api/anki/note-types")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "write_blocked"


async def test_prepare_note_types_creates_then_leaves_unchanged(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    status = (await login(api)).json()
    assert status["sync"]["state"] == "idle"

    first = (await api.post("/api/anki/note-types")).json()
    assert {item["result"] for item in first} == {"created"}
    assert {item["name"] for item in first} >= {"AINote Word V2", "AINote Phrase V2"}
    assert all(item["state"] == "synced" for item in first)

    second = (await api.post("/api/anki/note-types")).json()
    assert {item["result"] for item in second} == {"unchanged"}

    listed = (await api.get("/api/anki/note-types")).json()
    assert [item["key"] for item in listed] == [item["key"] for item in first]
    assert {item["state"] for item in listed} == {"synced"}


async def test_collection_in_use_is_reported(
    api: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data" / "ankinote" / "collection.anki2"
    path.parent.mkdir(parents=True)
    holder = CollectionRuntime(str(path))
    await holder.open()
    try:
        response = await api.put("/api/anki/backend", json={"backend": "collection"})
    finally:
        await holder.close()
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "in_use"
    assert (await api.get("/api/anki")).json()["open_error"]["code"] == "in_use"


async def test_anki_desktop_is_probed_and_set_up(
    api: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop = CollectionRuntime(str(tmp_path / "desktop.anki2"))
    await desktop.open()
    try:
        async with fake_anki_connect_server(desktop) as url:
            monkeypatch.setattr(envs, "ANKI_CONNECT_URL", url)
            response = await api.put("/api/anki/backend", json={"backend": "connect"})
            assert response.status_code == 200, response.text
            assert response.json()["choice"] == "connect"

            prepared = (await api.post("/api/anki/note-types")).json()
            assert {item["result"] for item in prepared} == {"created"}
    finally:
        await desktop.close()
    assert saved_anki_backend() == "connect"


async def test_anki_desktop_not_running_is_unreachable(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(envs, "ANKI_CONNECT_URL", "http://127.0.0.1:9")
    response = await api.put("/api/anki/backend", json={"backend": "connect"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "unreachable"
    # The choice is kept, so retrying only retries the connection.
    assert (await api.get("/api/anki")).json()["choice"] == "connect"


async def test_deployment_account_hides_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ankiweb: dict[str, Any]
) -> None:
    monkeypatch.setattr(envs, "ANKI_BACKEND", "collection")
    monkeypatch.setattr(envs, "ANKI_COLLECTION_PATH", str(tmp_path / "c.anki2"))
    monkeypatch.setattr(envs, "ANKIWEB_USERNAME", "ops@example.com")
    monkeypatch.setattr(envs, "ANKIWEB_PASSWORD", PASSWORD)
    await start_anki_backend()
    try:
        status = await anki_api.get_status()
        assert status["account"] == "ops@example.com"
        assert status["account_managed"] is True
        assert status["sync"]["state"] == "idle"
        with pytest.raises(Exception) as raised:
            await anki_api.login(anki_api.LoginIn(email="x@y.z", password="p"))
        assert raised.value.detail["code"] == "managed"  # type: ignore[attr-defined]
    finally:
        await stop_anki_backend()
