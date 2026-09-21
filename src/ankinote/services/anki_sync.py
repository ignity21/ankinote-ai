"""Network-independent sync scheduling and write admission.

The owner starts/closes the service and supplies a driver. Drivers finish both
collection and media work before returning, and never perform local card writes.
Persisted snapshots can be supplied on restart; credentials are never part of them.
"""

import asyncio
import math
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, Protocol

from pydantic import TypeAdapter


class SyncState(StrEnum):
    NOT_LOGGED_IN = "not_logged_in"
    INITIALIZING = "initializing"
    IDLE = "idle"
    SYNCING = "syncing"
    PENDING = "pending"
    NEEDS_FULL_SYNC_CHOICE = "needs_full_sync_choice"
    ERROR = "error"


class SyncNetworkError(Exception):
    """A transient failure that can be retried without repeating local writes."""


class SyncCredentialError(Exception):
    """Authentication must be renewed before any further sync attempt."""


class SyncMediaError(Exception):
    """Collection succeeded; media failed, optionally requiring retry or login."""

    def __init__(self, *, network: bool = False, credentials: bool = False) -> None:
        super().__init__("AnkiWeb media synchronization failed")
        self.network = network
        self.credentials = credentials


class FullSyncRequired(Exception):
    """An explicit upload/download choice is required."""

    def __init__(
        self,
        directions: tuple[Literal["upload", "download"], ...] = ("upload", "download"),
    ) -> None:
        super().__init__("Full sync requires a data source choice")
        self.directions = directions


class SyncBackupError(Exception):
    """No replacement started because the required backup failed."""


