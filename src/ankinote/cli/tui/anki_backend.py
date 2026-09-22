"""Anki backend selector — AnkiConnect vs. a local collection file."""

import questionary

from ankinote.services.anki_factory import COLLECTION_BACKEND, CONNECT_BACKEND
from ankinote.settings import Settings, default_collection_path, save_settings


def run_anki_backend_menu(settings: Settings) -> None:
    """Prompt for the Anki backend and, for ``collection``, its file path."""
    current = settings.anki_backend or CONNECT_BACKEND
    backend = questionary.select(
        "Anki backend",
        choices=[
            questionary.Choice(
                "AnkiConnect (talk to a running Anki desktop app)",
                value=CONNECT_BACKEND,
            ),
            questionary.Choice(
                "Local collection file (no Anki desktop app needed)",
                value=COLLECTION_BACKEND,
            ),
        ],
        default=current,
    ).ask()
    if backend is None:
        return
    settings.anki_backend = backend
    if backend == COLLECTION_BACKEND:
        path = questionary.text(
            "Collection path",
            default=settings.anki_collection_path or default_collection_path(),
        ).ask()
        if path is None:
            return
        settings.anki_collection_path = path.strip()
    save_settings(settings)
