"""Word card page — generate vocabulary cards via AI and push to Anki."""

import asyncio
import re
from typing import Literal

from nicegui import ui

from ankinote.app import Application
from ankinote.collections.word import WordCollection
from ankinote.consts import TARGET_LANGUAGES, Language
from ankinote.services.ai import LiteLLMTextService
from ankinote.services.anki_factory import create_anki_client
from ankinote.ui.config import (
    CUSTOM_VENDOR,
    ProviderProfile,
    apply_env,
    load_settings,
)
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.image_service import build_image_service
from ankinote.ui.sync import (
    retain_generated_save,
    save_allowed,
    saved_message,
    sync_feedback,
)

_ERROR_MESSAGE_RE = re.compile(r'"message"\s*:\s*"([^"]+)"')


def format_error(exc: Exception) -> str:
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

    # -- Form ----------------------------------------------------------------
    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-4"):
        ui.label(t("word.title")).classes("text-2xl font-bold")

        word_input = ui.input(
            label=t("word.word"),
            placeholder=t("word.word_placeholder"),
        ).classes("w-full")

        batch_textarea = ui.textarea(
            label=t("word.batch"),
            placeholder=t("word.batch_placeholder"),
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

        generate_image_switch = ui.switch(
            t("settings.images_default"),
            value=settings.defaults.generate_image,
        )

        parallelism_select = ui.select(
            label=t("word.parallel"),
            options={
                1: "1 at a time",
                2: "2 at a time",
                3: "3 at a time",
                5: "5 at a time",
            },
            value=1,
        ).classes("w-full")
        ui.label(t("common.higher_parallelism")).classes("text-xs text-gray-500 -mt-3")

        # -- Results area ----------------------------------------------------
        results_container = ui.column().classes("w-full gap-2")
        status_label = ui.label("").classes("text-sm text-gray-500")
        sync_feedback()

        # -- Generate button -------------------------------------------------
        generate_btn = (
            ui.button(
                t("word.generate"),
                on_click=lambda: asyncio.ensure_future(_generate()),
                icon="auto_awesome",
            )
            .props("unevaluated")
            .classes("w-full")
        )

        async def _generate():
            # Re-read from disk so a Settings change made after this page
            # loaded (e.g. in another tab) is picked up on every click.
            if not save_allowed():
                _notify(t("sync.write_blocked"), "warning")
                return
            settings = load_settings()
            apply_env(settings)

            single = (word_input.value or "").strip()
            batch_text = (batch_textarea.value or "").strip()
            words: list[str] = []
            if single:
                words.append(single)
            if batch_text:
                words.extend(w.strip() for w in batch_text.splitlines() if w.strip())
            if not words:
                _notify(t("word.enter"), "warning")
                return

            native = native_select.value
            target = target_select.value
            generate_image = generate_image_switch.value
            parallelism = int(parallelism_select.value or 1)

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
                        lbl = ui.label(f"⏳ {word} — {t('common.generating')}")
                    placeholders.append((card, lbl))

            status_label.text = t(
                "word.generating", count=len(words), parallelism=parallelism
            )

            image_service = None
            if generate_image:
                image_profile = (
                    settings.image_providers.get(settings.active_image_provider)
                    or ProviderProfile()
                )
                image_service = build_image_service(
                    image_profile,
                    image_size=settings.image_size,
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
                    client = create_anki_client()
                    async with WordCollection(
                        client,
                        native_language=Language(native),
                        target_language=Language(target),
                        text_model=text_profile.model,
                        text_service=text_service,
                        image_service=image_service,
                    ) as collection:
                        semaphore = asyncio.Semaphore(parallelism)

                        async def _generate_one(
                            index: int, word: str
                        ) -> tuple[int, Exception | None]:
                            async with semaphore:
                                try:
                                    await retain_generated_save(
                                        lambda: collection.generate_and_add_note(word),
                                        placeholders[index][0],
                                    )
                                except Exception as exc:
                                    return index, exc
                            return index, None

                        tasks = [
                            asyncio.create_task(_generate_one(index, word))
                            for index, word in enumerate(words)
                        ]
                        for task in asyncio.as_completed(tasks):
                            index, error = await task
                            card, lbl = placeholders[index]
                            word = words[index]
                            if error is None:
                                lbl.set_text(f"✓ {word} — {saved_message()}")
                                lbl.classes("text-green-700 dark:text-green-400")
                                card.classes(add="bg-green-50 dark:bg-green-900/20")
                                success_count += 1
                            else:
                                lbl.set_text(f"✗ {word} — {format_error(error)}")
                                lbl.classes("text-red-700 dark:text-red-400")
                                card.classes(add="bg-red-50 dark:bg-red-900/20")
                                fail_count += 1

                    total = len(words)
                    if fail_count == 0:
                        status_label.text = t("word.success", total=total)
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
