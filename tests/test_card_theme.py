"""Card themes: palette tokens and fonts composed in front of each note type's CSS."""

import re
from importlib.resources import files

import pytest

from ankinote import card_theme
from ankinote.card_theme import CardTheme, compose, font_files, theme_css
from ankinote.note_types import build_specs
from ankinote.settings import Settings, load_settings, save_settings

PACKAGES = ["word", "phrase", "sentence", "stem"]


def _rules(package: str) -> str:
    return (
        files(f"ankinote.collections.{package}.card_templates")
        .joinpath("style.css")
        .read_text("utf-8")
    )


def _block(css: str, selector_start: str) -> str:
    start = css.index(selector_start)
    return css[start : css.index("}", start)]


def test_light_palette_on_card_and_dark_under_night_mode() -> None:
    css = theme_css(CardTheme(light="gruvbox", dark="rose-pine"))
    assert css.startswith("/* ankinote-style: 1.0 · light: gruvbox · dark: rose-pine")
    light = _block(css, ".card {")
    dark = _block(css, ".card.nightMode,")
    assert "--an-tile: #FBF1C7;" in light  # Gruvbox light
    assert "--an-tile: #1F1D2E;" in dark  # Rosé Pine dark
    # Anki desktop, AnkiDroid and AnkiMobile mark night mode differently.
    for selector in (".nightMode .card", ".night_mode .card", ".card.night_mode"):
        assert selector in css


def test_unknown_palette_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown palette"):
        CardTheme(light="solarized", dark="kanagawa")


@pytest.mark.parametrize("package", PACKAGES)
def test_card_css_uses_only_theme_tokens(package: str) -> None:
    rules = _rules(package)
    used = set(re.findall(r"var\(--an-([a-z0-9-]+)\)", rules))
    defined = set(
        re.findall(r"--an-([a-z0-9-]+):", theme_css(card_theme.default_theme()))
    )
    assert used, "the stylesheet should take its colours from the theme"
    assert used <= defined
    # Colours and fonts come from the theme, never from the stylesheet itself.
    hard_coded = re.findall(
        r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\bwhite\b(?!-)|\bblack\b|font-family:(?! var)",
        rules,
    )
    assert hard_coded == []


def test_every_font_the_css_names_ships() -> None:
    urls = re.findall(r'url\("([^"]+)"\)', theme_css(card_theme.default_theme()))
    assert urls and set(urls) == set(font_files())
    # A leading underscore keeps Anki's "Check media" from deleting them.
    assert all(name.startswith("_") for name in font_files())
    assert all(data[:4] == b"wOF2" for data in font_files().values())


def test_note_types_use_the_saved_theme() -> None:
    settings = load_settings()
    settings.card_theme_light, settings.card_theme_dark = "tokyo-night", "gruvbox"
    save_settings(settings)
    css = build_specs()[0].css
    assert css == compose(_rules("word"), CardTheme("tokyo-night", "gruvbox"))


def test_settings_keep_the_card_theme_and_drop_unknown_palettes() -> None:
    assert Settings().card_theme_light == card_theme.default_palette()
    settings = load_settings()
    settings.card_theme_light, settings.card_theme_dark = "rose-pine", "gone"
    save_settings(settings)
    loaded = load_settings()
    assert loaded.card_theme_light == "rose-pine"
    assert loaded.card_theme_dark == card_theme.default_palette()
