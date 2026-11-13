"""Anki connection endpoints: built-in collection + AnkiWeb, or Anki Desktop.

The built-in backend is the in-process collection (``ANKI_BACKEND=collection``)
synced with AnkiWeb; Anki Desktop is reached through the AnkiConnect add-on.
Responses never carry the AnkiWeb password or login token: the password goes
to AnkiWeb once and only the returned token is stored, by
:class:`~ankinote.services.anki_sync_driver.AnkiSyncDriver`.
"""

import asyncio
import importlib.util
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from ankinote.config import envs
from ankinote.note_types import NoteTypeSpec, TypeStatus, build_specs, load_status
from ankinote.services.anki import (
    AnkiCollectionClient,
    AnkiConnectError,
    AnkiTransportError,
)
from ankinote.services.anki_batch import anki_write_batch
from ankinote.services.anki_factory import (
    COLLECTION_BACKEND,
    CONNECT_BACKEND,
    AnkiBackendConfigError,
    create_anki_client,
    get_shared_runtime,
    resolve_backend,
    start_anki_backend,
    switch_backend,
)
from ankinote.services.anki_sync import (
    SyncCredentialError,
    SyncNetworkError,
    SyncSnapshot,
    SyncState,
    SyncWriteBlocked,
)
from ankinote.services.collection_runtime import (
    CollectionInUseError,
    CollectionRuntime,
    CollectionRuntimeError,
)
from ankinote.settings import (
    apply_env,
    default_collection_path,
    load_settings,
    save_settings,
    saved_anki_backend,
)
from ankinote.utils.httpcli import init_session

Backend = Literal["collection", "connect"]
Direction = Literal["upload", "download"]

# Why the collection couldn't be opened, from the last start attempt.
_open_error: dict[str, str] | None = None
# The running full upload/download; it can take minutes, so it isn't awaited
# by the request that starts it.
_full_sync: asyncio.Task | None = None


class BackendIn(BaseModel):
    backend: Backend


class LoginIn(BaseModel):
    email: str
    password: str


class FullSyncIn(BaseModel):
    direction: Direction


def _fail(status: int, code: str, detail: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "detail": detail})


def _builtin_available() -> bool:
    return importlib.util.find_spec("anki") is not None


def _classify_open_error(exc: BaseException) -> dict[str, str]:
    if isinstance(exc, CollectionInUseError):
        code = "in_use"
    elif isinstance(exc, ImportError):
        code = "unavailable"
    elif isinstance(exc, (AnkiBackendConfigError, ValueError)):
        code = "config"
    else:
        code = "open"
    # Open errors name paths and permissions, never credentials.
    return {"code": code, "detail": str(exc)}


async def start_backend() -> None:
    """Apply ``settings.json`` and open the configured backend; never raises."""
    global _open_error
    apply_env(load_settings())
    _open_error = None
    try:
        await start_anki_backend()
    except (
        CollectionRuntimeError,
        AnkiBackendConfigError,
        OSError,
        ImportError,
        ValueError,
    ) as exc:
        _open_error = _classify_open_error(exc)
        logger.error("Anki backend failed to start: {}", exc)


async def _switch() -> None:
    global _open_error
    _open_error = None
    try:
        await switch_backend()
    except (
        CollectionRuntimeError,
        AnkiBackendConfigError,
        OSError,
        ImportError,
        ValueError,
    ) as exc:
        _open_error = _classify_open_error(exc)
        raise _fail(409, _open_error["code"], _open_error["detail"]) from exc


def sync_out(snapshot: SyncSnapshot) -> dict:
    return {
        "state": snapshot.state.value,
        "initialized": snapshot.initialized,
        "full_sync_required": snapshot.full_sync_required,
        "directions": list(snapshot.directions),
        "error": snapshot.error,
        "last_success": snapshot.last_success.isoformat()
        if snapshot.last_success
        else None,
        "result": asdict(snapshot.result) if snapshot.result else None,
    }


def _full_sync_running() -> bool:
    return _full_sync is not None and not _full_sync.done()


async def _local_cards(runtime: CollectionRuntime) -> int | None:
    """How many cards the collection holds, to word the full-sync choice.

    Only asked while the choice is pending and nothing runs on the worker:
    during a full sync this would queue behind it for minutes.
    """
    service = runtime.sync_service
    if (
        service is None
        or _full_sync_running()
        or service.status.state != SyncState.NEEDS_FULL_SYNC_CHOICE
    ):
        return None
    return await runtime.submit(lambda col: col.card_count())


