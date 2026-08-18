"""ankinote GUI — NiceGUI-powered interface for Anki card generation."""

from nicegui import ui

from ankinote.ui.pages.settings import settings_page
from ankinote.ui.pages.word import word_page


def _create_layout() -> None:
    """Create the shared layout elements (header, drawer, footer)."""
    # Header
    with ui.header(elevated=True).classes("items-center justify-between px-4"):
        ui.label("ankinote").classes("text-lg font-bold")
        with ui.row().classes("items-center gap-2"):
            # Anki connection status indicator
            status_badge = ui.badge(
                "Anki: ?", color="grey"
            ).props("outline").classes("text-xs")

    # Left drawer (navigation)
    with ui.left_drawer(value=True).classes("bg-gray-50 dark:bg-gray-900"):
        ui.label("Navigation").classes("text-sm font-semibold text-gray-500 px-4 pt-4 pb-2")

        with ui.column().classes("w-full gap-1 px-2"):
            ui.link("📝  Word Cards", "/").classes(
                "w-full px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700"
            )
            ui.link("⚙️  Settings", "/settings").classes(
                "w-full px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700"
            )

        # Dark mode toggle
        ui.separator().classes("my-4")
        ui.label("Appearance").classes("text-sm font-semibold text-gray-500 px-4 pb-2")
        dark = ui.dark_mode()
        ui.switch(
            "Dark mode",
            value=dark.value,
            on_change=lambda e: dark.set_value(e.value),
        ).classes("px-4")

    # Footer
    with ui.footer().classes("text-xs text-gray-400 justify-center"):
        ui.label("Powered by ankinote — AI-powered Anki card generator")


@ui.page("/")
def _word_page() -> None:
    """Word card generation page."""
    _create_layout()
    word_page()


@ui.page("/settings")
def _settings_page() -> None:
    """Settings page."""
    _create_layout()
    settings_page()


def start_gui() -> None:
    """Launch the ankinote GUI."""
    ui.run(
        title="ankinote",
        favicon="📝",
        storage_secret="ankinote-ui-session-key",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    start_gui()