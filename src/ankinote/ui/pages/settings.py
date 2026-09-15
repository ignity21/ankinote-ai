"""Settings page — LLM provider, TTS, and default language preferences."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from nicegui import events, ui

from ankinote.consts import TARGET_LANGUAGES, Language
from ankinote.ui.config import (
    CUSTOM_VENDOR,
    DEFAULT_IMAGE_PROFILE_NAME,
    DEFAULT_TEXT_PROFILE_NAME,
    IMAGE_PROVIDERS,
    PROVIDERS,
    DefaultsConfig,
    ProviderProfile,
    Settings,
    apply_env,
    fetch_image_model_ids,
    fetch_model_ids,
    get_image_provider_models,
    get_provider_models,
    load_settings,
    save_settings,
    unique_name,
)
from ankinote.ui.config_transfer import (
    MIN_PASSPHRASE_LENGTH,
    ConfigImportError,
    export_config,
    import_config,
    merge_bundle,
)
from ankinote.ui.i18n import set_locale, t
from ankinote.ui.pages.word import format_error
from ankinote.ui.sync import sync_settings

# The vendor options offered by each rack's "Add provider" dialog: the
# curated templates plus the generic custom/other endpoint.
_TEXT_VENDOR_OPTIONS: tuple[str, ...] = (*PROVIDERS.keys(), CUSTOM_VENDOR)
_IMAGE_VENDOR_OPTIONS: tuple[str, ...] = (*IMAGE_PROVIDERS.keys(), CUSTOM_VENDOR)


@dataclass
class RouteDraft:
    """One provider profile shown on the settings page, edited in place."""

    name: str
    vendor: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    saved: bool = False


def _default_route(
    vendor: str,
    vendor_templates: dict[str, dict],
    get_model_options: Callable[[str], list[str]],
) -> RouteDraft:
    """A placeholder route used only when a settings object has none saved."""
    return RouteDraft(
        name=vendor,
        vendor=vendor,
        model=get_model_options(vendor)[0],
        base_url=vendor_templates[vendor]["api_base"],
    )


def _routes_from_settings(settings: Settings) -> list[RouteDraft]:
    """Build the editable text-route list from every saved profile."""
    routes = [
        RouteDraft(
            name=name,
            vendor=profile.vendor,
            model=profile.model,
            base_url=profile.base_url,
            api_key=profile.api_key,
            saved=True,
        )
        for name, profile in settings.text_providers.items()
    ]
    if not routes:
        routes.append(
            _default_route(DEFAULT_TEXT_PROFILE_NAME, PROVIDERS, get_provider_models)
        )
    return routes


def _image_routes_from_settings(settings: Settings) -> list[RouteDraft]:
    """Build the editable image-route list from every saved profile."""
    routes = [
        RouteDraft(
            name=name,
            vendor=profile.vendor,
            model=profile.model,
            base_url=profile.base_url,
            api_key=profile.api_key,
            saved=True,
        )
        for name, profile in settings.image_providers.items()
    ]
    if not routes:
        routes.append(
            _default_route(
                DEFAULT_IMAGE_PROFILE_NAME, IMAGE_PROVIDERS, get_image_provider_models
            )
        )
    return routes


def _route_hint(route: RouteDraft, vendor_templates: dict[str, dict]) -> str:
    """One-line description shown under a route editor."""
    info = vendor_templates.get(route.vendor)
    if route.vendor == CUSTOM_VENDOR or info is None:
        return route.base_url or "OpenAI-compatible endpoint"
    return f"{route.vendor} · {info['litellm_provider']}"


def _suggest_name(vendor: str, routes: list[RouteDraft]) -> str:
    """A default profile name for a newly-picked vendor, deduped against routes."""
    base = "Custom" if vendor == CUSTOM_VENDOR else vendor
    return unique_name(base, {r.name for r in routes})


class RouteRack:
    """A pill rack of saved provider profiles plus an editor for the active one.

    Shared by the text- and image-generation sections so both offer the exact
    same add/select/fetch/remove/save interaction — only the vendor catalog
    and model lookup differ. Every profile — vendor-templated or fully custom
    (``vendor == CUSTOM_VENDOR``) — carries its own name, base URL, model, and
    API key, so multiple accounts of the same vendor can coexist.
    """

    def __init__(
        self,
        *,
        vendor_templates: dict[str, dict],
        get_model_options: Callable[[str], list[str]],
        fetch_ids: Callable[..., Awaitable[list[str]]],
        routes: list[RouteDraft],
        selected: int,
        on_save: Callable[[], None],
        on_removed: Callable[[], None],
        fetched_noun: str = "models",
    ) -> None:
        self.vendor_templates = vendor_templates
        self.vendor_options: tuple[str, ...] = (*vendor_templates.keys(), CUSTOM_VENDOR)
        self.get_model_options = get_model_options
        self.fetch_ids = fetch_ids
        self.routes = routes
        self.state: dict = {"selected": selected}
        self.on_save = on_save
        self.on_removed = on_removed
        self.fetched_noun = fetched_noun

    def select(self, index: int) -> None:
        self.state["selected"] = index
        self.workspace.refresh()

    def add_profile(self, *, name: str, vendor: str, base_url: str) -> None:
        options = self.get_model_options(vendor) if vendor != CUSTOM_VENDOR else []
        model = options[0] if options else ""
        self.routes.append(
            RouteDraft(name=name, vendor=vendor, model=model, base_url=base_url)
        )
        self.select(len(self.routes) - 1)

    def remove(self, index: int) -> None:
        route = self.routes[index]
        if not route.saved:
            self.routes.pop(index)
            self.state["selected"] = max(0, index - 1)
            self.workspace.refresh()
            return
        self._confirm_remove(route, index)

    def _confirm_remove(self, route: RouteDraft, index: int) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96 gap-2"):
            ui.label(t("settings.remove_confirm", name=route.name)).classes(
                "text-lg font-semibold"
            )
            ui.label(t("settings.remove_help")).classes("text-sm text-slate-600")

            def _confirm() -> None:
                self.routes.pop(index)
                self.state["selected"] = max(0, index - 1)
                self.on_removed()
                dialog.close()
                self.workspace.refresh()
                ui.notify(t("settings.removed", name=route.name), type="positive")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.remove"), on_click=_confirm, icon="delete").props(
                    "color=negative"
                )
        dialog.open()

    def _open_add_dialog(self) -> None:
        vendor_options = list(self.vendor_options)
        last_vendor = {"value": vendor_options[0]}

        with ui.dialog() as dialog, ui.card().classes("w-96 gap-3 route-dialog"):
            ui.label(t("settings.add_provider")).classes("text-lg font-semibold")
            vendor_select = ui.select(
                label=t("settings.vendor"),
                options=vendor_options,
                value=vendor_options[0],
            ).classes("w-full")
            name_input = ui.input(
                label=t("settings.name"),
                value=_suggest_name(vendor_options[0], self.routes),
            ).classes("w-full")
            base_input = ui.input(
                label=t("settings.base_url"),
                value=self.vendor_templates.get(vendor_options[0], {}).get(
                    "api_base", ""
                ),
            ).classes("w-full")

            def _on_vendor_change(e) -> None:
                vendor = e.value or CUSTOM_VENDOR
                prev_suggestion = _suggest_name(last_vendor["value"], self.routes)
                if (name_input.value or "") == prev_suggestion:
                    name_input.value = _suggest_name(vendor, self.routes)
                base_input.value = self.vendor_templates.get(vendor, {}).get(
                    "api_base", ""
                )
                last_vendor["value"] = vendor

            vendor_select.on_value_change(_on_vendor_change)

            def _create() -> None:
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify(t("settings.name_first"), type="warning")
                    return
                if any(r.name == name for r in self.routes):
                    ui.notify(t("settings.duplicate", name=name), type="warning")
                    return
                self.add_profile(
                    name=name,
                    vendor=vendor_select.value or CUSTOM_VENDOR,
                    base_url=(base_input.value or "").strip(),
                )
                dialog.close()
                self.workspace.refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.create"), on_click=_create).props(
                    "unelevated no-caps"
                )
        dialog.open()

    @ui.refreshable_method
    def workspace(self) -> None:
        if not self.routes:  # user removed the last route — fall back to a default
            first = self.vendor_options[0]
            self.routes.append(
                RouteDraft(
                    name=first,
                    vendor=first,
                    model=self.get_model_options(first)[0],
                    base_url=self.vendor_templates[first]["api_base"],
                )
            )
        selected = max(0, min(self.state["selected"], len(self.routes) - 1))
        self.state["selected"] = selected
        route = self.routes[selected]

        with ui.row().classes("route-rack"):
            for index, item in enumerate(self.routes):
                classes = "route-pill"
                if index == selected:
                    classes += " route-pill--active"
                with (
                    ui.element("button")
                    .classes(classes)
                    .on("click", lambda *_, index=index: self.select(index))
                ):
                    ui.icon("dns" if item.vendor == CUSTOM_VENDOR else "hub").classes(
                        "text-sm"
                    )
                    ui.label(item.name or t("settings.new_provider"))
                    if not item.saved:
                        ui.label(t("settings.draft")).classes("route-pill__tag")

            add_btn = (
                ui.button(icon="add", on_click=self._open_add_dialog)
                .props("flat round dense")
                .classes("route-add")
            )
            with add_btn:
                ui.tooltip(t("settings.add_provider"))

        with ui.column().classes("route-editor"):
            name_input = ui.input(
                label=t("settings.name"),
                value=route.name,
            ).classes("w-full")
            name_input.on_value_change(
                lambda e: setattr(route, "name", (e.value or "").strip())
            )
            base_input = ui.input(
                label=t("settings.base_url"),
                placeholder="https://your-endpoint.example.com/v1",
                value=route.base_url,
            ).classes("w-full")
            base_input.on_value_change(
                lambda e: setattr(route, "base_url", (e.value or "").strip())
            )

            vendor_info = self.vendor_templates.get(route.vendor)
            supports_fetch = vendor_info is None or vendor_info.get(
                "supports_fetch", True
            )

            if route.vendor == CUSTOM_VENDOR:
                model_options = [route.model] if route.model else []
            else:
                model_options = self.get_model_options(route.vendor)
            if route.model and route.model not in model_options:
                model_options = [route.model, *model_options]

            with ui.row().classes("route-model-row w-full items-center gap-2"):
                model_select = ui.select(
                    label=t("settings.model"),
                    options=model_options,
                    value=route.model or (model_options[0] if model_options else None),
                    with_input=True,
                    new_value_mode="add-unique",
                ).classes("flex-1 min-w-0")
                model_select.on_value_change(
                    lambda e: setattr(route, "model", e.value or "")
                )
                fetch_btn = None
                if supports_fetch:
                    fetch_btn = (
                        ui.button(icon="sync")
                        .props("flat dense")
                        .classes("route-fetch-btn")
                    )
                    with fetch_btn:
                        ui.tooltip(t("settings.fetch_models"))

            key_input = ui.input(
                label=vendor_info["env_key"] if vendor_info else t("settings.api_key"),
                placeholder="sk-…",
                password=True,
                password_toggle_button=True,
                value=route.api_key,
            ).classes("w-full")
            key_input.on_value_change(
                lambda e: setattr(route, "api_key", e.value or "")
            )

            if fetch_btn is not None:

                async def _fetch(*, _route: RouteDraft = route) -> None:
                    key = (key_input.value or "").strip()
                    info = self.vendor_templates.get(_route.vendor)
                    provider = info["litellm_provider"] if info else "openai"
                    if not key and provider != "fal_ai":
                        ui.notify(t("settings.enter_key"), type="warning")
                        return
                    api_base = (base_input.value or "").strip()
                    model_api_base = (
                        info.get("model_api_base", api_base) if info else api_base
                    )
                    if not model_api_base:
                        ui.notify(t("settings.enter_base"), type="warning")
                        return
                    prefix = info["model_prefix"] if info else None

                    fetch_btn.props("loading")
                    fetch_btn.update()
                    try:
                        ids = await self.fetch_ids(
                            litellm_provider=provider,
                            api_base=model_api_base,
                            api_key=key,
                            model_prefix=prefix,
                        )
                    except (httpx.HTTPError, ValueError) as exc:
                        ui.notify(
                            t("settings.fetch_failed", message=format_error(exc)),
                            type="negative",
                        )
                        return
                    finally:
                        fetch_btn.props(remove="loading")
                        fetch_btn.update()

                    if not ids:
                        ui.notify(
                            t("settings.no_models", noun=self.fetched_noun),
                            type="warning",
                        )
                        return
                    current = model_select.value
                    options = ids if not current or current in ids else [current, *ids]
                    model_select.set_options(options, value=current or ids[0])
                    _route.model = model_select.value or ""
                    ui.notify(
                        t("settings.loaded", count=len(ids), noun=self.fetched_noun),
                        type="positive",
                    )

                fetch_btn.on("click", _fetch)

            ui.label(_route_hint(route, self.vendor_templates)).classes(
                "text-xs text-slate-500 pt-1"
            )
            with ui.row().classes("w-full justify-between items-center"):
                ui.button(
                    t("common.remove"),
                    icon="delete",
                    on_click=lambda: self.remove(selected),
                ).props("flat dense no-caps color=negative")
                ui.button(
                    t("settings.save_provider"), icon="save", on_click=self.on_save
                ).props("unelevated no-caps").classes("route-save-btn")


def settings_page() -> None:
    """Render the settings page."""

    _settings_styles()

    cached = ui.context.client.storage.get("settings")
    settings: Settings = (
        cached
        if isinstance(cached, Settings) and hasattr(cached, "text_providers")
        else load_settings()
    )
    set_locale(settings.ui_language)

    def _build_settings() -> Settings | None:
        """Collect every field into a Settings, or notify and return None."""
        active_text_route = (
            text_rack.routes[text_rack.state["selected"]] if text_rack.routes else None
        )
        active_image_route = (
            image_rack.routes[image_rack.state["selected"]]
            if image_rack.routes
            else None
        )

        text_providers: dict[str, ProviderProfile] = {}
        for route in text_rack.routes:
            name = route.name.strip()
            if not name:
                if route is active_text_route:
                    ui.notify(t("settings.name_first"), type="warning")
                    return None
                continue  # unnamed draft the user left behind — skip it
            if name in text_providers:
                ui.notify(t("settings.two_named", name=name), type="warning")
                return None
            text_providers[name] = ProviderProfile(
                vendor=route.vendor,
                model=route.model,
                base_url=route.base_url,
                api_key=route.api_key,
            )

        image_providers: dict[str, ProviderProfile] = {}
        for route in image_rack.routes:
            name = route.name.strip()
            if not name:
                if route is active_image_route:
                    ui.notify(t("settings.name_first"), type="warning")
                    return None
                continue
            if name in image_providers:
                ui.notify(t("settings.two_named", name=name), type="warning")
                return None
            image_providers[name] = ProviderProfile(
                vendor=route.vendor,
                model=route.model,
                base_url=route.base_url,
                api_key=route.api_key,
            )

        return Settings(
            text_providers=text_providers,
            active_text_provider=active_text_route.name.strip()
            if active_text_route
            else "",
            image_providers=image_providers,
            active_image_provider=active_image_route.name.strip()
            if active_image_route
            else "",
            image_size=settings.image_size,
            api_keys={"GOOGLE_TTS_KEY": tts_key_input.value or ""},
            defaults=DefaultsConfig(
                native_language=native_select.value or "",
                target_language=target_select.value or "",
                generate_image=bool(generate_image_switch.value),
            ),
            ui_language=settings.ui_language,
        )

    def _persist(new_settings: Settings) -> None:
        nonlocal settings
        save_settings(new_settings)
        apply_env(new_settings)
        ui.context.client.storage["settings"] = new_settings
        settings = new_settings

    def _save() -> None:
        new_settings = _build_settings()
        if new_settings is None:
            return
        _persist(new_settings)
        for route in (*text_rack.routes, *image_rack.routes):
            route.saved = bool(route.name.strip())
        text_rack.workspace.refresh()
        image_rack.workspace.refresh()
        ui.notify(t("common.settings_saved"), type="positive")

    def _persist_after_removal() -> None:
        new_settings = _build_settings()
        if new_settings is not None:
            _persist(new_settings)

    text_routes = _routes_from_settings(settings)
    text_rack = RouteRack(
        vendor_templates=PROVIDERS,
        get_model_options=get_provider_models,
        fetch_ids=fetch_model_ids,
        routes=text_routes,
        selected=next(
            (
                i
                for i, r in enumerate(text_routes)
                if r.name == settings.active_text_provider
            ),
            0,
        ),
        on_save=_save,
        on_removed=_persist_after_removal,
        fetched_noun="models",
    )

    image_routes = _image_routes_from_settings(settings)
    image_rack = RouteRack(
        vendor_templates=IMAGE_PROVIDERS,
        get_model_options=get_image_provider_models,
        fetch_ids=fetch_image_model_ids,
        routes=image_routes,
        selected=next(
            (
                i
                for i, r in enumerate(image_routes)
                if r.name == settings.active_image_provider
            ),
            0,
        ),
        on_save=_save,
        on_removed=_persist_after_removal,
        fetched_noun="image models",
    )

    with ui.column().classes("w-full max-w-3xl mx-auto p-6 md:p-8 gap-7"):
        ui.label(t("settings.title")).classes("settings-title")

        sync_settings()

        with ui.column().classes("gap-1"):
            ui.label(t("settings.generation_route")).classes("settings-eyebrow")
            ui.label(t("settings.text_where")).classes("settings-h2")
            ui.label(t("settings.route_help")).classes("text-sm text-slate-500")

        text_rack.workspace()

        # -- Image Model ------------------------------------------------------------
        with ui.column().classes("gap-1 mt-2"):
            ui.label(t("settings.image_route")).classes("settings-eyebrow")
            ui.label(t("settings.image_where")).classes("settings-h2")
            ui.label(t("settings.route_help")).classes("text-sm text-slate-500")

        image_rack.workspace()

        # -- TTS (Google Cloud) -----------------------------------------------------
        _section(t("settings.tts"))

        tts_key_input = ui.input(
            label=t("settings.tts_key"),
            placeholder=t("settings.tts_placeholder"),
            password=True,
            password_toggle_button=True,
            value=settings.api_keys.get("GOOGLE_TTS_KEY", ""),
        ).classes("w-full")

        # -- Defaults ---------------------------------------------------------------
        _section(t("settings.defaults"))

        language_options = [lang.value for lang in Language]
        target_language_options = [lang.value for lang in TARGET_LANGUAGES]

        native_select = ui.select(
            label=t("settings.native"),
            options=language_options,
            value=settings.defaults.native_language,
        ).classes("w-full")

        target_select = ui.select(
            label=t("settings.target"),
            options=target_language_options,
            value=settings.defaults.target_language,
        ).classes("w-full")

        generate_image_switch = ui.switch(
            t("settings.images_default"),
            value=settings.defaults.generate_image,
        )

        # -- Save -----------------------------------------------------------------
        ui.separator()
        ui.button(t("settings.save"), on_click=_save, icon="save").props(
            "unelevated"
        ).classes("w-full settings-save")

        # -- Backup & transfer ----------------------------------------------------
        _section(t("settings.transfer"))
        ui.label(t("settings.transfer_help")).classes("text-sm text-slate-500")
        _config_transfer_controls(
            current=lambda: _build_settings() or settings, persist=_persist
        )


def _config_transfer_controls(
    *, current: Callable[[], Settings], persist: Callable[[Settings], None]
) -> None:
    """Render the passphrase-protected export/import of provider config."""

    async def _run_export(passphrase: str, dialog: ui.dialog) -> None:
        if len(passphrase) < MIN_PASSPHRASE_LENGTH:
            ui.notify(
                t("settings.passphrase_short", min=MIN_PASSPHRASE_LENGTH),
                type="warning",
            )
            return
        blob = await asyncio.to_thread(export_config, current(), passphrase)
        dialog.close()
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        ui.download(blob, f"ankinote-config-{stamp}.json", "application/json")
        ui.notify(t("settings.export_done"), type="positive")

    def _open_export() -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96 gap-3"):
            ui.label(t("settings.export_title")).classes("text-lg font-semibold")
            ui.label(t("settings.passphrase_help", min=MIN_PASSPHRASE_LENGTH)).classes(
                "text-sm text-slate-500"
            )
            pw = ui.input(
                t("settings.passphrase"), password=True, password_toggle_button=True
            ).classes("w-full")
            pw.on("keydown.enter", lambda: _run_export(pw.value or "", dialog))
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props(
                    "flat no-caps"
                )
                ui.button(
                    t("settings.export_run"),
                    on_click=lambda: _run_export(pw.value or "", dialog),
                ).props("unelevated no-caps")
        dialog.open()

    async def _run_import(blob: bytes, passphrase: str, dialog: ui.dialog) -> None:
        try:
            bundle = await asyncio.to_thread(import_config, blob, passphrase)
        except ConfigImportError:
            ui.notify(t("settings.import_failed"), type="negative")
            return
        persist(merge_bundle(current(), bundle))
        dialog.close()
        ui.notify(
            t("settings.import_done", count=bundle.profile_count), type="positive"
        )
        ui.navigate.reload()

    def _open_import(blob: bytes) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96 gap-3"):
            ui.label(t("settings.import_title")).classes("text-lg font-semibold")
            ui.label(t("settings.import_passphrase_help")).classes(
                "text-sm text-slate-500"
            )
            pw = ui.input(
                t("settings.passphrase"), password=True, password_toggle_button=True
            ).classes("w-full")
            pw.on(
                "keydown.enter",
                lambda: _run_import(blob, pw.value or "", dialog),
            )
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props(
                    "flat no-caps"
                )
                ui.button(
                    t("settings.import_confirm"),
                    on_click=lambda: _run_import(blob, pw.value or "", dialog),
                ).props("unelevated no-caps")
        dialog.open()

    async def _on_file(event: events.UploadEventArguments) -> None:
        blob = await event.file.read()
        picker.reset()
        _open_import(blob)

    picker = (
        ui.upload(auto_upload=True, max_files=1, on_upload=_on_file)
        .props("accept=.json")
        .classes("hidden")
    )

    with ui.row().classes("gap-3 items-center flex-wrap"):
        ui.button(t("settings.export"), icon="lock", on_click=_open_export).props(
            "outline no-caps"
        )
        ui.button(
            t("settings.import"),
            icon="lock_open",
            on_click=lambda: picker.run_method("pickFiles"),
        ).props("outline no-caps")


def _section(title: str) -> None:
    """Render a section heading."""
    ui.label(title).classes("text-lg font-semibold text-primary mt-2")


def _settings_styles() -> None:
    """Small design system for the settings page."""
    ui.add_css(
        """
        .settings-title {
            color: #0f172a;
            font-size: 1.75rem;
            font-weight: 800;
            letter-spacing: -.02em;
        }
        .settings-eyebrow {
            color: #64748b;
            font-size: .72rem;
            font-weight: 700;
            letter-spacing: .11em;
            text-transform: uppercase;
        }
        .settings-h2 {
            color: #0f172a;
            font-size: 1.15rem;
            font-weight: 600;
        }
        .route-rack {
            align-items: center;
            flex-wrap: wrap;
            gap: .4rem;
        }
        .route-pill {
            -webkit-appearance: none;
            appearance: none;
            align-items: center;
            background: #fff;
            font: inherit;
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            color: #334155;
            cursor: pointer;
            display: inline-flex;
            font-size: .82rem;
            font-weight: 600;
            gap: .4rem;
            padding: .4rem .85rem;
        }
        .route-pill:hover {
            background: #eff6ff;
            border-color: #60a5fa;
        }
        .route-pill:focus-visible {
            outline: 2px solid #2563eb;
            outline-offset: 2px;
        }
        .route-pill--active,
        .route-pill--active:hover {
            background: #2563eb;
            border-color: #2563eb;
            color: #fff;
        }
        .route-pill__tag {
            background: rgba(148, 163, 184, .28);
            border-radius: 5px;
            font-size: .6rem;
            font-weight: 800;
            letter-spacing: .08em;
            padding: .05rem .3rem;
            text-transform: uppercase;
        }
        .route-add {
            border: 1px dashed #93c5fd !important;
            color: #2563eb !important;
        }
        .route-editor {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            gap: .9rem;
            margin-top: .4rem;
            padding: 1.1rem;
            width: 100%;
        }
        .route-dialog {
            border-radius: 14px;
        }
        .route-model-row {
            flex-wrap: nowrap;
        }
        .route-fetch-btn {
            flex: 0 0 auto;
        }
        .route-save-btn {
            border-radius: 8px;
        }
        .settings-save {
            border-radius: 10px;
            min-height: 2.7rem;
        }
        @media (prefers-reduced-motion: no-preference) {
            .route-pill { transition: background-color .16s ease, border-color .16s ease; }
        }
        .body--dark .settings-title,
        .body--dark .settings-h2 { color: #f1f5f9; }
        .body--dark .route-pill {
            background: #1e293b;
            border-color: #334155;
            color: #cbd5e1;
        }
        .body--dark .route-pill:hover { background: #1e3a5f; }
        .body--dark .route-editor {
            background: #0f172a;
            border-color: #1e293b;
        }
        """
    )