def _choice(backend: str) -> Backend:
    """The option the step preselects: what's in use, else the recommendation."""
    if backend == COLLECTION_BACKEND or saved_anki_backend() != CONNECT_BACKEND:
        return COLLECTION_BACKEND
    return CONNECT_BACKEND


async def _status() -> dict:
    try:
        backend = resolve_backend()
    except AnkiBackendConfigError:
        backend = CONNECT_BACKEND
    runtime = get_shared_runtime()
    service = runtime.sync_service if runtime else None
    driver = runtime.sync_driver if runtime else None
    return {
        "backend": backend,
        "choice": _choice(backend),
        "builtin_available": _builtin_available(),
        "connect_url": envs.ANKI_CONNECT_URL,
        "collection_path": runtime.path
        if runtime
        else envs.ANKI_COLLECTION_PATH or default_collection_path(),
        "open": runtime is not None,
        "open_error": _open_error,
        "account": driver.account if driver else None,
        "account_managed": bool(driver and driver.externally_configured),
        "sync": sync_out(service.status) if service else None,
        "busy": _full_sync_running(),
        "writable": service is None or not service.write_blocked,
        "local_cards": await _local_cards(runtime) if runtime else None,
    }


def _collection_runtime() -> CollectionRuntime:
    runtime = get_shared_runtime()
    if runtime is None or runtime.sync_service is None or runtime.sync_driver is None:
        raise _fail(409, "not_open")
    return runtime


async def probe_anki_connect(url: str) -> int:
    """Ask AnkiConnect for its version, quickly and without retries.

    Raises:
        HTTPException: 503 ``unreachable`` when nothing answers at ``url``;
            502 ``not_ankiconnect`` / ``ankiconnect`` when something answers
            but not as a working AnkiConnect.
    """
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.post(url, json={"action": "version", "version": 6})
        body = response.json()
    except httpx.HTTPError as exc:
        raise _fail(503, "unreachable", url) from exc
    except ValueError as exc:
        raise _fail(502, "not_ankiconnect", url) from exc
    if not isinstance(body, dict) or "result" not in body:
        raise _fail(502, "not_ankiconnect", url)
    if body.get("error"):
        raise _fail(502, "ankiconnect", str(body["error"]))
    return int(body["result"])


router = APIRouter(prefix="/api/anki")


@router.get("")
async def get_status() -> dict:
    return await _status()


@router.put("/backend")
async def put_backend(body: BackendIn) -> dict:
    """Save the backend choice and switch to it.

    The choice is saved even when the connection then fails, so "Try again"
    only has to retry the connection.
    """
    if body.backend == COLLECTION_BACKEND and not _builtin_available():
        raise _fail(409, "unavailable")
    settings = load_settings()
    settings.anki_backend = body.backend
    if body.backend == COLLECTION_BACKEND:
        if not settings.anki_collection_path:
            settings.anki_collection_path = default_collection_path()
        Path(settings.anki_collection_path).parent.mkdir(parents=True, exist_ok=True)
    save_settings(settings)
    apply_env(settings)
    await _switch()
    if body.backend == CONNECT_BACKEND:
        await probe_anki_connect(envs.ANKI_CONNECT_URL)
    return await _status()


@router.post("/login")
async def login(body: LoginIn) -> dict:
    runtime = _collection_runtime()
    driver, service = runtime.sync_driver, runtime.sync_service
    assert driver is not None and service is not None
    if driver.externally_configured:
        raise _fail(409, "managed")
    email = body.email.strip()
    if not email or not body.password:
        raise _fail(422, "fields")
    try:
        await driver.login(service, email, body.password)
    except SyncCredentialError as exc:
        raise _fail(401, "auth") from exc
    except SyncNetworkError as exc:
        raise _fail(503, "network") from exc
    except ValueError as exc:
        # The collection is bound to another AnkiWeb account.
        raise _fail(409, "other_account") from exc
    except Exception as exc:
        logger.warning("AnkiWeb login failed: {}", type(exc).__name__)
        raise _fail(502, "error") from exc
    return await _status()


@router.post("/logout")
async def logout() -> dict:
    runtime = _collection_runtime()
    driver, service = runtime.sync_driver, runtime.sync_service
    assert driver is not None and service is not None
    if driver.externally_configured:
        raise _fail(409, "managed")
    await driver.logout(service)
    return await _status()


