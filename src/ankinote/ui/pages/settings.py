"""Settings page — LLM provider, TTS, and default language preferences."""

from nicegui import ui

from ankinote.consts import Language
from ankinote.ui.config import (
    CUSTOM_API_KEY_STORAGE_KEY,
    CUSTOM_PROVIDER,
    DEFAULT_IMAGE_MODELS,
    NEW_CUSTOM_PROVIDER,
    PROVIDERS,
    CustomProvider,
    DefaultsConfig,
    Settings,
    apply_env,
    get_provider_models,
    save_settings,
)


def settings_page() -> None:
    """Render the settings page."""

    _provider_ui_styles()

    settings = ui.context.client.storage.get("settings")
    if settings is None:
        from ankinote.ui.config import load_settings
        settings = load_settings()

    custom_profile = settings.custom_providers.get(settings.provider)
    if settings.provider == CUSTOM_PROVIDER and custom_profile is None:
        custom_profile = CustomProvider(
            base_url=settings.custom_base_url,
            model=settings.text_model,
            api_key=settings.api_keys.get(CUSTOM_API_KEY_STORAGE_KEY, ""),
        )
    is_custom = custom_profile is not None or settings.provider in {
        CUSTOM_PROVIDER,
        NEW_CUSTOM_PROVIDER,
    }
    current_env_key = (
        CUSTOM_API_KEY_STORAGE_KEY if is_custom else PROVIDERS[settings.provider]["env_key"]
    )

    with ui.column().classes("w-full max-w-3xl mx-auto p-6 md:p-8 gap-7"):
        ui.label("Settings").classes("text-3xl font-bold tracking-tight text-slate-900")

        # -- LLM Provider -----------------------------------------------------------
        with ui.row().classes("items-end justify-between w-full gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Generation route").classes("settings-eyebrow")
                ui.label("Choose where card content is generated").classes(
                    "text-xl font-semibold text-slate-900"
                )
            ui.icon("hub").classes("text-3xl text-blue-600")

        with ui.element("div").classes("provider-route-ribbon"):
            ui.icon("bolt").classes("text-blue-600 text-xl")
            with ui.column().classes("gap-0 flex-1"):
                route_name = ui.label(settings.provider).classes("font-semibold text-slate-900")
                route_detail = ui.label("Active provider profile").classes(
                    "text-xs text-slate-500"
                )
            ui.label("ACTIVE").classes("route-status")

        provider_catalog = ui.row().classes("provider-catalog")

        provider_select = ui.select(
            label="Provider profile",
            options=[*PROVIDERS.keys(), *settings.custom_providers.keys(), NEW_CUSTOM_PROVIDER],
            value=settings.provider if settings.provider in PROVIDERS or is_custom else "OpenAI",
        ).classes("w-full provider-picker")

        model_select = ui.select(
            label="Model for this route",
            options=get_provider_models(settings.provider) if settings.provider in PROVIDERS else [],
            value=settings.text_model if settings.provider in PROVIDERS else None,
        ).classes("w-full provider-field").bind_visibility_from(
            provider_select, "value", backward=lambda v: v in PROVIDERS
        )

        with ui.column().classes("provider-custom-panel").bind_visibility_from(
            provider_select, "value", backward=lambda v: v not in PROVIDERS
        ):
            ui.label("OpenAI-compatible connection").classes("settings-eyebrow")

            custom_name_input = ui.input(
                label="Profile name",
                placeholder="e.g. Alibaba Cloud",
                value=settings.provider if custom_profile else "",
            ).classes("w-full provider-field")

            custom_base_url_input = ui.input(
                label="Base URL",
                placeholder="https://your-endpoint.example.com/v1",
                value=custom_profile.base_url if custom_profile else "",
            ).classes("w-full provider-field")

            custom_model_input = ui.input(
                label="Model ID",
                placeholder="e.g. llama-3.1-70b-instruct",
                value=custom_profile.model if custom_profile else "",
            ).classes("w-full provider-field")

        api_key_input = ui.input(
            label=current_env_key,
            placeholder="sk-...",
            password=True,
            password_toggle_button=True,
            value=custom_profile.api_key if custom_profile else settings.api_keys.get(current_env_key, ""),
        ).classes("w-full provider-field")

        def _on_provider_change() -> None:
            provider = provider_select.value
            route_name.set_text(provider)
            if provider == NEW_CUSTOM_PROVIDER:
                route_detail.set_text("Create a new OpenAI-compatible route")
                api_key_input.label = CUSTOM_API_KEY_STORAGE_KEY
                api_key_input.value = ""
                custom_name_input.value = ""
                custom_base_url_input.value = ""
                custom_model_input.value = ""
                return
            if provider in settings.custom_providers or provider == CUSTOM_PROVIDER:
                profile = settings.custom_providers.get(provider)
                if profile is None:
                    profile = CustomProvider(
                        base_url=settings.custom_base_url,
                        model=settings.text_model,
                        api_key=settings.api_keys.get(CUSTOM_API_KEY_STORAGE_KEY, ""),
                    )
                api_key_input.label = CUSTOM_API_KEY_STORAGE_KEY
                route_detail.set_text("OpenAI-compatible custom endpoint")
                api_key_input.value = profile.api_key
                custom_name_input.value = provider
                custom_base_url_input.value = profile.base_url
                custom_model_input.value = profile.model
                return
            info = PROVIDERS[provider]
            route_detail.set_text(f"Built-in route · {info['litellm_provider']}")
            models = get_provider_models(provider)
            current_model = model_select.value
            model_select.set_options(models)
            model_select.value = current_model if current_model in models else models[0]
            api_key_input.label = info["env_key"]
            api_key_input.value = settings.api_keys.get(info["env_key"], "")

        provider_select.on_value_change(lambda _: _on_provider_change())

        def _select_provider(provider: str) -> None:
            provider_select.set_value(provider)
            _on_provider_change()

        with provider_catalog:
            for provider in PROVIDERS:
                ui.button(
                    provider,
                    on_click=lambda provider=provider: _select_provider(provider),
                    icon="public",
                ).props("outline no-caps").classes("provider-chip")
            for provider in settings.custom_providers:
                ui.button(
                    provider,
                    on_click=lambda provider=provider: _select_provider(provider),
                    icon="dns",
                ).props("outline no-caps").classes("provider-chip")
            ui.button(
                "New endpoint",
                on_click=lambda: _select_provider(NEW_CUSTOM_PROVIDER),
                icon="add",
            ).props("flat no-caps").classes("provider-add-chip")

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
            custom_providers = dict(settings.custom_providers)
            if provider not in PROVIDERS:
                provider_name = (custom_name_input.value or "").strip()
                if not provider_name:
                    ui.notify("Enter a name for the custom provider", type="warning")
                    return
                if provider_name in PROVIDERS or provider_name == NEW_CUSTOM_PROVIDER:
                    ui.notify("That provider name is reserved", type="warning")
                    return
                text_model = (custom_model_input.value or "").strip()
                env_key = CUSTOM_API_KEY_STORAGE_KEY
                custom_base_url = (custom_base_url_input.value or "").strip()
                custom_providers[provider_name] = CustomProvider(
                    base_url=custom_base_url,
                    model=text_model,
                    api_key=api_key_input.value or "",
                )
                if provider not in {CUSTOM_PROVIDER, NEW_CUSTOM_PROVIDER} and provider != provider_name:
                    custom_providers.pop(provider, None)
                provider = provider_name
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
                custom_providers=custom_providers,
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

        def _delete_current_provider() -> None:
            provider = provider_select.value
            if provider not in settings.custom_providers:
                ui.notify("Select a saved custom provider to delete", type="warning")
                return

            with ui.dialog() as dialog, ui.card().classes("w-96"):
                ui.label(f'Delete custom provider "{provider}"?').classes(
                    "text-lg font-semibold"
                )
                ui.label(
                    "Its endpoint, model, and API key will be removed from this app."
                ).classes("text-sm text-gray-600")

                def _confirm_delete() -> None:
                    custom_providers = dict(settings.custom_providers)
                    custom_providers.pop(provider)
                    api_keys = dict(settings.api_keys)
                    if provider == CUSTOM_PROVIDER:
                        api_keys.pop(CUSTOM_API_KEY_STORAGE_KEY, None)

                    new_settings = Settings(
                        provider="OpenAI",
                        text_model=Settings().text_model,
                        image_model=settings.image_model,
                        image_size=settings.image_size,
                        api_keys=api_keys,
                        custom_providers=custom_providers,
                        defaults=settings.defaults,
                    )
                    save_settings(new_settings)
                    apply_env(new_settings)
                    ui.context.client.storage["settings"] = new_settings
                    dialog.close()
                    ui.notify(f'Provider "{provider}" deleted', type="positive")
                    ui.navigate.to("/settings")

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Delete", on_click=_confirm_delete, icon="delete").props(
                        "color=negative"
                    )
            dialog.open()

        ui.button("Save route", on_click=_save, icon="save").props("unelevated").classes(
            "w-full provider-save-button"
        )
        ui.button(
            "Delete custom provider",
            on_click=_delete_current_provider,
            icon="delete",
        ).props("flat color=negative").classes("w-full").bind_visibility_from(
            provider_select,
            "value",
            backward=lambda value: value in settings.custom_providers,
        )


