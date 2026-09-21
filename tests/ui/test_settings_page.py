"""Tests for the settings page route-list helpers."""

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from ankinote.ui import sync
from ankinote.ui.config import (
    CUSTOM_VENDOR,
    IMAGE_PROVIDERS,
    PROVIDERS,
    ProviderProfile,
    Settings,
)
from ankinote.ui.pages import settings as settings_module
from ankinote.ui.pages.settings import (
    _IMAGE_VENDOR_OPTIONS,
    _TEXT_VENDOR_OPTIONS,
    _image_routes_from_settings,
    _route_hint,
    _routes_from_settings,
    _suggest_name,
)


def test_text_vendor_options_are_the_curated_list_plus_custom() -> None:
    # DeepSeek, xAI, and other litellm providers are reachable via
    # "Custom / Other".
    assert "DeepSeek" not in _TEXT_VENDOR_OPTIONS
    assert "xAI" not in _TEXT_VENDOR_OPTIONS
    assert {"OpenAI", "Anthropic", "Gemini"} <= set(_TEXT_VENDOR_OPTIONS)
    assert _TEXT_VENDOR_OPTIONS[-1] == CUSTOM_VENDOR


def test_image_vendor_options_are_the_curated_list_plus_custom() -> None:
    assert set(_IMAGE_VENDOR_OPTIONS) == {"OpenAI", "Gemini", "Fal", CUSTOM_VENDOR}


def test_routes_from_fresh_settings_shows_the_default_profile() -> None:
    routes = _routes_from_settings(Settings())
    assert [(r.name, r.vendor, r.saved) for r in routes] == [("OpenAI", "OpenAI", True)]


def test_routes_show_every_saved_profile() -> None:
    settings = Settings(
        text_providers={
            "OpenAI (work)": ProviderProfile(
                vendor="OpenAI", model="gpt-4o", api_key="sk-o"
            ),
            "Anthropic": ProviderProfile(
                vendor="Anthropic", model="claude-x", api_key="sk-a"
            ),
            "Local vLLM": ProviderProfile(
                vendor=CUSTOM_VENDOR, base_url="http://x/v1", model="m", api_key="k"
            ),
        },
        active_text_provider="OpenAI (work)",
    )
    routes = _routes_from_settings(settings)
    names = [r.name for r in routes]
    assert names == ["OpenAI (work)", "Anthropic", "Local vLLM"]
    assert all(r.saved for r in routes)


def test_route_hint_describes_vendor() -> None:
    (builtin,) = _routes_from_settings(Settings())
    assert _route_hint(builtin, PROVIDERS) == "OpenAI · openai"

    custom_settings = Settings(
        text_providers={
            "X": ProviderProfile(vendor=CUSTOM_VENDOR, base_url="http://h/v1")
        },
        active_text_provider="X",
    )
    (custom,) = _routes_from_settings(custom_settings)
    assert _route_hint(custom, PROVIDERS) == "http://h/v1"


def test_image_routes_from_fresh_settings_shows_the_default_profile() -> None:
    routes = _image_routes_from_settings(Settings())
    assert [(r.name, r.vendor, r.saved) for r in routes] == [("Gemini", "Gemini", True)]


def test_image_routes_show_every_saved_profile() -> None:
    settings = Settings(
        image_providers={
            "Gemini": ProviderProfile(
                vendor="Gemini",
                model="gemini/gemini-3.1-flash-lite-image",
                api_key="sk-g",
            ),
            "My xAI account": ProviderProfile(
                vendor=CUSTOM_VENDOR, model="xai/grok-2-image", api_key="sk-x"
            ),
        },
        active_image_provider="Gemini",
    )
    routes = _image_routes_from_settings(settings)
    assert [r.name for r in routes] == ["Gemini", "My xAI account"]
    assert all(r.saved for r in routes)


def test_image_route_hint_matches_vendor() -> None:
    (builtin,) = _image_routes_from_settings(Settings())
    assert _route_hint(builtin, IMAGE_PROVIDERS) == "Gemini · gemini"


def test_suggest_name_dedupes_against_existing_routes() -> None:
    routes = _routes_from_settings(Settings())  # has one "OpenAI" route already
    assert _suggest_name("OpenAI", routes) == "OpenAI (2)"
    assert _suggest_name("Anthropic", routes) == "Anthropic"
    assert _suggest_name(CUSTOM_VENDOR, routes) == "Custom"


@pytest.fixture
def _rendered_settings(monkeypatch):
    """A settings page backed by an in-memory Settings, sync in connect mode."""
    state = {
        "settings": Settings(
            text_providers={
                "OpenAI": ProviderProfile("OpenAI", "gpt-4o", "https://api", "sk-old"),
            },
            active_text_provider="OpenAI",
        )
    }
    monkeypatch.setattr(settings_module, "load_settings", lambda: state["settings"])
    monkeypatch.setattr(
        settings_module, "save_settings", lambda s: state.update(settings=s)
    )
    monkeypatch.setattr(settings_module, "apply_env", lambda _s: None)
    monkeypatch.setattr(sync, "get_shared_runtime", lambda: None)
    return state


async def test_transfer_section_renders_and_export_validates(
    _rendered_settings,
) -> None:
    async with user_simulation(settings_module.settings_page) as user:
        await user.open("/")
        await user.should_see("Backup & transfer")
        user.find(kind=ui.button, content="Export").click()
        await user.should_see("Export configuration")
        user.find("Passphrase").type("short")
        user.find(kind=ui.button, content="Export file").click()
        await user.should_see("at least")


async def test_backend_defaults_to_connect_and_hides_collection_path(
    _rendered_settings,
) -> None:
    async with user_simulation(settings_module.settings_page) as user:
        await user.open("/")
        await user.should_see("Anki Backend")
        await user.should_see("AnkiConnect (desktop app)")
        await user.should_not_see("Collection file path")


async def test_selecting_collection_backend_reveals_the_path_input(
    _rendered_settings,
) -> None:
    async with user_simulation(settings_module.settings_page) as user:
        await user.open("/")
        user.find("AnkiConnect (desktop app)").click()  # opens the dropdown
        user.find("Direct collection (no desktop app needed)").click()  # picks it
        await user.should_see("Collection file path")


async def test_apply_with_empty_collection_path_warns_instead_of_switching(
    _rendered_settings,
) -> None:
    async with user_simulation(settings_module.settings_page) as user:
        await user.open("/")
        user.find("AnkiConnect (desktop app)").click()
        user.find("Direct collection (no desktop app needed)").click()
        user.find(kind=ui.button, content="Apply").click()
        await user.should_see("Enter a collection file path first")


async def test_apply_with_a_path_persists_and_switches_backend(
    _rendered_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    switched = {"count": 0}

    async def fake_switch_backend() -> None:
        switched["count"] += 1

    monkeypatch.setattr(settings_module, "switch_backend", fake_switch_backend)

    async with user_simulation(settings_module.settings_page) as user:
        await user.open("/")
        user.find("AnkiConnect (desktop app)").click()
        user.find("Direct collection (no desktop app needed)").click()
        user.find("Collection file path").type("/tmp/ankinote-test/collection.anki2")
        user.find(kind=ui.button, content="Apply").click()
        await user.should_see("Anki backend switched")

    assert switched["count"] == 1
    assert _rendered_settings["settings"].anki_backend == "collection"
    assert (
        _rendered_settings["settings"].anki_collection_path
        == "/tmp/ankinote-test/collection.anki2"
    )
