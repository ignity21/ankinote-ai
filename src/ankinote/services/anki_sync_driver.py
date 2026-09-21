"""Official Anki sync APIs, executed exclusively on the collection worker."""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from ankinote.services.anki_credentials import CredentialStore, SyncCredential
from ankinote.services.anki_sync import (
    FullSyncRequired,
    SyncBackupError,
    SyncCredentialError,
    SyncMediaError,
    SyncNetworkError,
    SyncResult,
    SyncService,
    SyncSnapshot,
)

if TYPE_CHECKING:
    from anki.collection import Collection

    from ankinote.services.collection_runtime import CollectionRuntime


class AnkiSyncDriver:
    """Own secrets privately; return only plain, credential-free results."""

    def __init__(
        self,
        runtime: CollectionRuntime,
        store: CredentialStore,
        *,
        username: str = "",
        password: str = "",
    ) -> None:
        if bool(username.strip()) != bool(password):
            raise ValueError(
                "ANKIWEB_USERNAME and ANKIWEB_PASSWORD must be set together"
            )
        self._runtime = runtime
        self._store = store
        self._username = username.strip()
        self._password = password
        self._account_lock = asyncio.Lock()
        self.externally_configured = bool(username)
        self._credential = None if self.externally_configured else store.load()
        if self.externally_configured:
            store.check_account(self._username)

    @property
    def authenticated(self) -> bool:
        return self.externally_configured or self._credential is not None

    @property
    def account(self) -> str | None:
        """Public account label; never includes authentication tokens."""
        return (
            self._username
            if self.externally_configured
            else (self._credential.account if self._credential is not None else None)
        )

    async def _submit[T](self, operation: Callable[[Collection], T]) -> T:
        # Cancellation must not release sync's admission lock while native work runs.
        task = asyncio.create_task(self._runtime.submit(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise

    def _login(self, col: Collection, username: str, password: str) -> None:
        self._store.check_account(username)
        auth = col.sync_login(username, password, endpoint=None)
        credential = SyncCredential(
            username.strip().casefold(), auth.hkey, auth.endpoint or None
        )
        if self.externally_configured:
            self._store.bind(username)
        else:
            self._store.save(credential)
        self._credential = credential

    async def login(
        self, service: SyncService, username: str, password: str
    ) -> SyncSnapshot:
        """Renew a UI credential without ever returning it to the caller."""
        if self.externally_configured:
            raise ValueError("AnkiWeb credentials are externally configured")
        async with self._account_lock:
            self._store.check_account(username)
            await service.logout()
            await self._submit(
                lambda col: self._classified(
                    lambda: self._login(col, username, password)
                )
            )
            return await service.reauthenticate()

    async def logout(self, service: SyncService) -> None:
        """Drain active work, pause sync and remove only the private credential."""
        if self.externally_configured:
            raise ValueError("AnkiWeb credentials are externally configured")
        async with self._account_lock:
            await service.logout()
            self._credential = None
            self._store.remove()

    async def login_configured_account(self, service: SyncService) -> SyncSnapshot:
        """Explicitly retry deployment credentials after authentication failure."""
        if not self.externally_configured:
            raise ValueError("No deployment account is configured")
        async with self._account_lock:
            await service.logout()
            await self._submit(
                lambda col: self._classified(
                    lambda: self._login(col, self._username, self._password)
                )
            )
            return await service.reauthenticate()

    def _classified[T](self, operation: Callable[[], T]) -> T:
        from anki.errors import NetworkError, SyncError, SyncErrorKind

        try:
            return operation()
        except NetworkError:
            raise SyncNetworkError("AnkiWeb network failure") from None
        except SyncError as exc:
            if exc.kind == SyncErrorKind.AUTH:
                raise SyncCredentialError("AnkiWeb authentication failed") from None
            raise RuntimeError("AnkiWeb synchronization failed") from None
        except (
            FullSyncRequired,
            SyncBackupError,
            SyncMediaError,
            SyncCredentialError,
            SyncNetworkError,
        ):
            raise
        except Exception:
            raise RuntimeError("AnkiWeb operation failed") from None

    async def sync(self) -> SyncResult:
        return await self._submit(lambda col: self._classified(lambda: self._sync(col)))

    async def full_sync(self, direction: Literal["upload", "download"]) -> SyncResult:
        if direction not in ("upload", "download"):
            raise ValueError("Full sync direction must be upload or download")
        return await self._submit(
            lambda col: self._classified(lambda: self._sync(col, direction))
        )

    def _sync(  # noqa: C901 - existing sync state machine; refactor separately
        self, col: Collection, direction: Literal["upload", "download"] | None = None
    ) -> SyncResult:
        from anki.sync_pb2 import SyncAuth, SyncCollectionResponse

        if self._credential is None:
            if not self.externally_configured:
                raise SyncCredentialError("AnkiWeb login required")
            self._login(col, self._username, self._password)
        credential = self._credential
        assert credential is not None
        auth = SyncAuth(hkey=credential.hkey, endpoint=credential.endpoint)
        output = col.sync_collection(auth, sync_media=False)
        if output.new_endpoint:
            auth.endpoint = output.new_endpoint
            credential = SyncCredential(
                credential.account, credential.hkey, output.new_endpoint
            )
            if not self.externally_configured:
                self._store.save(credential)
            self._credential = credential
        if output.required in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_UPLOAD,
            SyncCollectionResponse.FULL_DOWNLOAD,
        ):
            directions: tuple[Literal["upload", "download"], ...] = (
                ("upload",)
                if output.required == SyncCollectionResponse.FULL_UPLOAD
                else ("download",)
                if output.required == SyncCollectionResponse.FULL_DOWNLOAD
                else ("upload", "download")
            )
            if direction is None:
                raise FullSyncRequired(directions)
            if (
                direction == "upload"
                and output.required == SyncCollectionResponse.FULL_DOWNLOAD
            ) or (
                direction == "download"
                and output.required == SyncCollectionResponse.FULL_UPLOAD
            ):
                raise FullSyncRequired(directions)
            # Keep each confirmed destructive operation's backup independently.
            folder = Path(f"{self._runtime.path}.backups") / uuid4().hex
            try:
                folder.mkdir(parents=True)
                if not col.create_backup(
                    backup_folder=str(folder), force=True, wait_for_completion=True
                ):
                    raise SyncBackupError()
            except Exception:
                raise SyncBackupError() from None
            col.close_for_full_sync()  # clears Anki's cached note types
            try:
                col.full_upload_or_download(
                    auth=auth,
                    server_usn=output.server_media_usn,
                    upload=direction == "upload",
                )
            finally:
                col.reopen(after_full_sync=True)
        # Normal sync also changes note types; discard Python-side cached objects.
        col.models._clear_cache()
        try:
            self._classified(lambda: col.sync_media(auth))
            while self._classified(col.media_sync_status).active:
                time.sleep(0.1)
        except SyncCredentialError:
            raise SyncMediaError(credentials=True) from None
        except SyncNetworkError:
            raise SyncMediaError(network=True) from None
        except Exception:
            raise SyncMediaError() from None
        return SyncResult()
