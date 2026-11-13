"""Render Anki card templates to HTML for the in-app preview.

Covers the template syntax ankinote's note types use: ``{{Field}}``,
``{{#Field}}…{{/Field}}``, ``{{^Field}}…{{/Field}}``, ``{{FrontSide}}``,
``{{type:Field}}`` and the ``text:`` filter. ``[sound:…]`` becomes Anki's
replay button (played by the preview page, which reads ``data-src``), and
media references point at ``media_url(name)``.
"""

import html
import re
from collections.abc import Callable, Mapping
from urllib.parse import quote

_SECTION = re.compile(r"\{\{([#^])\s*([^}]+?)\s*\}\}(.*?)\{\{/\s*\2\s*\}\}", re.DOTALL)
_TAG = re.compile(r"\{\{\s*([^#^/}][^}]*?)\s*\}\}")
_SOUND = re.compile(r"\[sound:([^\]]+)\]")
_IMG_SRC = re.compile(r"""(<img\b[^>]*?\bsrc=)(['"])([^'"]+)\2""", re.IGNORECASE)
# Anki's own test for an empty field: only whitespace, <br> and <div>.
_EMPTY = re.compile(r"^(?:\s|&nbsp;|</?(?:br|div)\s*/?>)*$", re.IGNORECASE)

# Anki's replay icon, so card CSS that styles `.replay-button svg` applies.
_PLAY_SVG = (
    '<svg class="playImage" viewBox="0 0 64 64" version="1.1" aria-hidden="true">'
    '<circle cx="32" cy="32" r="29"/>'
    '<path d="M56.502,32.301l-37.502,20.101l0.329,-40.804l37.173,20.703Z"/></svg>'
)


def _is_empty(value: str) -> bool:
    return bool(_EMPTY.match(value))


def render_card(
    template: str,
    fields: Mapping[str, str],
    *,
    media_url: Callable[[str], str],
    front_side: str = "",
    answer: bool = False,
) -> str:
    """One side of a card. For the back, pass the rendered front as ``front_side``."""

    def section(match: re.Match[str]) -> str:
        kind, name, body = match.groups()
        shown = not _is_empty(fields.get(name, ""))
        return body if shown == (kind == "#") else ""

    previous = None
    out = template
    while previous != out:  # inner sections first, then their parents
        previous, out = out, _SECTION.sub(section, out)

    def tag(match: re.Match[str]) -> str:
        *filters, name = [part.strip() for part in match.group(1).split(":")]
        if name == "FrontSide" and not filters:
            # The back repeats the question, minus its answer box.
            return re.sub(r'<input type="text" id="typeans"[^>]*>', "", front_side)
        if name not in fields:
            return f"<span class='preview-error'>{{{{{html.escape(name)}}}}}</span>"
        value = fields[name]
        if "type" in filters:
            if answer:
                return (
                    f'<code id="typeans"><span class="typeGood">{value}</span></code>'
                )
            return (
                '<input type="text" id="typeans" autocomplete="off" spellcheck="false">'
            )
        if "text" in filters:
            value = re.sub(r"<[^>]+>", "", value)
        return value

    out = _TAG.sub(tag, out)
    out = _SOUND.sub(
        lambda m: (
            '<a class="replay-button soundLink" href="#" '
            f'data-src="{html.escape(media_url(m.group(1)))}">{_PLAY_SVG}</a>'
        ),
        out,
    )
    return _IMG_SRC.sub(
        lambda m: (
            m.group(0)
            if re.match(r"^(?:[a-z]+:|/)", m.group(3))
            else f"{m.group(1)}{m.group(2)}{media_url(m.group(3))}{m.group(2)}"
        ),
        out,
    )


def media_path(prefix: str, name: str) -> str:
    """``prefix/name`` with the name URL-quoted."""
    return f"{prefix}/{quote(name)}"
