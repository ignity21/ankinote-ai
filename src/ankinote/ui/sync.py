"""AnkiWeb settings and unobtrusive, shared save-page status feedback."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from nicegui import ui

from ankinote.services.anki_batch import recoverable_save
from ankinote.services.anki_factory import get_shared_runtime
from ankinote.services.anki_sync import (
    SyncCredentialError,
    SyncNetworkError,
    SyncService,
    SyncSnapshot,
    SyncState,
)
from ankinote.services.anki_sync_driver import AnkiSyncDriver
from ankinote.ui.i18n import t


@dataclass(frozen=True, slots=True)
class SyncPresentation:
    """Semantic text keys, separate from styling and backend enums."""

    title: str
    detail: str
    icon: str = "cloud_queue"
    attention: bool = False


def present_sync(status: SyncSnapshot) -> SyncPresentation:
    """Describe current outcomes without implying that a save failed."""
    if status.error == "state_store":
        return SyncPresentation(
            "sync.state_store", "sync.state_store_help", "error_outline", True
        )
    if status.error == "credentials":
        return SyncPresentation(
            "sync.credentials", "sync.credentials_help", "login", True
        )
    if status.state in (SyncState.SYNCING, SyncState.INITIALIZING):
        key = "sync.syncing" if status.initialized else "sync.initializing"
        return SyncPresentation(key, f"{key}_help", "sync")
    if status.full_sync_required:
        key = "sync.backup" if status.error == "backup" else "sync.choice"
        return SyncPresentation(key, f"{key}_help", "compare_arrows", True)
    if status.state == SyncState.NOT_LOGGED_IN:
        return SyncPresentation(
            "sync.not_logged_in",
            "sync.offline_help" if status.initialized else "sync.first_help",
        )
    if status.state == SyncState.IDLE:
        return SyncPresentation("sync.idle", "sync.idle_help", "cloud_done")
    if status.error == "media":
        detail = (
            "sync.retry_help"
            if status.state == SyncState.PENDING
            else "sync.media_help"
        )
        return SyncPresentation("sync.media", detail, "cloud_off", True)
    if status.state == SyncState.PENDING:
        detail = "sync.retry_help" if status.initialized else "sync.first_retry_help"
        return SyncPresentation("sync.pending", detail, "cloud_off", True)
    return SyncPresentation("sync.error", "sync.error_help", "error_outline", True)


def _result_text(status: SyncSnapshot) -> str:
    if status.result is None:
        return ""
    if status.result.collection_ok and status.result.media_ok:
        outcome = "sync.result_ok"
    elif status.result.collection_ok:
        outcome = "sync.result_media"
    else:
        outcome = "sync.result_failed"
    return t("sync.last_result", result=t(outcome))


def save_allowed() -> bool:
    """Check before generation as well as at the backend write boundary."""
    runtime = get_shared_runtime()
    return (
        runtime is None
        or runtime.sync_service is None
        or not runtime.sync_service.write_blocked
    )


def saved_message() -> str:
    return (
        t("sync.saved")
        if get_shared_runtime() is not None
        else t("common.added_to_anki")
    )


async def retain_generated_save[T](
    operation: Callable[[], Awaitable[T]], container: ui.element
) -> T:
    """Resume only the prepared write when sync blocks it after generation."""
    task = asyncio.current_task()
    if task is not None:
        container.client.on_delete(task.cancel)
    progress: ui.label | None = None

    def on_saved() -> None:
        nonlocal progress
        if container.is_deleted:
            return
        if progress is None:
            with container:
                progress = ui.label(t("sync.saved_waiting")).props("role=status")

    async def wait_for_retry() -> None:
        ready = asyncio.Event()

        def retry() -> None:
            if save_allowed():
                ready.set()
            else:
                ui.notify(t("sync.write_blocked"), type="warning")

        with container, ui.column().classes("w-full gap-2") as recovery:
            ui.label(t("sync.prepared")).props("role=status")
            ui.link(t("sync.resolve_new_tab"), "/settings#anki-sync", new_tab=True)
            ui.button(t("sync.retry_save"), on_click=retry).props("outline no-caps")
        try:
            await ready.wait()
        finally:
            if not recovery.is_deleted:
                recovery.delete()

    try:
        with recoverable_save(wait_for_retry, on_saved):
            return await operation()
    finally:
        if progress is not None and not progress.is_deleted:
            progress.delete()


def sync_feedback() -> None:
    """A stable status region for card and note-type pages; never toasts."""
    runtime = get_shared_runtime()
    if runtime is None or runtime.sync_service is None:
        return
    service = runtime.sync_service
    with (
        ui.column()
        .classes("w-full gap-1 text-sm")
        .props("role=status aria-live=polite")
    ):
        status_label = ui.label()
        blocked_label = ui.label(t("sync.write_blocked")).classes(
            "text-amber-800 dark:text-amber-300"
        )
        ui.link(t("sync.view"), "/settings#anki-sync")

    def update() -> None:
        view = present_sync(service.status)
        message = f"{t(view.title)}. {t(view.detail)}"
        if status_label.text != message:
            status_label.set_text(message)
        blocked_label.set_visibility(service.write_blocked)

    update()
    ui.timer(1, update)


class SyncPanel:
    """Keep inputs mounted while state changes, including during authentication."""

    def __init__(self, service: SyncService, driver: AnkiSyncDriver) -> None:
        self.service = service
        self.driver = driver
        self.busy = False
        self.login_open = False
        self._directions: tuple[str, ...] = ()
        self._snapshot: SyncSnapshot | None = None
        self._account: str | None = None

        with ui.column().classes("anki-sync w-full gap-4").props("id=anki-sync"):
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label(t("sync.title")).classes("text-lg font-semibold")
                self.sync_button = ui.button(
                    t("sync.now"),
                    on_click=lambda: self.run(service.sync_now),
                    icon="sync",
                ).props("unelevated no-caps")
            with (
                ui.column()
                .classes("w-full gap-1")
                .props("role=status aria-live=polite aria-atomic=true")
            ):
                with ui.row().classes("items-center gap-2"):
                    self.icon = ui.icon("cloud_queue")
                    self.spinner = ui.spinner(size="1.2em")
                    self.title = ui.label().classes("font-medium")
                self.detail = ui.label().classes("sync-muted")
                self.last = ui.label().classes("sync-muted text-sm")
                self.result = ui.label().classes("sync-muted text-sm")
                self.blocked = ui.label(t("sync.write_blocked")).classes(
                    "sync-attention text-sm"
                )
            self.error = (
                ui.label().classes("sync-attention text-sm").props("role=alert")
            )

            with ui.row().classes("w-full justify-between items-center gap-2"):
                self.account = ui.label().classes("text-sm break-all")
                with ui.row().classes("gap-2"):
                    self.login_button = ui.button(
                        t("sync.login"), on_click=self.open_login
                    ).props("flat no-caps")
                    self.logout_button = ui.button(
                        t("sync.logout"),
                        on_click=lambda: self.run(lambda: driver.logout(service)),
                    ).props("flat no-caps")
            self.managed = ui.label(t("sync.managed_help")).classes(
                "sync-muted text-sm"
            )
            self.configured_login = ui.button(
                t("sync.retry_login"),
                on_click=lambda: self.run(
                    lambda: driver.login_configured_account(service)
                ),
            ).props("outline no-caps")
            self.logout_help = ui.label(t("sync.logout_help")).classes(
                "sync-muted text-sm"
            )
            with ui.column().classes("w-full gap-3") as self.login_form:
                self.email = (
                    ui.input(t("sync.email"))
                    .props("type=email autocomplete=username")
                    .classes("w-full")
                )
                self.password = (
                    ui.input(
                        t("sync.password"), password=True, password_toggle_button=True
                    )
                    .props("autocomplete=current-password")
                    .classes("w-full")
                )
                self.password.on("keydown.enter", self.login)
                with ui.row().classes("gap-2"):
                    self.submit_login = ui.button(
                        t("sync.login_sync"), on_click=self.login
                    ).props("unelevated no-caps")
                    ui.button(t("common.cancel"), on_click=self.close_login).props(
                        "flat no-caps"
                    )

            with ui.column().classes("sync-choice w-full gap-3") as self.choice:
                ui.label(t("sync.choose_source")).classes("font-semibold")
                ui.label(t("sync.choose_help")).classes("text-sm")
                self.radio = ui.radio({}, value=None).classes("w-full")
                self.direction_help = ui.label().classes("text-sm sync-muted")
                self.radio.on_value_change(lambda _: self.update_selection())
                self.continue_button = ui.button(
                    t("sync.continue"), on_click=self.confirm
                ).props("unelevated no-caps")

            with ui.expansion(t("sync.interval"), icon="schedule").classes(
                "w-full"
            ) as self.interval:
                ui.label(t("sync.interval_help")).classes("sync-muted text-sm")
                self.minutes = ui.number(
                    t("sync.minutes"),
                    value=service.status.interval_seconds / 60,
                    min=1,
                    step=1,
                    precision=0,
                ).classes("w-full")
                self.interval_button = ui.button(
                    t("sync.save_interval"), on_click=self.save_interval
                ).props("flat no-caps")
                self.interval_result = (
                    ui.label().classes("text-sm").props("role=status")
                )
        self.update(force=True)
        ui.timer(1, self.update)

    def open_login(self) -> None:
        self.login_open = True
        self.email.set_value(self.driver.account or self.email.value or "")
        self.update(force=True)
        self.email.run_method("focus")

    def close_login(self) -> None:
        self.login_open = False
        self.password.set_value("")
        self.update(force=True)

    async def run(self, operation: Callable[[], Awaitable[object]]) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.error.set_text("")
        self.update(force=True)
        try:
            await operation()
        except SyncCredentialError:
            self.error.set_text(t("sync.login_failed"))
        except SyncNetworkError:
            self.error.set_text(t("sync.login_network"))
        except ValueError:
            self.error.set_text(t("sync.account_or_state"))
        except Exception:
            self.error.set_text(t("sync.operation_failed"))
        else:
            return True
        finally:
            self.busy = False
            self.update(force=True)
        return False

    async def login(self) -> None:
        if self.busy:
            return
        email, password = (self.email.value or "").strip(), self.password.value or ""
        if not email or not password:
            self.error.set_text(t("sync.login_fields"))
            return
        try:
            if await self.run(lambda: self.driver.login(self.service, email, password)):
                self.login_open = False
        finally:
            self.password.set_value("")
            self.update(force=True)

    def save_interval(self) -> None:
        try:
            minutes = float(self.minutes.value or 0)
            if not minutes.is_integer() or minutes < 1:
                raise ValueError()
            self.service.set_interval(minutes * 60)
        except ValueError:
            self.interval_result.set_text(t("sync.interval_invalid"))
        except Exception:
            self.interval_result.set_text(t("sync.interval_failed"))
        else:
            self.interval_result.set_text(t("sync.interval_saved"))
        self.update(force=True)

    def update_selection(self) -> None:
        direction = self.radio.value
        self.direction_help.set_text(
            t(f"sync.{direction}_help") if direction else t("sync.no_default")
        )
        self.continue_button.set_enabled(
            not self.busy and direction in self.service.status.directions
        )

    def confirm(self) -> None:
        direction = self.radio.value
        if self.busy or direction not in ("upload", "download"):
            return
        self._confirm_direction(direction)

    def _confirm_direction(self, direction: Literal["upload", "download"]) -> None:
        expected = self.service.status
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg gap-4"):
            ui.label(t(f"sync.{direction}_confirm")).classes("text-lg font-semibold")
            ui.label(t(f"sync.{direction}_help"))
            ui.label(t("sync.backup_notice")).classes("text-sm")

            async def execute() -> None:
                if self.busy:
                    return
                dialog.close()
                if self.service.status != expected:
                    self.error.set_text(t("sync.state_changed"))
                    return
                await self.run(
                    lambda: self.service.resolve_full_sync(
                        direction, self.driver.full_sync
                    )
                )

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("sync.back"), on_click=dialog.close).props("flat no-caps")
                ui.button(t(f"sync.{direction}_confirm"), on_click=execute).props(
                    "unelevated no-caps color=negative"
                )
        dialog.open()

    def update(self, *, force: bool = False) -> None:
        status = self.service.status
        if (
            not force
            and self._snapshot == status
            and self._account == self.driver.account
        ):
            return
        new_choice = status.full_sync_required and (
            self._snapshot is None or not self._snapshot.full_sync_required
        )
        self._snapshot, self._account = status, self.driver.account
        active = self.busy or status.state in (
            SyncState.SYNCING,
            SyncState.INITIALIZING,
        )
        authenticated = (
            status.state != SyncState.NOT_LOGGED_IN and status.error != "credentials"
        )
        self._update_status_text(status, active)
        self._update_account_area(status, active, authenticated)
        self._update_login_form(active)
        self._update_choice(status, active, authenticated, new_choice)

    def _update_status_text(self, status: SyncSnapshot, active: bool) -> None:
        view = present_sync(status)
        self.title.set_text(t(view.title))
        self.detail.set_text(t(view.detail))
        self.icon.props(f"name={view.icon}")
        self.title.classes(
            remove="sync-attention", add="sync-attention" if view.attention else ""
        )
        self.last.set_text(
            t(
                "sync.last",
                time=status.last_success.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            )
            if status.last_success
            else t("sync.never")
        )
        self.result.set_text(_result_text(status))
        self.blocked.set_visibility(self.service.write_blocked)
        self.spinner.set_visibility(active)
        self.icon.set_visibility(not active)
        self.interval.set_text(
            t("sync.interval_summary", minutes=f"{status.interval_seconds / 60:g}")
        )

    def _update_account_area(
        self, status: SyncSnapshot, active: bool, authenticated: bool
    ) -> None:
        self.sync_button.set_enabled(
            not active and authenticated and not status.full_sync_required
        )
        self.sync_button.set_text(t("sync.syncing" if active else "sync.now"))
        self.account.set_text(
            t("sync.account", account=self.driver.account)
            if self.driver.account
            else t("sync.not_logged_in")
        )
        self.managed.set_visibility(self.driver.externally_configured)
        self.configured_login.set_visibility(
            self.driver.externally_configured and not authenticated
        )
        self.configured_login.set_enabled(not active)
        self.login_button.set_visibility(
            not self.driver.externally_configured and not authenticated
        )
        self.login_button.set_enabled(not active)
        self.logout_button.set_visibility(
            not self.driver.externally_configured and self.driver.account is not None
        )
        self.logout_button.set_enabled(not active)
        self.logout_help.set_visibility(self.logout_button.visible)

    def _update_login_form(self, active: bool) -> None:
        self.login_form.set_visibility(
            self.login_open and not self.driver.externally_configured
        )
        self.submit_login.set_enabled(not active)

    def _update_choice(
        self,
        status: SyncSnapshot,
        active: bool,
        authenticated: bool,
        new_choice: bool,
    ) -> None:
        self.choice.set_visibility(status.full_sync_required and authenticated)
        if new_choice or self._directions != status.directions:
            self._directions = status.directions
            self.radio.set_options(
                {d: t(f"sync.use_{d}") for d in status.directions}, value=None
            )
        self.update_selection()
        self.continue_button.set_enabled(
            not active and self.radio.value in status.directions
        )


def sync_settings() -> None:
    """Use the application's existing runtime; connect mode remains desktop-owned."""
    ui.add_css("""
        .anki-sync { color: #0f172a; scroll-margin-top: 5rem; }
        .anki-sync .sync-muted { color: #475569; line-height: 1.6; }
        .anki-sync .sync-attention { color: #92400e; }
        .anki-sync .sync-choice { border-left: 3px solid #3d6fa6; padding: 1rem; background: #f3f7fb; }
        .anki-sync :focus-visible { outline: 2px solid #3d6fa6; outline-offset: 3px; }
        .body--dark .anki-sync { color: #e2e8f0; }
        .body--dark .anki-sync .sync-muted { color: #cbd5e1; }
        .body--dark .anki-sync .sync-attention { color: #fcd34d; }
        .body--dark .anki-sync .sync-choice { background: #242833; border-color: #6fa8dc; }
        .body--dark .anki-sync :focus-visible { outline-color: #6fa8dc; }
        @media (prefers-reduced-motion: reduce) { .anki-sync * { animation: none !important; transition: none !important; } }
    """)
    runtime = get_shared_runtime()
    if runtime is None or runtime.sync_service is None or runtime.sync_driver is None:
        with ui.column().classes("w-full gap-1").props("id=anki-sync"):
            ui.label(t("sync.title")).classes("text-lg font-semibold")
            ui.label(t("sync.connect_help")).classes(
                "text-sm text-slate-600 dark:text-slate-300"
            )
    else:
        SyncPanel(runtime.sync_service, runtime.sync_driver)
    ui.separator()