@router.post("/sync")
async def sync_now() -> dict:
    """Retry now: after a network error, or with a deployment-set account."""
    runtime = _collection_runtime()
    driver, service = runtime.sync_driver, runtime.sync_service
    assert driver is not None and service is not None
    try:
        if driver.externally_configured and (
            service.status.error == "credentials" or not driver.authenticated
        ):
            await driver.login_configured_account(service)
        else:
            await service.sync_now()
    except SyncCredentialError as exc:
        raise _fail(401, "auth") from exc
    except SyncNetworkError as exc:
        raise _fail(503, "network") from exc
    return await _status()


@router.post("/full-sync")
async def full_sync(body: FullSyncIn) -> dict:
    """Start the chosen full upload or download; poll ``GET /api/anki``."""
    global _full_sync
    runtime = _collection_runtime()
    driver, service = runtime.sync_driver, runtime.sync_service
    assert driver is not None and service is not None
    if _full_sync_running():
        return await _status()
    status = service.status
    if not status.full_sync_required or body.direction not in status.directions:
        raise _fail(409, "no_choice")
    _full_sync = asyncio.create_task(
        service.resolve_full_sync(body.direction, driver.full_sync)
    )
    # Let it take the sync lock, so the reply already says "syncing".
    await asyncio.wait({_full_sync}, timeout=0.2)
    return await _status()


def note_type_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SyncWriteBlocked):
        return _fail(409, "write_blocked")
    if isinstance(exc, AnkiTransportError):
        return _fail(503, "unreachable", envs.ANKI_CONNECT_URL)
    if isinstance(exc, AnkiBackendConfigError):
        return _fail(409, "not_open")
    if isinstance(exc, AnkiConnectError):
        return _fail(502, "ankiconnect", str(exc))
    logger.exception("Note type setup failed")
    return _fail(500, "error", type(exc).__name__)


def _note_type_out(status: TypeStatus) -> dict:
    """How one note type stands in Anki, and what setting it up would change."""
    spec = status.spec
    return {
        "key": spec.key,
        "name": spec.notetype_name,
        "deck": spec.deck_name,
        "state": status.state,
        "deck_exists": status.deck_exists,
        "missing_fields": status.missing_fields,
        "missing_templates": status.missing_templates,
        "css_differs": status.css_differs,
    }


_RESULT = {"missing": "created", "update": "updated", "synced": "unchanged"}


async def _set_up(client: AnkiCollectionClient, spec: NoteTypeSpec) -> dict:
    before = await load_status(client, spec)
    await spec.sync(client)
    item = _note_type_out(await load_status(client, spec))
    # A missing deck alone doesn't make a type "update"; setting up adds it.
    readded_deck = before.state == "synced" and not before.deck_exists
    item["result"] = "updated" if readded_deck else _RESULT[before.state]
    return item


async def ready_backend() -> None:
    """Fail fast (3 s, no retries) when Anki Desktop isn't answering."""
    init_session()
    if resolve_backend() == CONNECT_BACKEND:
        await probe_anki_connect(envs.ANKI_CONNECT_URL)


@router.get("/note-types")
async def note_types() -> list[dict]:
    await ready_backend()
    try:
        client = create_anki_client()
        statuses = [await load_status(client, spec) for spec in build_specs()]
    except Exception as exc:
        raise note_type_error(exc) from exc
    return [_note_type_out(s) for s in statuses]


@router.post("/note-types")
async def prepare_note_types() -> list[dict]:
    """Create missing note types and decks and update changed ones.

    Each item's ``result`` is ``created``, ``updated`` or ``unchanged``.
    Updating adds fields, templates and styling; it never removes anything,
    so existing notes, cards and review history stay as they are.
    """
    await ready_backend()
    try:
        client = create_anki_client()
        # One batch: one AnkiWeb sync after all the note types, not one each.
        async with anki_write_batch(client):
            return [await _set_up(client, spec) for spec in build_specs()]
    except Exception as exc:
        raise note_type_error(exc) from exc


@router.post("/note-types/{key}")
async def prepare_note_type(key: str) -> dict:
    """Create or update one note type and its deck, as above."""
    spec = next((s for s in build_specs() if s.key == key), None)
    if spec is None:
        raise _fail(404, "unknown", key)
    await ready_backend()
    try:
        client = create_anki_client()
        async with anki_write_batch(client):
            return await _set_up(client, spec)
    except Exception as exc:
        raise note_type_error(exc) from exc
