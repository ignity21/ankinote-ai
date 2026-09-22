"""Lazily-loaded interactive TUI for the bare ``ankinote`` invocation.

Only imported when ``ankinote`` runs with no subcommand — scripted usage
(``word add``, ``anki sync``, ...) never touches ``questionary``.
"""

import sys

import click

from ankinote.settings import load_settings


def run_tui() -> None:
    """Open the interactive settings menu, or bail out cleanly if not a TTY."""
    if not sys.stdin.isatty():
        click.echo("No subcommand given and not running interactively; see --help.")
        return

    from .menu import run_menu

    run_menu(load_settings())
