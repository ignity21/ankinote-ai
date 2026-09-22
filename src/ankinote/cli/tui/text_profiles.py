"""Interactive text-provider-profile submenu."""

import questionary

from ankinote.settings import (
    CUSTOM_VENDOR,
    PROVIDERS,
    Settings,
    get_provider_models,
    save_settings,
    unique_name,
)

from .profile_logic import add_profile, remove_profile, rename_profile

_VENDOR_OPTIONS = (*PROVIDERS.keys(), CUSTOM_VENDOR)


def _model_options(vendor: str) -> list[str]:
    return get_provider_models(vendor) if vendor != CUSTOM_VENDOR else []


def _label(name: str, active: str) -> str:
    return f"{name} (active)" if name == active else name


def run_text_profiles_menu(settings: Settings) -> None:
    """Loop the text-profile submenu until the user picks "Back"."""
    while True:
        choices = [
            questionary.Choice(_label(name, settings.active_text_provider), value=name)
            for name in settings.text_providers
        ] + [
            questionary.Separator(),
            questionary.Choice("+ Add profile", value="__add__"),
            questionary.Choice("< Back", value="__back__"),
        ]
        selection = questionary.select("Text provider profiles", choices=choices).ask()
        if selection is None or selection == "__back__":
            return
        if selection == "__add__":
            _add(settings)
        else:
            _edit(settings, selection)


def _add(settings: Settings) -> None:
    vendor = questionary.select("Vendor", choices=list(_VENDOR_OPTIONS)).ask()
    if vendor is None:
        return
    default_name = unique_name(
        "Custom" if vendor == CUSTOM_VENDOR else vendor, set(settings.text_providers)
    )
    name = questionary.text("Profile name", default=default_name).ask()
    if not name:
        return
    base_url = questionary.text(
        "Base URL", default=PROVIDERS.get(vendor, {}).get("api_base", "")
    ).ask()
    if base_url is None:
        return
    try:
        add_profile(
            settings.text_providers,
            name=name,
            vendor=vendor,
            base_url=base_url.strip(),
            model_options=_model_options(vendor),
        )
    except ValueError as exc:
        questionary.print(str(exc), style="fg:red")
        return
    settings.active_text_provider = name
    save_settings(settings)


def _set_active(settings: Settings, name: str, profile) -> bool:
    settings.active_text_provider = name
    return True


def _edit_model(settings: Settings, name: str, profile) -> bool:
    options = _model_options(profile.vendor)
    model = (
        questionary.select("Model", choices=options, default=profile.model).ask()
        if options
        else questionary.text("Model", default=profile.model).ask()
    )
    if model is None:
        return False
    profile.model = model
    return True


def _edit_base_url(settings: Settings, name: str, profile) -> bool:
    value = questionary.text("Base URL", default=profile.base_url).ask()
    if value is None:
        return False
    profile.base_url = value.strip()
    return True


def _edit_api_key(settings: Settings, name: str, profile) -> bool:
    value = questionary.password("API key", default=profile.api_key).ask()
    if value is None:
        return False
    profile.api_key = value
    return True


def _rename(settings: Settings, name: str, profile) -> bool:
    new_name = questionary.text("New name", default=name).ask()
    if not new_name:
        return False
    try:
        settings.active_text_provider = rename_profile(
            settings.text_providers, settings.active_text_provider, name, new_name
        )
    except ValueError as exc:
        questionary.print(str(exc), style="fg:red")
        return False
    return True


def _remove(settings: Settings, name: str, profile) -> bool:
    if not questionary.confirm(f"Remove profile {name!r}?", default=False).ask():
        return False
    try:
        settings.active_text_provider = remove_profile(
            settings.text_providers, settings.active_text_provider, name
        )
    except ValueError as exc:
        questionary.print(str(exc), style="fg:red")
        return False
    return True


_ACTIONS = {
    "Set active": _set_active,
    "Edit model": _edit_model,
    "Edit base URL": _edit_base_url,
    "Edit API key": _edit_api_key,
    "Rename": _rename,
    "Remove": _remove,
}


def _edit(settings: Settings, name: str) -> None:
    profile = settings.text_providers[name]
    action = questionary.select(
        f"Editing {name!r}", choices=[*_ACTIONS, "< Back"]
    ).ask()
    if action is None or action == "< Back":
        return
    if _ACTIONS[action](settings, name, profile):
        save_settings(settings)
