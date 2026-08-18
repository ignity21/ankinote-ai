"""Settings page — LLM provider, TTS, and default language preferences."""

from nicegui import ui

from ankinote.consts import Language
from ankinote.ui.config import (
    CUSTOM_API_KEY_STORAGE_KEY,
    CUSTOM_PROVIDER,
    DEFAULT_IMAGE_MODELS,
    PROVIDERS,
    DefaultsConfig,
    Settings,
    apply_env,
    get_provider_models,
    save_settings,
)


def settings_page() -> None:
    """Render the settings page."""

    settings = ui.context.client.storage.get("settings")
    if settings is None:
        from ankinote.ui.config import load_settings
        settings = load_settings()

    is_custom = settings.provider == CUSTOM_PROVIDER
    current_env_key = (
        CUSTOM_API_KEY_STORAGE_KEY if is_custom else PROVIDERS[settings.provider]["env_key"]
    )

    with ui.column().classes("w-full max-w-2xl mx-auto p-6 gap-6"):
        ui.label("Settings").classes("text-2xl font-bold")

        # -- LLM Provider -----------------------------------------------------------
        _section("LLM Provider")

        provider_select = ui.select(
            label="Provider",
            options=[*PROVIDERS.keys(), CUSTOM_PROVIDER],
            value=settings.provider,
        ).classes("w-full")

        model_select = ui.select(
            label="Model",
            options=get_provider_models(settings.provider) if not is_custom else [],
            value=settings.text_model if not is_custom else None,
        ).classes("w-full").bind_visibility_from(
            provider_select, "value", backward=lambda v: v != CUSTOM_PROVIDER
        )

        with ui.column().classes("w-full gap-4").bind_visibility_from(
            provider_select, "value", backward=lambda v: v == CUSTOM_PROVIDER
        ):
            custom_base_url_input = ui.input(
                label="Base URL",
                placeholder="https://your-endpoint.example.com/v1",
                value=settings.custom_base_url,
            ).classes("w-full")

            custom_model_input = ui.input(
                label="Model ID",
                placeholder="e.g. llama-3.1-70b-instruct",
                value=settings.text_model if is_custom else "",
            ).classes("w-full")

        api_key_input = ui.input(
            label=current_env_key,
            placeholder="sk-...",
            password=True,
            password_toggle_button=True,
            value=settings.api_keys.get(current_env_key, ""),
        ).classes("w-full")

        def _on_provider_change() -> None:
            provider = provider_select.value
            if provider == CUSTOM_PROVIDER:
                api_key_input.label = CUSTOM_API_KEY_STORAGE_KEY
                api_key_input.value = settings.api_keys.get(CUSTOM_API_KEY_STORAGE_KEY, "")
                return
            info = PROVIDERS[provider]
            models = get_provider_models(provider)
            current_model = model_select.value
            model_select.set_options(models)
            model_select.value = current_model if current_model in models else models[0]
            api_key_input.label = info["env_key"]
            api_key_input.value = settings.api_keys.get(info["env_key"], "")

        provider_select.on_value_change(lambda _: _on_provider_change())

        # -- Image Model ------------------------------------------------------------
        _section("Image Generation")

        image_model_select = ui.select(
            label="Image Model",
            options=DEFAULT_IMAGE_MODELS,
            value=settings.image_model,
        ).classes("w-full")

        gemini_env_key = PROVIDERS["Google"]["env_key"]

        image_api_key_input = ui.input(
            label=gemini_env_key,
            placeholder="Required for image generation (Gemini)",
            password=True,
            password_toggle_button=True,
            value=settings.api_keys.get(gemini_env_key, ""),
        ).classes("w-full").bind_visibility_from(
            provider_select, "value", backward=lambda v: v != "Google"
        )

        ui.label(
            "Image generation reuses your Google LLM Provider API key above."
        ).classes("text-xs text-gray-500").bind_visibility_from(
            provider_select, "value", backward=lambda v: v == "Google"
        )

        # -- TTS (Google Cloud) -----------------------------------------------------
        _section("Text-to-Speech (Google Cloud)")

        tts_key_input = ui.input(
            label="Google TTS API Key",
            placeholder="Your Google Cloud API key for TTS",
            password=True,
            password_toggle_button=True,
            value=settings.api_keys.get("GOOGLE_TTS_KEY", ""),
        ).classes("w-full")

        # -- Defaults ---------------------------------------------------------------
        _section("Defaults")

        language_options = [lang.value for lang in Language]

        native_select = ui.select(
            label="Native Language",
            options=language_options,
            value=settings.defaults.native_language,
        ).classes("w-full")

        target_select = ui.select(
            label="Target Language",
            options=language_options,
            value=settings.defaults.target_language,
        ).classes("w-full")

        generate_image_switch = ui.switch(
            "Generate images by default",
            value=settings.defaults.generate_image,
        )

        # -- Save button ------------------------------------------------------------
        ui.separator()

        def _save():
            provider = provider_select.value
            if provider == CUSTOM_PROVIDER:
                text_model = (custom_model_input.value or "").strip()
                env_key = CUSTOM_API_KEY_STORAGE_KEY
                custom_base_url = (custom_base_url_input.value or "").strip()
            else:
                text_model = model_select.value or ""
                env_key = PROVIDERS[provider]["env_key"]
                custom_base_url = ""

            api_keys = {
                **settings.api_keys,
                env_key: api_key_input.value or "",
                "GOOGLE_TTS_KEY": tts_key_input.value or "",
            }
            if provider != "Google":
                api_keys[gemini_env_key] = image_api_key_input.value or ""

            new_settings = Settings(
                provider=provider,
                text_model=text_model,
                image_model=image_model_select.value or "",
                custom_base_url=custom_base_url,
                api_keys=api_keys,
                defaults=DefaultsConfig(
                    native_language=native_select.value or "",
                    target_language=target_select.value or "",
                    generate_image=bool(generate_image_switch.value),
                ),
            )
            save_settings(new_settings)
            apply_env(new_settings)
            ui.context.client.storage["settings"] = new_settings
            ui.notify("Settings saved", type="positive")

        ui.button("Save", on_click=_save, icon="save").props("unelevated").classes(
            "w-full"
        )


def _section(title: str) -> None:
    """Render a section heading."""
    ui.label(title).classes("text-lg font-semibold text-primary mt-2")