def _section(title: str) -> None:
    """Render a section heading."""
    ui.label(title).classes("text-lg font-semibold text-primary mt-2")


def _provider_ui_styles() -> None:
    """Add the small design system used by the provider route workspace."""
    ui.add_css(
        """
        .settings-eyebrow {
            color: #64748b;
            font-size: .72rem;
            font-weight: 700;
            letter-spacing: .11em;
            text-transform: uppercase;
        }
        .provider-route-ribbon {
            align-items: center;
            background: linear-gradient(100deg, #eff6ff 0%, #f8fafc 72%);
            border: 1px solid #bfdbfe;
            border-radius: 14px;
            display: flex;
            gap: .8rem;
            min-height: 4.5rem;
            padding: .85rem 1rem;
        }
        .route-status {
            background: #dbeafe;
            border-radius: 999px;
            color: #1d4ed8;
            font-size: .66rem;
            font-weight: 800;
            letter-spacing: .09em;
            padding: .28rem .5rem;
        }
        .provider-catalog {
            align-items: center;
            gap: .45rem;
            padding: .1rem 0 .15rem;
        }
        .provider-chip {
            border-color: #cbd5e1 !important;
            border-radius: 999px !important;
            color: #334155 !important;
            font-size: .78rem;
            min-height: 2rem;
        }
        .provider-add-chip {
            color: #2563eb !important;
            font-size: .78rem;
            min-height: 2rem;
        }
        .provider-picker .q-field__control,
        .provider-field .q-field__control {
            border-radius: 10px;
        }
        .provider-picker .q-field__control {
            background: #fff;
            box-shadow: 0 1px 2px rgb(15 23 42 / .04);
        }
        .provider-custom-panel {
            background: #f8fafc;
            border-left: 3px solid #60a5fa;
            border-radius: 0 12px 12px 0;
            gap: .9rem;
            padding: 1rem;
            width: 100%;
        }
        .provider-save-button {
            background: #2563eb !important;
            border-radius: 10px;
            box-shadow: 0 8px 20px rgb(37 99 235 / .2);
            min-height: 2.8rem;
        }
        @media (prefers-reduced-motion: no-preference) {
            .provider-route-ribbon { transition: border-color .18s ease, box-shadow .18s ease; }
            .provider-route-ribbon:hover { box-shadow: 0 8px 22px rgb(37 99 235 / .08); }
            .provider-chip { transition: background-color .16s ease, border-color .16s ease; }
            .provider-chip:hover { background: #eff6ff !important; border-color: #60a5fa !important; }
        }
        """
    )
