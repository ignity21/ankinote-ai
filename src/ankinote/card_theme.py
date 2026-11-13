"""Card themes: the app's palettes and IBM Plex Sans, applied to card CSS.

A theme is a light palette and a dark one, chosen separately. Each note
type's ``style.css`` only refers to ``--an-*`` tokens; :func:`compose` puts
the theme's values in front of it: light on ``.card``, dark where Anki marks
night mode, so every client switches with its own night mode setting.

The fonts ship as collection media (:func:`font_files`); the leading
underscore keeps Anki's "Check media" from deleting them as unused.
"""

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

STYLE_VERSION = "1.0"

_CJK = (
    '"PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Noto Sans SC", '
    '"Source Han Sans SC", "Microsoft YaHei"'
)
SANS = f'"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", {_CJK}, sans-serif'

# Collection media name -> packaged file, with the range each subset covers
# (as @fontsource ships them), so a card loads only what its text needs.
_FONTS = {
    400: {
        "latin": "ibm-plex-sans-latin-400-normal.woff2",
        "latin-ext": "ibm-plex-sans-latin-ext-400-normal.woff2",
    },
    600: {
        "latin": "ibm-plex-sans-latin-600-normal.woff2",
        "latin-ext": "ibm-plex-sans-latin-ext-600-normal.woff2",
    },
}
_RANGES = {
    "latin": (
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,"
        "U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,"
        "U+FEFF,U+FFFD"
    ),
    "latin-ext": (
        "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,"
        "U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,"
        "U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
    ),
}
MEDIA_PREFIX = "_ankinote-"


@cache
def _tokens() -> dict:
    text = files("ankinote.themes").joinpath("palettes.json").read_text("utf-8")
    return json.loads(text)


def palette_ids() -> list[str]:
    """The palettes a theme can use, in display order."""
    return list(_tokens()["palettes"])


def default_palette() -> str:
    return _tokens()["default"]


@dataclass(frozen=True, slots=True)
class CardTheme:
    light: str
    dark: str

    def __post_init__(self) -> None:
        for palette in (self.light, self.dark):
            if palette not in _tokens()["palettes"]:
                raise ValueError(f"Unknown palette: {palette}")


def default_theme() -> CardTheme:
    return CardTheme(default_palette(), default_palette())


def current_theme() -> CardTheme:
    """The theme saved in settings."""
    from ankinote.settings import load_settings

    settings = load_settings()
    return CardTheme(settings.card_theme_light, settings.card_theme_dark)


def font_files() -> dict[str, bytes]:
    """Collection media name -> font data, for every face the CSS declares."""
    package = files("ankinote.themes").joinpath("fonts")
    return {
        MEDIA_PREFIX + name: package.joinpath(name).read_bytes()
        for faces in _FONTS.values()
        for name in faces.values()
    }


def _font_faces() -> str:
    return "".join(
        "@font-face {\n"
        '  font-family: "IBM Plex Sans";\n'
        "  font-style: normal;\n"
        f"  font-weight: {weight};\n"
        "  font-display: swap;\n"
        f'  src: url("{MEDIA_PREFIX}{name}") format("woff2");\n'
        f"  unicode-range: {_RANGES[subset]};\n"
        "}\n"
        for weight, faces in _FONTS.items()
        for subset, name in faces.items()
    )


def _declarations(palette: str, mode: str) -> str:
    values = _tokens()["palettes"][palette][mode]
    return "".join(f"  --an-{role}: {values[role]};\n" for role in _tokens()["roles"])


def theme_css(theme: CardTheme) -> str:
    """The theme's part of a card's CSS: marker, fonts and tokens."""
    return (
        f"/* ankinote-style: {STYLE_VERSION} · light: {theme.light}"
        f" · dark: {theme.dark} */\n"
        f"{_font_faces()}\n"
        ".card {\n"
        f"  --an-sans: {SANS};\n"
        f"{_declarations(theme.light, 'light')}"
        "}\n\n"
        ".card.nightMode,\n.card.night_mode,\n.nightMode .card,\n.night_mode .card {\n"
        f"{_declarations(theme.dark, 'dark')}"
        "}\n"
    )


def compose(body_css: str, theme: CardTheme) -> str:
    """A note type's full CSS: the theme, then its own rules."""
    return f"{theme_css(theme)}\n{body_css}"


def preview_css(css: str, font_url: str) -> str:
    """Card CSS for the in-app preview, with the fonts served from ``font_url``."""
    return css.replace(f'url("{MEDIA_PREFIX}', f'url("{font_url}/{MEDIA_PREFIX}')