class SyncWriteBlocked(Exception):
    """The collection is not currently safe for application writes."""


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Separate outcomes; a media failure does not undo collection success."""

    collection_ok: bool = True
    media_ok: bool = True


@dataclass(frozen=True, slots=True)
class SyncSnapshot:
    """Credential-free durable state exposed to status consumers."""

    state: SyncState = SyncState.NOT_LOGGED_IN
    initialized: bool = False
    full_sync_required: bool = False
    last_success: datetime | None = None
    result: SyncResult | None = None
    error: str | None = None
    directions: tuple[Literal["upload", "download"], ...] = ("upload", "download")
    interval_seconds: float = 300


class SyncDriver(Protocol):
    """Perform one synchronization; classify failures with the exceptions above."""

    async def sync(self) -> SyncResult: ...


class SyncStateStore:
    """Atomically replace a credential-free JSON snapshot on local disk."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._adapter = TypeAdapter(SyncSnapshot)

    def load(self) -> SyncSnapshot:
        """Restore saved state; missing files represent a fresh collection.

        Invalid or unreadable files raise rather than silently enabling writes.
        """
        try:
            data = self._path.read_bytes()
        except FileNotFoundError:
            return SyncSnapshot()
        return self._adapter.validate_json(data)

    def save(self, snapshot: SyncSnapshot) -> None:
        """Persist a complete snapshot, leaving the old file intact on failure."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self._path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(self._adapter.dump_json(snapshot))
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                temporary.replace(self._path)
            finally:
                temporary.unlink(missing_ok=True)


class SyncService:
    """Coalesce requests and serialize sync with admitted writes.

    ``save`` persists each snapshot synchronously before it becomes visible.
    A caller's cancellation does not cancel a shared sync. ``close`` does cancel
    owned tasks and waits for their cleanup. Callers must finish writes first.
    """

    def __init__(
        self,
        driver: SyncDriver,
        *,
        snapshot: SyncSnapshot | None = None,
        save: Callable[[SyncSnapshot], None] | None = None,
        interval: float | None = None,
        retry_initial: float = 1,
        retry_max: float = 300,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        interval = (
            interval
            if interval is not None
            else (snapshot or SyncSnapshot()).interval_seconds
        )
        if (
            not math.isfinite(interval)
            or interval <= 0
            or retry_initial <= 0
            or retry_max < retry_initial
        ):
            raise ValueError(
                "Sync interval and retry bounds must be positive and ordered"
            )
        self._driver = driver
        self._snapshot = replace(snapshot or SyncSnapshot(), interval_seconds=interval)
        self._save = save
        self._interval = interval
        self._retry_initial = retry_initial
        self._retry_max = retry_max
        self._retry_delay = retry_initial
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._attempt: asyncio.Task[SyncSnapshot] | None = None
        self._timer: asyncio.Task[None] | None = None
        self._retry: asyncio.Task[None] | None = None
        self._manual: asyncio.Task[SyncSnapshot] | None = None
        self._authenticated = False
        self._persistence_failed = False
        self._started = False
        self._closed = False

    @property
    def status(self) -> SyncSnapshot:
        """Return an immutable status without acquiring the collection lock."""
        return self._snapshot

    @property
    def write_blocked(self) -> bool:
        """Expose admission policy without opening or locking the collection."""
        return (
            self._persistence_failed
            or not self.status.initialized
            or self.status.full_sync_required
        )

    def set_interval(self, seconds: float) -> None:
        """Persist the interval before restarting the periodic timer."""
        self._ensure_running()
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Sync interval must be positive and finite")
        self._update(interval_seconds=seconds)
        self._interval = seconds
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.create_task(self._periodic())

    async def sync_now(self) -> SyncSnapshot:
        """Skip network backoff for an explicit request, coalescing active work."""
        self._ensure_running()
        if self._manual is None or self._manual.done():
            self._manual = asyncio.create_task(self._sync_now())
        return await asyncio.shield(self._manual)

    async def _sync_now(self) -> SyncSnapshot:
        """Drop any pending backoff, then join the one shared attempt."""
        retry, self._retry = self._retry, None
        if retry is not None:
            retry.cancel()
            await asyncio.gather(retry, return_exceptions=True)
        return await self.request()

    def _update(self, **changes: object) -> None:
        updated = replace(self._snapshot, **changes)
        if self._save is not None:
            try:
                self._save(updated)
            except Exception:
                self._persistence_failed = True
                # Retain safety flags even if the durable write failed.
                self._snapshot = replace(
                    updated, state=SyncState.ERROR, error="state_store"
                )
                raise
            self._persistence_failed = False
        self._snapshot = updated

    async def start(
        self, *, authenticated: bool = False, synchronize: bool = True
    ) -> SyncSnapshot:
        """Start the five-minute timer and await the initial attempt if logged in."""
        if self._closed or self._started:
            raise RuntimeError("Sync service is already started or closed")
        self._started = True
        self._authenticated = authenticated
        self._timer = asyncio.create_task(self._periodic())
        if not authenticated:
            self._update(state=SyncState.NOT_LOGGED_IN)
        elif self.status.error == "credentials":
            self._authenticated = False
            self._update(state=SyncState.ERROR)
        return await self.request() if synchronize else self.status

    async def reauthenticate(self) -> SyncSnapshot:
        """Resume attempts after the owner has successfully renewed credentials."""
        self._ensure_running()
        self._authenticated = True
        self._retry_delay = self._retry_initial
        self._update(error=None)
        return await self.request()

    async def logout(self) -> None:
        """Pause automatic sync; credential removal belongs to the owner."""
        self._ensure_running()
        self._authenticated = False
        await self._cancel_work()
        self._update(state=SyncState.NOT_LOGGED_IN, error=None)

    def _ensure_running(self) -> None:
        if not self._started or self._closed:
            raise RuntimeError("Sync service is not running")

    async def request(self) -> SyncSnapshot:
        """Await one shared attempt, returning offline/error status promptly."""
        self._ensure_running()
        if not self._authenticated:
            return self.status
        if self._attempt is not None and not self._attempt.done():
            return await asyncio.shield(self._attempt)
        if self.status.full_sync_required:
            self._update(state=SyncState.NEEDS_FULL_SYNC_CHOICE)
            return self.status
        if self._retry is not None and not self._retry.done():
            return self.status
        self._attempt = asyncio.create_task(self._run())
        return await asyncio.shield(self._attempt)

    async def resolve_full_sync(
        self,
        direction: Literal["upload", "download"],
        operation: Callable[[Literal["upload", "download"]], Awaitable[SyncResult]],
    ) -> SyncSnapshot:
        """Execute an explicit direction once; failed attempts keep writes blocked."""
        self._ensure_running()
        if direction not in ("upload", "download"):
            raise ValueError("Full sync direction must be upload or download")
        if not self._authenticated or not self.status.full_sync_required:
            raise ValueError("No authenticated full-sync choice is pending")
        if self._attempt is not None and not self._attempt.done():
            return await asyncio.shield(self._attempt)
        self._attempt = asyncio.create_task(self._run(lambda: operation(direction)))
        return await asyncio.shield(self._attempt)

    async def _run(  # noqa: C901 - existing sync state machine; refactor separately
        self, operation: Callable[[], Awaitable[SyncResult]] | None = None
    ) -> SyncSnapshot:
        async with self._lock:
            self._update(
                state=SyncState.SYNCING
                if self.status.initialized
                else SyncState.INITIALIZING,
                error=None,
            )
            try:
                result = await (operation or self._driver.sync)()
            except FullSyncRequired as exc:
                self._update(
                    state=SyncState.NEEDS_FULL_SYNC_CHOICE,
                    full_sync_required=True,
                    error="full_sync_required",
                    directions=exc.directions,
                )
            except SyncBackupError:
                self._update(state=SyncState.ERROR, error="backup")
            except SyncMediaError as exc:
                self._update(
                    result=SyncResult(collection_ok=True, media_ok=False),
                    initialized=True,
                    full_sync_required=False,
                    state=SyncState.PENDING if exc.network else SyncState.ERROR,
                    error="credentials" if exc.credentials else "media",
                )
                if exc.credentials:
                    self._authenticated = False
                elif exc.network:
                    self._schedule_retry()
            except SyncCredentialError:
                self._authenticated = False
                self._update(state=SyncState.ERROR, error="credentials")
            except SyncNetworkError:
                self._update(state=SyncState.PENDING, error="network")
                self._schedule_retry()
            except asyncio.CancelledError:
                self._update(state=SyncState.PENDING, error="cancelled")
                raise
            except Exception:
                # Never expose arbitrary driver messages (which may contain secrets).
                self._update(state=SyncState.ERROR, error="driver")
            else:
                self._update(
                    result=result,
                    full_sync_required=False,
                    initialized=result.collection_ok or self.status.initialized,
                )
                if result.collection_ok and result.media_ok:
                    self._retry_delay = self._retry_initial
                    self._update(
                        state=SyncState.IDLE,
                        initialized=True,
                        last_success=datetime.now(UTC),
                    )
                else:
                    self._update(
                        state=SyncState.ERROR,
                        error="media" if result.collection_ok else "collection",
                    )
            return self.status

    def _schedule_retry(self) -> None:
        delay = self._retry_delay
        self._retry_delay = min(delay * 2, self._retry_max)
        self._retry = asyncio.create_task(self._retry_after(delay))

    async def _retry_after(self, delay: float) -> None:
        await self._sleep(delay)
        self._retry = None
        await self.request()

    async def _periodic(self) -> None:
        while True:
            await self._sleep(self._interval)
            await self.request()

    @asynccontextmanager
    async def write_scope(self) -> AsyncIterator[None]:
        """Reject unsafe writes, then hold sync off until the write completes."""
        self._ensure_running()
        self._check_write()
        async with self._lock:
            self._ensure_running()
            self._check_write()
            yield

    def _check_write(self) -> None:
        if (
            self._persistence_failed
            or not self.status.initialized
            or self.status.full_sync_required
        ):
            raise SyncWriteBlocked(f"Anki writes are blocked: {self.status.state}")

    async def _cancel_work(self) -> None:
        tasks = [
            task
            for task in (self._manual, self._retry, self._attempt)
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            await asyncio.gather(task, return_exceptions=True)
        self._retry = None
        self._attempt = None
        self._manual = None

    async def close(self) -> None:
        """Stop timer, backoff, and active sync; safe to call repeatedly."""
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            self._timer.cancel()
            await asyncio.gather(self._timer, return_exceptions=True)
        await self._cancel_work()
