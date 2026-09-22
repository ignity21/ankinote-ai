"""Sentence card page — generate production cards and push to Anki."""

import asyncio
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.sentence import SentenceCollection
from ankinote.consts import TARGET_LANGUAGES, Language
from ankinote.services.ai import LiteLLMTextService
from ankinote.services.anki_factory import create_anki_client
from ankinote.settings import (
    CUSTOM_VENDOR,
    ProviderProfile,
    apply_env,
    load_settings,
)
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.pages.word import format_error
from ankinote.ui.sync import (
    retain_generated_save,
    save_allowed,
    saved_message,
    sync_feedback,
)


def sentence_page() -> None:  # noqa: C901 - UI composition
    """Render the sentence production-card generation page."""

    settings = load_settings()
    set_locale(settings.ui_language)
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
    target_language_options = [lang.value for lang in TARGET_LANGUAGES]

    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-4"):
        with ui.row().classes("items-center gap-2"):
            ui.badge(t("sentence.production"), color="teal").props("outline")
            ui.label(t("sentence.title")).classes("text-2xl font-bold")
        ui.label(t("sentence.description")).classes("text-sm text-gray-500 -mt-3")

        sentence_input = ui.input(
            label=t("sentence.input"),
            placeholder=t("sentence.input_placeholder"),
        ).classes("w-full")

        batch_textarea = ui.textarea(
            label=t("sentence.batch"),
            placeholder=t("sentence.batch_placeholder"),
        ).classes("w-full")
        batch_textarea.props("autogrow")

        with ui.row().classes("w-full gap-4"):
            native_select = ui.select(
                label=t("settings.native"),
                options=language_options,
                value=settings.defaults.native_language,
            ).classes("flex-1")

            target_select = ui.select(
                label=t("settings.target"),
                options=target_language_options,
                value=settings.defaults.target_language,
            ).classes("flex-1")

        parallelism_select = ui.select(
            label=t("sentence.parallel"),
            options={
                1: "1 at a time",
                2: "2 at a time",
                3: "3 at a time",
                5: "5 at a time",
            },
            value=1,
        ).classes("w-full")
        ui.label(t("common.higher_parallelism")).classes("text-xs text-gray-500 -mt-3")

        results_container = ui.column().classes("w-full gap-2")
        status_label = ui.label("").classes("text-sm text-gray-500")
        sync_feedback()

        generate_btn = (
            ui.button(
                t("sentence.generate"),
                on_click=lambda: asyncio.ensure_future(_generate()),
                icon="auto_awesome",
            )
            .props("unevaluated")
            .classes("w-full")
        )

        async def _generate() -> None:  # noqa: C901 - UI workflow
            if not save_allowed():
                _notify(t("sync.write_blocked"), "warning")
                return
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
                _notify(t("sentence.enter"), "warning")
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
                        label = ui.label(f"⏳ {sentence} — {t('common.generating')}")
                    placeholders.append((card, label))

            status_label.text = t(
                "sentence.generating", count=len(sentences), parallelism=parallelism
            )

            text_profile = (
                settings.text_providers.get(settings.active_text_provider)
                or ProviderProfile()
            )
            text_service = LiteLLMTextService(
                api_base=text_profile.base_url or None,
                api_key=text_profile.api_key or None,
                force_openai_route=text_profile.vendor == CUSTOM_VENDOR,
            )

            success_count = 0
            fail_count = 0

            try:
                async with Application():
                    anki_client = create_anki_client()
                    async with SentenceCollection(
                        anki_client,
                        native_language=Language(native),
                        target_language=Language(target),
                        text_model=text_profile.model,
                        text_service=text_service,
                    ) as collection:
                        semaphore = asyncio.Semaphore(parallelism)

                        async def _generate_one(
                            index: int, sentence: str
                        ) -> tuple[int, Exception | None]:
                            async with semaphore:
                                try:
                                    await retain_generated_save(
                                        lambda: collection.generate_and_add_note(
                                            sentence
                                        ),
                                        placeholders[index][0],
                                    )
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
                                label.set_text(f"✓ {sentence} — {saved_message()}")
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
                        status_label.text = t("sentence.success", total=total)
                        _notify(t("common.all_done"), "positive")
                    else:
                        status_label.text = t(
                            "sync.batch_result", saved=success_count, failed=fail_count
                        )

            except Exception as exc:
                message = format_error(exc)
                _notify(t("common.error", message=message), "negative")
                status_label.text = t("common.error", message=message)
            finally:
                generate_btn.props(remove="loading")
                generate_btn.update()
