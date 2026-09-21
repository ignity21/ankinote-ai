"""STEM card page — generate a STEM card via AI, preview, and push to Anki."""

import asyncio
from itertools import count
from typing import Literal, cast

from nicegui import events, ui

from ankinote.app import Application
from ankinote.collections.stem import CardType, StemCard, StemCollection
from ankinote.collections.stem.models import NOTE_FIELDS, FormulaModel
from ankinote.services.ai import (
    LiteLLMTextService,
    resolve_thinking,
)
from ankinote.services.anki import AnkiCollectionClient
from ankinote.services.anki_factory import create_anki_client, get_shared_runtime
from ankinote.ui.config import (
    CUSTOM_VENDOR,
    ProviderProfile,
    Settings,
    apply_env,
    get_image_provider_models,
    load_settings,
)
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.image_service import build_image_service
from ankinote.ui.pages.word import format_error
from ankinote.ui.sync import (
    retain_generated_save,
    save_allowed,
    saved_message,
    sync_feedback,
)

_THINKING_OPTIONS = {
    "default": "Default (thinking on)",
    "off": "Off",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


def _build_text_service(settings: Settings) -> LiteLLMTextService:
    """Assemble the text service from the active text provider profile."""
    profile = settings.text_providers.get(settings.active_text_provider) or (
        ProviderProfile()
    )
    return LiteLLMTextService(
        api_base=profile.base_url or None,
        api_key=profile.api_key or None,
        force_openai_route=profile.vendor == CUSTOM_VENDOR,
    )


def _edited_card(model: StemCard, fields: dict[str, str]) -> StemCard:
    """Validate all edited fields before a save can reach Anki."""
    values = model.model_dump()
    for name, value in fields.items():
        value = value.strip()
        if name.startswith("variable_"):
            continue
        if name == "tags":
            values[name] = [tag.strip() for tag in value.split(",") if tag.strip()]
        elif name == "steps":
            values[name] = [step.strip() for step in value.splitlines() if step.strip()]
        elif name == "image_description":
            values[name] = value or None
        else:
            values[name] = value
    if isinstance(model, FormulaModel):
        values["variables"] = [
            {
                "symbol": value.strip(),
                "description": fields[name.replace("_symbol", "_description")].strip(),
            }
            for name, value in fields.items()
            if name.startswith("variable_") and name.endswith("_symbol")
        ]
    return type(model).model_validate(values)


def stem_page() -> None:  # noqa: C901 - UI composition
    """Render the STEM card generation page."""

    settings = load_settings()
    set_locale(settings.ui_language)
    apply_env(settings)
    client = ui.context.client

    def _notify(
        message: str,
        notification_type: Literal["positive", "negative", "warning"],
    ) -> None:
        with client:
            ui.notify(message, type=notification_type)

    def _image_model_options(profile: ProviderProfile) -> list[str]:
        models = (
            []
            if profile.vendor == CUSTOM_VENDOR
            else get_image_provider_models(profile.vendor)
        )
        if profile.model and profile.model not in models:
            models = [profile.model, *models]
        return models

    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-4"):
        ui.label(t("stem.title")).classes("text-2xl font-bold")
        ui.label(t("stem.description")).classes("text-sm text-gray-500")

        topic_input = ui.input(
            label=t("stem.topic"),
            placeholder=t("stem.topic_placeholder"),
        ).classes("w-full")

        type_select = ui.select(
            label=t("stem.card_type"),
            options={
                "auto": t("stem.auto"),
                **{kind: kind.title() for kind in CardType},
            },
            value="auto",
        ).classes("w-full")

        reference_image: dict[str, bytes | str] = {}

        async def _on_reference_image_upload(e: events.UploadEventArguments) -> None:
            reference_image["bytes"] = await e.file.read()
            reference_image["mime"] = e.file.content_type or "image/png"
            _notify(t("stem.reference_attached", name=e.file.name), "positive")

        with ui.row().classes("w-full items-center gap-2"):
            ui.upload(
                label=t("stem.reference"),
                on_upload=_on_reference_image_upload,
                auto_upload=True,
                max_files=1,
            ).props("accept=image/*").classes("flex-1")
            ui.button(
                icon="close",
                on_click=lambda: reference_image.clear(),
            ).props("flat round dense").tooltip(t("stem.clear_reference"))
        ui.label(t("stem.reference_help")).classes("text-xs text-gray-500")

        thinking_select = ui.select(
            label=t("stem.thinking"),
            options=_THINKING_OPTIONS,
            value="default",
        ).classes("w-full")

        generate_image_switch = ui.switch(
            t("stem.generate_diagram"),
            value=settings.defaults.generate_image,
        )

        active_image_profile = (
            settings.image_providers.get(settings.active_image_provider)
            or ProviderProfile()
        )

        with (
            ui.row()
            .classes("w-full gap-4")
            .bind_visibility_from(generate_image_switch, "value")
        ):
            image_profile_select = ui.select(
                label=t("stem.image_provider"),
                options=list(settings.image_providers.keys()),
                value=settings.active_image_provider,
            ).classes("flex-1")
            image_model_select = ui.select(
                label=t("stem.image_model"),
                options=_image_model_options(active_image_profile),
                value=active_image_profile.model,
                with_input=True,
                new_value_mode="add-unique",
            ).classes("flex-1")

        def _on_image_profile_change() -> None:
            profile = (
                settings.image_providers.get(image_profile_select.value)
                or ProviderProfile()
            )
            models = _image_model_options(profile)
            current = image_model_select.value
            image_model_select.set_options(models)
            image_model_select.value = (
                current if current in models else (models[0] if models else current)
            )

        image_profile_select.on_value_change(lambda _: _on_image_profile_change())

        results_container = ui.column().classes("w-full gap-2")
        status_label = ui.label("").classes("text-sm text-gray-500")
        sync_feedback()

        generate_btn = (
            ui.button(
                t("stem.generate"),
                on_click=lambda: asyncio.ensure_future(_generate()),
                icon="auto_awesome",
            )
            .props("unevaluated")
            .classes("w-full")
        )

        def _collection(
            anki_client: AnkiCollectionClient,
            settings: Settings,
            *,
            with_image: bool,
            reasoning_effort: str | None,
            card_type: CardType | None = None,
        ) -> StemCollection:
            image_service = None
            if with_image:
                image_profile = (
                    settings.image_providers.get(image_profile_select.value)
                    or ProviderProfile()
                )
                image_service = build_image_service(
                    image_profile,
                    model=image_model_select.value or image_profile.model,
                    image_size=settings.image_size,
                )
            text_profile = (
                settings.text_providers.get(settings.active_text_provider)
                or ProviderProfile()
            )
            return StemCollection(
                anki_client,
                card_type=card_type,
                text_model=text_profile.model,
                text_service=_build_text_service(settings),
                image_service=image_service,
                reasoning_effort=reasoning_effort,
            )

        async def _save_edited(
            topic: str,
            model: StemCard,
            with_image: bool,
            reasoning_effort: str | None,
            fields: dict[str, ui.input | ui.textarea],
            save_btn: ui.button,
        ) -> None:
            try:
                edited = _edited_card(
                    model, {name: field.value or "" for name, field in fields.items()}
                )
            except ValueError as exc:
                _notify(f"Invalid card: {format_error(exc)}", "negative")
                return
            if not save_allowed():
                _notify(t("sync.write_blocked"), "warning")
                return
            save_btn.props("loading")
            save_btn.update()
            status_label.text = (
                "Generating diagram and saving…"
                if with_image and edited.image_description
                else "Saving card…"
            )
            image_error: Exception | None = None

            def _record_image_error(exc: Exception) -> None:
                nonlocal image_error
                image_error = exc

            try:
                settings = load_settings()
                apply_env(settings)
                async with Application():
                    anki = create_anki_client()
                    async with _collection(
                        anki,
                        settings,
                        with_image=with_image,
                        reasoning_effort=reasoning_effort,
                        card_type=model.card_type,
                    ) as collection:
                        await retain_generated_save(
                            lambda: collection.add_note(
                                edited,
                                topic=topic,
                                on_image_error=_record_image_error,
                            ),
                            results_container,
                        )
                results_container.clear()
                if image_error is None:
                    status_label.text = f"✓ {edited.front} — {saved_message()}"
                    _notify(
                        t("sync.card_saved")
                        if get_shared_runtime() is not None
                        else "Card saved to Anki",
                        "positive",
                    )
                else:
                    message = format_error(image_error)
                    status_label.text = (
                        f"✓ {edited.front} — saved; diagram failed: {message}"
                    )
                    _notify(f"Card saved, but diagram failed: {message}", "warning")
            except Exception as exc:
                message = format_error(exc)
                status_label.text = f"Error: {message}"
                _notify(f"Error: {message}", "negative")
            finally:
                # Saving a card clears the preview, which also deletes
                # its button. Do not update an element that no longer exists.
                if not save_btn.is_deleted:
                    save_btn.props(remove="loading")
                    save_btn.update()

        def _render_preview(
            topic: str,
            model: StemCard,
            with_image: bool,
            reasoning_effort: str | None,
        ) -> None:
            results_container.clear()
            with results_container, ui.card().classes("w-full p-4 gap-3"):
                ui.label(t("stem.review", card_type=model.card_type.title())).classes(
                    "text-sm font-semibold"
                )
                fields: dict[str, ui.input | ui.textarea] = {}
                values = model.model_dump(mode="json")
                names = [
                    name for name in NOTE_FIELDS[model.card_type] if name != "image"
                ]
                for name in [*names, "tags", "image_description"]:
                    value = values[name]
                    label = name.replace("_", " ").title()
                    if name == "tags":
                        label += " (comma-separated)"
                        value = ", ".join(model.tags)
                    elif name == "steps":
                        label += " (one step per line)"
                        value = "\n".join(value)
                    elif name == "variables":
                        ui.label(t("stem.variables")).classes("text-sm font-semibold")
                        variable_rows = ui.column().classes("w-full")
                        row_ids = count()

                        def add_variable(
                            symbol: str = "",
                            description: str = "",
                            *,
                            rows: ui.column = variable_rows,
                            ids: count = row_ids,
                        ) -> None:
                            index = next(ids)
                            symbol_key = f"variable_{index}_symbol"
                            description_key = f"variable_{index}_description"
                            with (
                                rows,
                                ui.row().classes("w-full items-center") as row,
                            ):
                                fields[symbol_key] = ui.input(
                                    label="Symbol", value=symbol
                                ).classes("w-28")
                                fields[description_key] = ui.input(
                                    label="Description", value=description
                                ).classes("flex-1")

                                def remove_variable() -> None:
                                    fields.pop(symbol_key)
                                    fields.pop(description_key)
                                    row.delete()

                                ui.button(icon="close", on_click=remove_variable).props(
                                    "flat round"
                                )

                        for variable in value:
                            add_variable(variable["symbol"], variable["description"])
                        ui.button(
                            "Add variable", on_click=lambda: add_variable()
                        ).props("flat")
                        continue
                    fields[name] = (
                        ui.textarea(label=label, value=value or "")
                        .classes("w-full")
                        .props("autogrow")
                    )
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button(
                        "Discard", icon="close", on_click=results_container.clear
                    ).props("flat")
                    save_btn: ui.button = ui.button(
                        "Save to Anki",
                        icon="save",
                        on_click=lambda: asyncio.ensure_future(
                            _save_edited(
                                topic,
                                model,
                                with_image,
                                reasoning_effort,
                                fields,
                                save_btn,
                            )
                        ),
                    )

        async def _generate() -> None:
            settings = load_settings()
            apply_env(settings)

            topic = (topic_input.value or "").strip()
            if not topic:
                _notify("Enter a topic", "warning")
                return

            with_image = bool(generate_image_switch.value)
            reasoning_effort = resolve_thinking(thinking_select.value, unset=None)

            generate_btn.props("loading")
            generate_btn.update()
            results_container.clear()
            status_label.text = "Generating card content…"

            try:
                async with Application():
                    anki = create_anki_client()
                    async with _collection(
                        anki,
                        settings,
                        with_image=with_image,
                        reasoning_effort=reasoning_effort,
                        card_type=None
                        if type_select.value == "auto"
                        else CardType(type_select.value),
                    ) as collection:
                        model = await collection.generate_model(
                            topic,
                            reference_image=cast(
                                bytes | None, reference_image.get("bytes")
                            ),
                            reference_image_mime=cast(
                                str, reference_image.get("mime", "image/png")
                            ),
                        )
                        status_label.text = ""
                        _render_preview(topic, model, with_image, reasoning_effort)
            except Exception as exc:
                message = format_error(exc)
                status_label.text = f"Error: {message}"
                _notify(f"Error: {message}", "negative")
            finally:
                generate_btn.props(remove="loading")
                generate_btn.update()
