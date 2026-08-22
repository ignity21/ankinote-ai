"""Phrase and idiom card page — generate expression cards and push to Anki."""

import asyncio
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.phrase import PhraseCollection
from ankinote.consts import Language
from ankinote.services.ai import LiteLLMTextService
from ankinote.services.anki import AnkiConnectClient
from ankinote.ui.config import (
    CUSTOM_API_KEY_STORAGE_KEY,
    CUSTOM_PROVIDER,
    CustomProvider,
    apply_env,
    load_settings,
)
from ankinote.ui.pages.word import format_error


def phrase_page() -> None:
    """Render the phrase and idiom card generation page."""

    settings = load_settings()
    apply_env(settings)
    client = ui.context.client

    def _notify(
        message: str,
        notification_type: Literal["positive", "negative", "warning"],
    ) -> None:
        """Send a notification from the generation background task."""
        with client:
            ui.notify(message, type=notification_type)

    language_options = [lang.value for lang in Language]

    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-4"):
        with ui.row().classes("items-center gap-2"):
            ui.badge("Expression", color="indigo").props("outline")
            ui.label("Phrase & Idiom Cards").classes("text-2xl font-bold")
        ui.label(
            "Capture reusable expressions and idioms with meanings, examples, and audio."
        ).classes("text-sm text-gray-500 -mt-3")

        phrase_input = ui.input(
            label="Phrase or idiom",
            placeholder="Enter one expression (e.g. look forward to)",
        ).classes("w-full")

        batch_textarea = ui.textarea(
            label="Batch phrases and idioms (optional)",
            placeholder="One expression per line:\nlook forward to\nonce in a blue moon",
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

        parallelism_select = ui.select(
            label="Parallel expressions",
            options={
                1: "1 at a time",
                2: "2 at a time",
                3: "3 at a time",
                5: "5 at a time",
            },
            value=1,
        ).classes("w-full")
        ui.label(
            "Higher values finish batches sooner but use more provider capacity."
        ).classes("text-xs text-gray-500 -mt-3")

        results_container = ui.column().classes("w-full gap-2")
        status_label = ui.label("").classes("text-sm text-gray-500")

        generate_btn = (
            ui.button(
                "Generate expression cards",
                on_click=lambda: asyncio.ensure_future(_generate()),
                icon="auto_awesome",
            )
            .props("unevaluated")
            .classes("w-full")
        )

        async def _generate() -> None:
            settings = load_settings()
            apply_env(settings)

            single = (phrase_input.value or "").strip()
            batch_text = (batch_textarea.value or "").strip()
            expressions: list[str] = []
            if single:
                expressions.append(single)
            if batch_text:
                expressions.extend(
                    expression.strip()
                    for expression in batch_text.splitlines()
                    if expression.strip()
                )
            if not expressions:
                _notify("Enter at least one phrase or idiom", "warning")
                return

            native = native_select.value
            target = target_select.value
            parallelism = int(parallelism_select.value or 1)

            generate_btn.props("loading")
            generate_btn.update()
            status_label.text = ""
            results_container.clear()

            placeholders: list[tuple[ui.card, ui.label]] = []
            with results_container:
                for expression in expressions:
                    card = ui.card().classes("w-full p-2 text-sm")
                    with card:
                        label = ui.label(f"⏳ {expression} — generating...")
                    placeholders.append((card, label))

            status_label.text = (
                f"Generating {len(expressions)} expression(s), "
                f"up to {parallelism} at a time…"
            )

            custom_profile = settings.custom_providers.get(settings.provider)
            if settings.provider == CUSTOM_PROVIDER and custom_profile is None:
                custom_profile = CustomProvider(
                    base_url=settings.custom_base_url,
                    model=settings.text_model,
                    api_key=settings.api_keys.get(CUSTOM_API_KEY_STORAGE_KEY, ""),
                )
            if custom_profile is not None:
                text_service = LiteLLMTextService(
                    api_base=custom_profile.base_url or None,
                    api_key=custom_profile.api_key or None,
                )
            else:
                text_service = LiteLLMTextService()

            success_count = 0
            fail_count = 0

            try:
                async with Application():
                    anki_client = AnkiConnectClient()
                    async with PhraseCollection(
                        anki_client,
                        native_language=Language(native),
                        target_language=Language(target),
                        text_model_id=settings.text_model,
                        text_service=text_service,
                    ) as collection:
                        semaphore = asyncio.Semaphore(parallelism)

                        async def _generate_one(
                            index: int, expression: str
                        ) -> tuple[int, Exception | None]:
                            async with semaphore:
                                try:
                                    await collection.generate_and_add_note(expression)
                                except Exception as exc:
                                    return index, exc
                            return index, None

                        tasks = [
                            asyncio.create_task(_generate_one(index, expression))
                            for index, expression in enumerate(expressions)
                        ]
                        for task in asyncio.as_completed(tasks):
                            index, error = await task
                            card, label = placeholders[index]
                            expression = expressions[index]
                            if error is None:
                                label.set_text(f"✓ {expression} — added to Anki")
                                label.classes("text-green-700 dark:text-green-400")
                                card.classes(add="bg-green-50 dark:bg-green-900/20")
                                success_count += 1
                            else:
                                label.set_text(
                                    f"✗ {expression} — {format_error(error)}"
                                )
                                label.classes("text-red-700 dark:text-red-400")
                                card.classes(add="bg-red-50 dark:bg-red-900/20")
                                fail_count += 1

                    total = len(expressions)
                    if fail_count == 0:
                        status_label.text = (
                            f"✅ All {total} expression(s) generated successfully!"
                        )
                        _notify("All done!", "positive")
                    else:
                        status_label.text = (
                            f"✅ {success_count}/{total} succeeded, "
                            f"❌ {fail_count} failed"
                        )

            except Exception as exc:
                message = format_error(exc)
                _notify(f"Error: {message}", "negative")
                status_label.text = f"Error: {message}"
            finally:
                generate_btn.props(remove="loading")
                generate_btn.update()
