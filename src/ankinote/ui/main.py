"""ankinote GUI — NiceGUI-powered interface for Anki card generation."""

import os
from pathlib import Path

from loguru import logger
from nicegui import app, ui

from ankinote.services.anki_factory import (
    AnkiBackendConfigError,
    start_anki_backend,
    stop_anki_backend,
)
from ankinote.services.collection_runtime import CollectionRuntimeError
from ankinote.ui.config import load_settings, save_settings
from ankinote.ui.i18n import SUPPORTED_LOCALES, set_locale, t
from ankinote.ui.pages.notetypes import notetypes_page
from ankinote.ui.pages.phrase import phrase_page
from ankinote.ui.pages.sentence import sentence_page
from ankinote.ui.pages.settings import settings_page
from ankinote.ui.pages.stem import stem_page
from ankinote.ui.pages.word import word_page

# Colors are tokenised so the header, drawer and content surfaces stay in sync
# across themes. The content area and drawer share one surface; the header is the
# only chrome that carries colour, and it is a distinct (not merely re-tinted)
# tone in dark mode.
_PRIMARY = "#3d6fa6"
_PRIMARY_DARK = "#6fa8dc"
_SURFACE_DARK = "#242833"
_PAGE_DARK = "#16181d"

_STATIC_DIR = Path(__file__).parent / "static"
app.add_static_files("/static", _STATIC_DIR)

_THEME_CSS = f"""
<style>
  /* Content + drawer are one white surface; also stops the header colour
     bleeding into the page on browsers that leave .q-page transparent. */
  .q-layout, .q-page-container, .q-page, .nicegui-content {{ background: #fff; }}
  .q-drawer {{ background: #fff; border-right: 1px solid #e8eaed; }}
  .q-header {{ background: {_PRIMARY}; }}

  .body--dark .q-layout,
  .body--dark .q-page-container,
  .body--dark .q-page,
  .body--dark .nicegui-content {{ background: {_PAGE_DARK}; }}
  .body--dark .q-drawer {{ background: #1c1f26; border-right-color: #2a2e38; }}
  .body--dark .q-header {{ background: #222834; }}
  .body--dark .q-card {{ background: {_SURFACE_DARK}; }}
  /* Lift the accent so it stays legible on the dark surface. */
  .body--dark .text-primary {{ color: {_PRIMARY_DARK}; }}
</style>
"""

ui.add_head_html(_THEME_CSS, shared=True)


def _create_layout() -> None:
    """Create the shared layout elements (header, drawer, footer)."""
    settings = load_settings()
    set_locale(settings.ui_language)
    ui.colors(
        primary=_PRIMARY,
        dark=_SURFACE_DARK,
        dark_page=_PAGE_DARK,
    )
    # Header
    with ui.header(elevated=True).classes(
        "items-center justify-between px-4 h-14 text-white"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.image("/static/ankinote-logo-micro.svg").classes("w-7 h-7")
            ui.label("AnkiNote").classes("text-lg font-bold text-white")

        with ui.row().classes("items-center gap-1"):

            def _change_language(locale: str) -> None:
                settings.ui_language = locale
                save_settings(settings)
                ui.run_javascript("window.location.reload()")

            dark = ui.dark_mode()
            dark_switch = ui.switch(
                value=dark.value,
                on_change=lambda event: dark.set_value(event.value),
            ).props("dense checked-icon=dark_mode unchecked-icon=light_mode")
            dark_switch.classes("text-white")
            with dark_switch:
                ui.tooltip(t("nav.dark_mode"))

            with (
                ui.button(icon="translate")
                .props("flat round dense")
                .classes("text-white")
            ):
                ui.tooltip(t("nav.language"))
                with (
                    ui.menu()
                    .props('anchor="bottom right" self="top right"')
                    .style("width: 10rem")
                ):
                    for locale, label in SUPPORTED_LOCALES.items():
                        ui.item(
                            label,
                            on_click=lambda locale=locale: _change_language(locale),
                        ).props(
                            f"dense {'active' if locale == settings.ui_language else ''}"
                        )

    # Left drawer (navigation)
    _nav_link_classes = (
        "w-full px-3 py-2 rounded text-base no-underline text-gray-700 "
        "dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-gray-700/40"
    )
    with ui.left_drawer(value=True).props("width=270"):
        ui.label(t("nav.navigation")).classes(
            "text-sm font-semibold text-gray-500 dark:text-slate-300 px-4 pt-4 pb-2"
        )

        with ui.column().classes("w-full gap-1 px-2"):
            ui.link(t("nav.word_cards"), "/").classes(_nav_link_classes)
            ui.link(t("nav.phrase_cards"), "/phrases").classes(_nav_link_classes)
            ui.link(t("nav.sentence_cards"), "/sentences").classes(_nav_link_classes)
            ui.link(t("nav.stem_cards"), "/stem").classes(_nav_link_classes)
            ui.link(t("nav.card_types"), "/notetypes").classes(_nav_link_classes)
            ui.link(t("nav.settings"), "/settings").classes(_nav_link_classes)


@ui.page("/")
def _word_page() -> None:
    """Word card generation page."""
    _create_layout()
    word_page()


@ui.page("/phrases")
def _phrase_page() -> None:
    """Phrase and idiom card generation page."""
    _create_layout()
    phrase_page()


@ui.page("/sentences")
def _sentence_page() -> None:
    """Sentence card generation page."""
    _create_layout()
    sentence_page()


@ui.page("/stem")
def _stem_page() -> None:
    """STEM card generation page."""
    _create_layout()
    stem_page()


@ui.page("/notetypes")
def _notetypes_page() -> None:
    """Card Types (note type + deck setup) page."""
    _create_layout()
    notetypes_page()


@ui.page("/settings")
def _settings_page() -> None:
    """Settings page."""
    _create_layout()
    settings_page()


@app.on_startup
async def _open_anki_backend() -> None:
    """Open the shared collection runtime once for the whole web app."""
    try:
        await start_anki_backend()
    except (CollectionRuntimeError, AnkiBackendConfigError, OSError) as exc:
        # A misconfigured collection path or a stale lock is an operator
        # problem, not a bug — log it plainly instead of a NiceGUI traceback.
        logger.error("Anki backend failed to start: {}", exc)


@app.on_shutdown
async def _close_anki_backend() -> None:
    """Close the shared collection runtime on web app shutdown."""
    await stop_anki_backend()


def start_gui() -> None:
    """Launch the ankinote GUI."""
    ui.run(
        title="AnkiNote",
        favicon=_STATIC_DIR / "ankinote-logo-micro.svg",
        host=os.getenv("ANKINOTE_HOST", "0.0.0.0"),
        port=int(os.getenv("ANKINOTE_PORT", "8080")),
        storage_secret=os.getenv("ANKINOTE_STORAGE_SECRET", "ankinote-ui-session-key"),
        show=os.getenv("ANKINOTE_SHOW", "true").lower() != "false",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    start_gui()
