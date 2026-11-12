"""Palette tokens are shared by the web UI and the card CSS; keep them legible."""

import json
from pathlib import Path

import pytest

import ankinote

PALETTES = json.loads(
    (Path(ankinote.__file__).parent / "themes" / "palettes.json").read_text()
)
TEXT_ROLES = ["fg", "muted", "accent", "accent2", "ok", "warn", "err"]
VARIANTS = [(pid, mode) for pid in PALETTES["palettes"] for mode in ("light", "dark")]


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_default_palette_exists() -> None:
    assert PALETTES["default"] in PALETTES["palettes"]


@pytest.mark.parametrize(("pid", "mode"), VARIANTS)
def test_every_variant_defines_every_role(pid: str, mode: str) -> None:
    assert set(PALETTES["palettes"][pid][mode]) == set(PALETTES["roles"])


@pytest.mark.parametrize(("pid", "mode"), VARIANTS)
def test_text_roles_meet_wcag_aa(pid: str, mode: str) -> None:
    tokens = PALETTES["palettes"][pid][mode]
    failing = {
        role: round(_contrast(tokens[role], tokens["tile"]), 2)
        for role in TEXT_ROLES
        if _contrast(tokens[role], tokens["tile"]) < 4.5
    }
    if _contrast(tokens["on-accent"], tokens["accent"]) < 4.5:
        failing["on-accent"] = round(
            _contrast(tokens["on-accent"], tokens["accent"]), 2
        )
    assert not failing
