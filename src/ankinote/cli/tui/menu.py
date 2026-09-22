"""Top-level interactive menu for the bare ``ankinote`` invocation."""

import questionary

from ankinote.settings import Settings

from .anki_backend import run_anki_backend_menu
from .image_profiles import run_image_profiles_menu
from .text_profiles import run_text_profiles_menu
from .tts import run_tts_menu

_ENTRIES = (
    ("Text provider profiles", run_text_profiles_menu),
    ("Image provider profiles", run_image_profiles_menu),
    ("Anki backend", run_anki_backend_menu),
    ("Google TTS key", run_tts_menu),
)


def run_menu(settings: Settings) -> None:
    """Loop the top-level menu until the user exits (Ctrl+C or "Exit")."""
    while True:
        selection = questionary.select(
            "AnkiNote settings — pick a section (Ctrl+C to exit)",
            choices=[*(label for label, _ in _ENTRIES), "Exit"],
        ).ask()
        if selection is None or selection == "Exit":
            return
        for label, handler in _ENTRIES:
            if label == selection:
                handler(settings)
                break
