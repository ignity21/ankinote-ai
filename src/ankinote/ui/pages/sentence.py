"""Sentence card page — generate production cards and push to Anki."""

import asyncio
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.sentence import SentenceCollection
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


def sentence_page() -> None:
    """Render the sentence production-card generation page."""

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
            ui.badge("Production", color="teal").props("outline")
            ui.label("Sentence Cards").classes("text-2xl font-bold")
        ui.label(
            "Add a target-language sentence; AI creates a native-language prompt, notes, and phrase breakdown."
        ).classes("text-sm text-gray-500 -mt-3")

        sentence_input = ui.input(
            label="Target-language sentence",
            placeholder="Enter one sentence (e.g. I overslept this morning.)",
        ).classes("w-full")

        batch_textarea = ui.textarea(
            label="Batch target-language sentences (optional)",
            placeholder="One target-language sentence per line:\nI overslept this morning.\nI need to leave earlier tomorrow.",
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
            label="Parallel sentences",
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
                "Generate sentence cards",
                on_click=lambda: asyncio.ensure_future(_generate()),
                icon="auto_awesome",
            )
            .props("unevaluated")
            .classes("w-full")
        )

        async def _generate() -> None:
            settings = load_settings()
            apply_env(settings)

            single = (sentence_input.value or "").strip()
            batch_text = (batch_textarea.value or "").strip()
            sentences: list[str] = []
            if single:
                sentences.append(single)
            if batch_text:
                sentences.extend(
                    sentence.strip()
                    for sentence in batch_text.splitlines()
                    if sentence.strip()
                )
            if not sentences:
                _notify("Enter at least one target-language sentence", "warning")
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
                for sentence in sentences:
                    card = ui.card().classes("w-full p-2 text-sm")
                    with card:
                        label = ui.label(f"⏳ {sentence} — generating...")
                    placeholders.append((card, label))

            status_label.text = (
                f"Generating {len(sentences)} sentence(s), "
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
                    async with SentenceCollection(
                        anki_client,
                        native_language=Language(native),
                        target_language=Language(target),
                        text_model_id=settings.text_model,
                        text_service=text_service,
                    ) as collection:
                        semaphore = asyncio.Semaphore(parallelism)

                        async def _generate_one(
                            index: int, sentence: str
                        ) -> tuple[int, Exception | None]:
                            async with semaphore:
                                try:
                                    await collection.generate_and_add_note(sentence)
                                except Exception as exc:
                                    return index, exc
                            return index, None

                        tasks = [
                            asyncio.create_task(_generate_one(index, sentence))
                            for index, sentence in enumerate(sentences)
                        ]
                        for task in asyncio.as_completed(tasks):
                            index, error = await task
                            card, label = placeholders[index]
                            sentence = sentences[index]
                            if error is None:
                                label.set_text(f"✓ {sentence} — added to Anki")
                                label.classes("text-green-700 dark:text-green-400")
                                card.classes(add="bg-green-50 dark:bg-green-900/20")
                                success_count += 1
                            else:
                                label.set_text(f"✗ {sentence} — {format_error(error)}")
                                label.classes("text-red-700 dark:text-red-400")
                                card.classes(add="bg-red-50 dark:bg-red-900/20")
                                fail_count += 1

                    total = len(sentences)
                    if fail_count == 0:
                        status_label.text = (
                            f"✅ All {total} sentence(s) generated successfully!"
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
