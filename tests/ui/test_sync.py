"""Render real sync controls against a network-free service."""

import asyncio
import json
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from ankinote.services.anki_sync import (
    FullSyncRequired,
    SyncCredentialError,
    SyncResult,
    SyncService,
    SyncSnapshot,
    SyncState,
)
from ankinote.ui import sync
from ankinote.ui.i18n import set_locale, t


@pytest.fixture
async def context(monkeypatch):
    driver = SimpleNamespace(
        account="learner@example.com",
        externally_configured=False,
        sync=AsyncMock(return_value=SyncResult()),
        full_sync=AsyncMock(return_value=SyncResult()),
    )
    service = SyncService(
        driver, snapshot=SyncSnapshot(state=SyncState.IDLE, initialized=True)
    )
    await service.start(authenticated=True, synchronize=False)

    async def login(service, email, password):
        driver.account = email
        return await service.reauthenticate()

    async def logout(service):
        await service.logout()
        driver.account = None

    driver.login = AsyncMock(side_effect=login)
    driver.logout = AsyncMock(side_effect=logout)
    runtime = SimpleNamespace(sync_service=service, sync_driver=driver)
    monkeypatch.setattr(sync, "get_shared_runtime", lambda: runtime)
    set_locale("en")
    yield service, driver
    await service.close()


@pytest.mark.parametrize("state", list(SyncState))
async def test_every_state_renders(context, state):
    service, _ = context
    service._snapshot = SyncSnapshot(
        state=state,
        initialized=state != SyncState.INITIALIZING,
        full_sync_required=state == SyncState.NEEDS_FULL_SYNC_CHOICE,
    )
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        await user.should_see(t(sync.present_sync(service.status).title))
        if state == SyncState.NEEDS_FULL_SYNC_CHOICE:
            await user.should_see("Which data would you like to use?")
            assert (
                not user.find(kind=ui.button, content="Continue").elements.pop().enabled
            )


async def test_full_sync_requires_selection_and_confirmation(context):
    service, driver = context
    driver.sync.side_effect = FullSyncRequired(("upload",))
    await service.sync_now()
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        await user.should_not_see("Use the data on AnkiWeb")
        user.find("Use the local data in AnkiNote").click()
        user.find(kind=ui.button, content="Continue").click()
        await user.should_see("Upload and replace")
        driver.full_sync.assert_not_awaited()
        user.find(kind=ui.button, content="Back").click()
        driver.full_sync.assert_not_awaited()
        user.find(kind=ui.button, content="Continue").click()
        user.find(kind=ui.button, content="Upload and replace").click()
        await user.should_see("Synced to AnkiWeb")
        driver.full_sync.assert_awaited_once_with("upload")


async def test_login_failure_keeps_email_clears_password_and_does_not_leak(context):
    service, driver = context
    await service.logout()
    driver.account = None
    driver.login.side_effect = SyncCredentialError("secret-token")
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        user.find(kind=ui.button, content="Log in to AnkiWeb").click()
        user.find("AnkiWeb email").type("learner@example.com")
        user.find("AnkiWeb password").type("private-password")
        user.find(kind=ui.button, content="Log in and sync").click()
        await user.should_see("Login failed. Check your email and password.")
        assert user.find("AnkiWeb email").elements.pop().value == "learner@example.com"
        assert user.find("AnkiWeb password").elements.pop().value == ""
        await user.should_not_see("secret-token")


async def test_status_refresh_preserves_login_draft(context):
    service, driver = context
    await service.logout()
    driver.account = None
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        user.find(kind=ui.button, content="Log in to AnkiWeb").click()
        user.find("AnkiWeb email").type("draft@example.com")
        user.find("AnkiWeb password").type("draft-password")
        service._snapshot = replace(service.status, error="state_store")
        await user.should_see("Could not save sync status")
        assert user.find("AnkiWeb email").elements.pop().value == "draft@example.com"
        assert user.find("AnkiWeb password").elements.pop().value == "draft-password"


async def test_environment_account_has_no_ui_login_or_logout(context):
    _, driver = context
    driver.externally_configured = True
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        await user.should_see("This account is managed by deployment settings.")
        await user.should_not_see("Log out")
        await user.should_not_see("Log in to AnkiWeb")


async def test_double_click_sync_coalesces(context):
    _, driver = context
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow():
        entered.set()
        await release.wait()
        return SyncResult()

    driver.sync.side_effect = slow
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        user.find(kind=ui.button, content="Sync now").click()
        await entered.wait()
        await user.should_see("Syncing…")
        release.set()
        await user.should_see("Synced to AnkiWeb")
        driver.sync.assert_awaited_once()


async def test_deferred_rerender_keeps_page_locale(context):
    """A click handler re-rendering labels must not fall back to English.

    Event-handler and ``ui.timer`` callbacks run in their own asyncio tasks,
    which do not inherit the request-time locale contextvar. The sync panel
    relabels itself from inside :meth:`SyncPanel.run`, so without a
    client-scoped locale those labels flashed back to English.
    """
    _, driver = context
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow():
        entered.set()
        await release.wait()
        return SyncResult()

    driver.sync.side_effect = slow

    def page() -> None:
        set_locale("zh-CN")
        sync.sync_settings()

    async with user_simulation(page) as user:
        await user.open("/")
        user.find(kind=ui.button, content="立即同步").click()
        await entered.wait()
        await user.should_see("正在同步…")
        await user.should_not_see("Syncing…")
        release.set()
        await user.should_see("已同步到 AnkiWeb")
        await user.should_not_see("Synced to AnkiWeb")


async def test_connect_mode_has_desktop_guidance(monkeypatch):
    monkeypatch.setattr(sync, "get_shared_runtime", lambda: None)
    async with user_simulation(sync.sync_settings) as user:
        await user.open("/")
        await user.should_see("Connected through Anki desktop.")
        await user.should_not_see("AnkiWeb password")


def test_sync_strings_exist_in_both_locales():
    root = Path(__file__).parents[2] / "src/ankinote/ui"
    en = json.loads((root / "i18n/locales/en.json").read_text())
    zh = json.loads((root / "i18n/locales/zh-CN.json").read_text())
    keys = {key for key in en if key.startswith("sync.")}
    assert keys == {key for key in zh if key.startswith("sync.")}
    for key in keys:
        assert en[key] and zh[key]
        assert set(re.findall(r"\{([^}]+)\}", en[key])) == set(
            re.findall(r"\{([^}]+)\}", zh[key])
        )
    for key in re.findall(r'["\'](sync\.[a-z_]+)["\']', (root / "sync.py").read_text()):
        assert key in keys
