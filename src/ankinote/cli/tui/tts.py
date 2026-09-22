"""Google Cloud TTS API key entry."""

import questionary

from ankinote.settings import Settings, save_settings


def run_tts_menu(settings: Settings) -> None:
    """Prompt for and persist the Google Cloud TTS API key."""
    current = settings.api_keys.get("GOOGLE_TTS_KEY", "")
    key = questionary.password("Google Cloud TTS API key", default=current).ask()
    if key is None:
        return
    settings.api_keys["GOOGLE_TTS_KEY"] = key
    save_settings(settings)
