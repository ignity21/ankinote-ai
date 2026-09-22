"""Pure sync-status -> presentation mapping, kept free of NiceGUI/runtime deps."""

from dataclasses import dataclass

from ankinote.services.anki_sync import SyncSnapshot, SyncState
from ankinote.ui.i18n import t


@dataclass(frozen=True, slots=True)
class SyncPresentation:
    """Semantic text keys, separate from styling and backend enums."""

    title: str
    detail: str
    icon: str = "cloud_queue"
    attention: bool = False


def _error_presentation(status: SyncSnapshot) -> SyncPresentation | None:
    if status.error == "state_store":
        return SyncPresentation(
            "sync.state_store", "sync.state_store_help", "error_outline", True
        )
    if status.error == "credentials":
        return SyncPresentation(
            "sync.credentials", "sync.credentials_help", "login", True
        )
    return None


def _active_presentation(status: SyncSnapshot) -> SyncPresentation | None:
    if status.state not in (SyncState.SYNCING, SyncState.INITIALIZING):
        return None
    key = "sync.syncing" if status.initialized else "sync.initializing"
    return SyncPresentation(key, f"{key}_help", "sync")


def _full_sync_presentation(status: SyncSnapshot) -> SyncPresentation | None:
    if not status.full_sync_required:
        return None
    key = "sync.backup" if status.error == "backup" else "sync.choice"
    return SyncPresentation(key, f"{key}_help", "compare_arrows", True)


def _logged_out_presentation(status: SyncSnapshot) -> SyncPresentation | None:
    if status.state == SyncState.NOT_LOGGED_IN:
        return SyncPresentation(
            "sync.not_logged_in",
            "sync.offline_help" if status.initialized else "sync.first_help",
        )
    if status.state == SyncState.IDLE:
        return SyncPresentation("sync.idle", "sync.idle_help", "cloud_done")
    return None


def _pending_presentation(status: SyncSnapshot) -> SyncPresentation | None:
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
    return None


# Order matters: each presenter returns None to fall through to the next one,
# so this is a priority list, not an unordered set of independent checks.
_PRESENTERS = (
    _error_presentation,
    _active_presentation,
    _full_sync_presentation,
    _logged_out_presentation,
    _pending_presentation,
)


def present_sync(status: SyncSnapshot) -> SyncPresentation:
    """Describe current outcomes without implying that a save failed."""
    for presenter in _PRESENTERS:
        presentation = presenter(status)
        if presentation is not None:
            return presentation
    return SyncPresentation("sync.error", "sync.error_help", "error_outline", True)


def result_text(status: SyncSnapshot) -> str:
    if status.result is None:
        return ""
    if status.result.collection_ok and status.result.media_ok:
        outcome = "sync.result_ok"
    elif status.result.collection_ok:
        outcome = "sync.result_media"
    else:
        outcome = "sync.result_failed"
    return t("sync.last_result", result=t(outcome))
