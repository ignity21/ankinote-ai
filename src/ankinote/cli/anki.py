"""Explicit AnkiWeb account and sync commands, sharing the application runtime."""

import asyncio
import json
from dataclasses import asdict
from typing import Literal

import click

from ankinote.services.anki_factory import (
    anki_backend_scope,
    get_shared_runtime,
)
from ankinote.services.anki_sync import SyncState


@click.group()
def anki() -> None:
    """Manage AnkiWeb sync (requires ANKI_BACKEND=collection).

    Stop the GUI before using these commands on the same collection.
    """


async def _execute(
    command: str,
    *,
    email: str = "",
    password: str = "",
    direction: Literal["upload", "download"] | None = None,
) -> int:
    # Status and logout must not trigger startup network activity. Explicit
    # sync/login perform exactly the action the command requested.
    async with anki_backend_scope(synchronize=False):
        runtime = get_shared_runtime()
        if (
            runtime is None
            or runtime.sync_service is None
            or runtime.sync_driver is None
        ):
            raise click.ClickException(
                "Use Anki desktop to sync, or configure ANKI_BACKEND=collection and ANKI_COLLECTION_PATH."
            )
        service, driver = runtime.sync_service, runtime.sync_driver
        match command:
            case "login":
                await driver.login(service, email, password)
            case "logout":
                await driver.logout(service)
            case "sync":
                if (
                    driver.externally_configured
                    and service.status.error == "credentials"
                ):
                    await driver.login_configured_account(service)
                else:
                    await service.sync_now()
                if direction is not None and service.status.full_sync_required:
                    await service.resolve_full_sync(direction, driver.full_sync)
        status = service.status
        click.echo(
            json.dumps(
                {
                    **asdict(status),
                    "account": driver.account,
                    "externally_configured": driver.externally_configured,
                    "write_blocked": service.write_blocked,
                },
                default=str,
                ensure_ascii=False,
                indent=2,
            )
        )
        if command == "logout":
            return 0
        return int(
            status.state != SyncState.IDLE
            or status.full_sync_required
            or service.write_blocked
        )


def _run(
    command: str,
    *,
    email: str = "",
    password: str = "",
    direction: Literal["upload", "download"] | None = None,
) -> None:
    try:
        code = asyncio.run(
            _execute(command, email=email, password=password, direction=direction)
        )
    except click.ClickException:
        raise
    except Exception:
        # Native errors may contain credentials; never print their raw message.
        raise click.ClickException(
            "AnkiWeb operation failed. Check the account, collection configuration, and whether another process has the collection open."
        ) from None
    if code:
        raise click.exceptions.Exit(code)


@anki.command()
@click.option(
    "--email",
    prompt="AnkiWeb email",
    help="Account already bound to this collection, if any.",
)
def login(email: str) -> None:
    """Log in and sync. The password prompt does not echo input."""
    password = click.prompt("AnkiWeb password", hide_input=True)
    _run("login", email=email, password=password)


@anki.command()
def logout() -> None:
    """Stop syncing and remove saved login credentials; retain cards."""
    _run("logout")


@anki.command()
def status() -> None:
    """Print local sync status as JSON without contacting AnkiWeb.

    Exit zero only when idle with no unresolved full sync or write block.
    """
    _run("status")


@anki.command()
@click.option(
    "--direction",
    type=click.Choice(["upload", "download"]),
    help="Resolve a required full sync: upload replaces AnkiWeb; download replaces AnkiNote. A collection backup is required first.",
)
def sync(direction: Literal["upload", "download"] | None) -> None:
    """Sync now, optionally resolving a full sync without prompting."""
    _run("sync", direction=direction)
