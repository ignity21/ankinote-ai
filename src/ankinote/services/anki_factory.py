"""Single construction point for the Anki collection client.

Every UI page and CLI command builds its client through :func:`create_anki_client`
instead of instantiating a backend directly, so backend selection lives in one
place. Selection is driven by ``ANKI_BACKEND``:

- ``connect`` (default): talk to a running AnkiConnect server. Stateless — each
  ``create_anki_client()`` call returns an independent client.
- ``collection``: operate on a local Anki collection in-process. Requires
  ``ANKI_COLLECTION_PATH`` and an active :func:`anki_backend_scope` (opened once
  for the web app at startup, once per CLI command), which owns the single
  shared :class:`CollectionRuntime` every client borrows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from ankinote.config import envs
from ankinote.services.anki import AnkiCollectionClient, AnkiConnectClient
from ankinote.services.anki_credentials import CredentialStore
from ankinote.services.anki_direct import DirectCollectionClient
from ankinote.services.anki_sync import SyncService, SyncStateStore
from ankinote.services.anki_sync_driver import AnkiSyncDriver
from ankinote.services.collection_runtime import CollectionRuntime

CONNECT_BACKEND = "connect"
COLLECTION_BACKEND = "collection"
_KNOWN_BACKENDS = (CONNECT_BACKEND, COLLECTION_BACKEND)

_shared_runtime: CollectionRuntime | None = None


class AnkiBackendConfigError(Exception):
    """Raised when the Anki backend selection is misconfigured."""


def resolve_backend() -> str:
    """Return the configured backend name, validated."""
    backend = (envs.ANKI_BACKEND or CONNECT_BACKEND).strip().lower()
    if backend not in _KNOWN_BACKENDS:
        raise AnkiBackendConfigError(
            f"Unknown ANKI_BACKEND {backend!r}; expected one of "
            f"{', '.join(_KNOWN_BACKENDS)}."
        )
    return backend


def _require_collection_path() -> str:
    if not envs.ANKI_COLLECTION_PATH:
        raise AnkiBackendConfigError(
            "ANKI_BACKEND=collection requires ANKI_COLLECTION_PATH to point "
            "at the Anki collection file."
        )
    return envs.ANKI_COLLECTION_PATH


def get_shared_runtime() -> CollectionRuntime | None:
    """Return the process-wide collection runtime, if one is open."""
    return _shared_runtime


async def start_anki_backend(*, synchronize: bool = True) -> None:
    """Open the shared collection runtime for the ``collection`` backend.

    No-op for the ``connect`` backend, or if the runtime is already open.
    """
    global _shared_runtime
    if resolve_backend() != COLLECTION_BACKEND or _shared_runtime is not None:
        return
    runtime = CollectionRuntime(_require_collection_path())
    await runtime.open()
    try:
        store = SyncStateStore(Path(f"{runtime.path}.sync.json"))
        driver = AnkiSyncDriver(
            runtime,
            CredentialStore(runtime.path),
            username=envs.ANKIWEB_USERNAME,
            password=envs.ANKIWEB_PASSWORD,
        )
        service = SyncService(driver, snapshot=store.load(), save=store.save)
        runtime.sync_service = service
        runtime.sync_driver = driver
        await service.start(authenticated=driver.authenticated, synchronize=synchronize)
    except BaseException:
        await runtime.close()
        raise
    _shared_runtime = runtime


async def stop_anki_backend() -> None:
    """Close the shared collection runtime if it is open."""
    global _shared_runtime
    if _shared_runtime is None:
        return
    runtime, _shared_runtime = _shared_runtime, None
    await runtime.close()


async def switch_backend() -> None:
    """Restart the backend after ``envs.ANKI_BACKEND``/``ANKI_COLLECTION_PATH``
    change, e.g. from a Settings-page save. Closes whatever is currently open
    (a no-op for ``connect``) before opening the newly configured backend.
    """
    await stop_anki_backend()
    await start_anki_backend()


@asynccontextmanager
async def anki_backend_scope(*, synchronize: bool = True) -> AsyncIterator[None]:
    """Own backend-wide resources for one process scope.

    For ``collection`` this opens the shared runtime on enter and closes it on
    exit (including on error). Nested scopes reuse the outer runtime and leave
    closing to whichever scope opened it. A no-op for ``connect``.
    """
    opened_here = get_shared_runtime() is None
    await start_anki_backend(synchronize=synchronize)
    try:
        yield
    finally:
        if opened_here:
            await stop_anki_backend()


def create_anki_client() -> AnkiCollectionClient:
    """Build the Anki client for the configured backend.

    Raises:
        AnkiBackendConfigError: If ``ANKI_BACKEND`` is unknown, a backend's
            required configuration is missing, or the ``collection`` backend is
            used without an active :func:`anki_backend_scope`.
    """
    backend = resolve_backend()

    if backend == CONNECT_BACKEND:
        return AnkiConnectClient()

    _require_collection_path()
    if _shared_runtime is None:
        raise AnkiBackendConfigError(
            "The 'collection' backend is not started; wrap the call in "
            "anki_backend_scope() (CLI) or start it at app startup (web)."
        )
    return DirectCollectionClient(_shared_runtime)
