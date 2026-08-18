"""Word card page — generate vocabulary cards via AI and push to Anki."""

import asyncio
import re

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.word import WordCollection
from ankinote.consts import Language
from ankinote.services.ai import LiteLLMTextService, LiteLLMGeminiImageService
from ankinote.services.anki import AnkiConnectClient
from ankinote.ui.config import CUSTOM_API_KEY_STORAGE_KEY, CUSTOM_PROVIDER, apply_env, load_settings


_ERROR_MESSAGE_RE = re.compile(r'"message"\s*:\s*"([^"]+)"')


def _format_error(exc: Exception) -> str:
    """Collapse a (possibly multi-line, JSON-y) exception into one readable line."""
    text = str(exc)
    match = _ERROR_MESSAGE_RE.search(text)
    if match:
        return match.group(1)
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= 200 else collapsed[:200] + "…"


def word_page() -> None:
    """Render the word card generation page."""

    settings = load_settings()
    apply_env(settings)

    language_options = [lang.value for lang in Language]

    # -- Form ----------------------------------------------------------------
    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-4"):
        ui.label("Word Cards").classes("text-2xl font-bold")

        word_input = ui.input(
            label="Word",
            placeholder="Enter a single word (e.g. apple)",
        ).classes("w-full")

        batch_textarea = ui.textarea(
            label="Batch Words (optional)",
            placeholder="One word per line:\napple\nbanana\ncherry",
        ).classes("w-full")
        batch_textarea.props("autogrow")

        with ui.row().classes("w-full gap-4"):
            native_select = ui.select(
                label="Native Language",
                options=language_options,
                value=settings.defaults.native_language,
            ).classes("flex-1")

            target_select = ui.select(
                label="Target Language",
                options=language_options,
                value=settings.defaults.target_language,
            ).classes("flex-1")

        generate_image_switch = ui.switch(
            "Generate images",
            value=settings.defaults.generate_image,
        )

        # -- Results area ----------------------------------------------------
        results_container = ui.column().classes("w-full gap-2")
        status_label = ui.label("").classes("text-sm text-gray-500")

        # -- Generate button -------------------------------------------------
        generate_btn = ui.button(
            "Generate",
            on_click=lambda: asyncio.ensure_future(_generate()),
            icon="auto_awesome",
        ).props("unevaluated").classes("w-full")

        async def _generate():
            # Re-read from disk so a Settings change made after this page
            # loaded (e.g. in another tab) is picked up on every click.
            settings = load_settings()
            apply_env(settings)

            single = (word_input.value or "").strip()
            batch_text = (batch_textarea.value or "").strip()
            words: list[str] = []
            if single:
                words.append(single)
            if batch_text:
                words.extend(
                    w.strip() for w in batch_text.splitlines() if w.strip()
                )
            if not words:
                ui.notify("Enter at least one word", type="warning")
                return

            native = native_select.value
            target = target_select.value
            generate_image = generate_image_switch.value

            generate_btn.props("loading")
            generate_btn.update()
            status_label.text = ""
            results_container.clear()

            # Build card placeholders
            placeholders: list[tuple[ui.card, ui.label]] = []
            with results_container:
                for word in words:
                    card = ui.card().classes("w-full p-2 text-sm")
                    with card:
                        lbl = ui.label(f"⏳ {word} — generating...")
                    placeholders.append((card, lbl))

            image_service = None
            if generate_image:
                image_service = LiteLLMGeminiImageService(
                    model_id=settings.image_model,
                    image_size=settings.image_size,
                    api_key=settings.api_keys.get("GEMINI_API_KEY") or None,
                )

            if settings.provider == CUSTOM_PROVIDER:
                text_service = LiteLLMTextService(
                    api_base=settings.custom_base_url or None,
                    api_key=settings.api_keys.get(CUSTOM_API_KEY_STORAGE_KEY) or None,
                )
            else:
                text_service = LiteLLMTextService()

            success_count = 0
            fail_count = 0

            try:
                async with Application():
                    client = AnkiConnectClient()
                    async with WordCollection(
                        client,
                        native_language=Language(native),
                        target_language=Language(target),
                        text_model_id=settings.text_model,
                        text_service=text_service,
                        image_service=image_service,
                    ) as collection:
                        for (card, lbl), word in zip(placeholders, words):
                            try:
                                await collection.generate_and_add_note(word)
                                lbl.set_text(f"✓ {word} — added to Anki")
                                lbl.classes(
                                    "text-green-700 dark:text-green-400"
                                )
                                card.classes(
                                    add="bg-green-50 dark:bg-green-900/20"
                                )
                                success_count += 1
                            except Exception as exc:
                                lbl.set_text(f"✗ {word} — {_format_error(exc)}")
                                lbl.classes(
                                    "text-red-700 dark:text-red-400"
                                )
                                card.classes(
                                    add="bg-red-50 dark:bg-red-900/20"
                                )
                                fail_count += 1

                    total = len(words)
                    if fail_count == 0:
                        status_label.text = (
                            f"✅ All {total} word(s) generated successfully!"
                        )
                        ui.notify("All done!", type="positive")
                    else:
                        status_label.text = (
                            f"✅ {success_count}/{total} succeeded, "
                            f"❌ {fail_count} failed"
                        )

            except Exception as exc:
                message = _format_error(exc)
                ui.notify(f"Error: {message}", type="negative")
                status_label.text = f"Error: {message}"
            finally:
                generate_btn.props(remove="loading")
                generate_btn.update()