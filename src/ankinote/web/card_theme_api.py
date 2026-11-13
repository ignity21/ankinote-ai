"""The card theme: which palettes the cards use in Anki's day and night modes.

Saving a theme also restyles the note types that already exist in Anki (CSS
only: no fields or card templates are added). When Anki can't be reached
the theme is still saved, and the Note types page shows the styling update
as pending until it can.
"""

from fastapi import APIRouter, HTTPException, Response
from loguru import logger
from pydantic import BaseModel

from ankinote import card_theme
from ankinote.card_theme import CardTheme
from ankinote.note_types import build_specs, restyle
from ankinote.services.anki_batch import anki_write_batch
from ankinote.services.anki_factory import create_anki_client
from ankinote.settings import load_settings, save_settings
from ankinote.web import anki_api

router = APIRouter(prefix="/api/card-theme")


class ThemeIn(BaseModel):
    light: str
    dark: str


def _out(theme: CardTheme) -> dict:
    return {"light": theme.light, "dark": theme.dark}


@router.get("")
async def get_theme() -> dict:
    return {**_out(card_theme.current_theme()), "palettes": card_theme.palette_ids()}


@router.put("")
async def put_theme(body: ThemeIn) -> dict:
    """Save the theme, then restyle the note types Anki has.

    ``restyled`` lists the keys of the note types now in the new style;
    ``anki`` is null, or why Anki couldn't be restyled (the theme is saved
    either way).
    """
    try:
        theme = CardTheme(body.light, body.dark)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "unknown_palette"}) from exc
    settings = load_settings()
    settings.card_theme_light, settings.card_theme_dark = theme.light, theme.dark
    save_settings(settings)

    restyled: list[str] = []
    failure = None
    try:
        await anki_api.ready_backend()
        client = create_anki_client()
        # One batch: one AnkiWeb sync for every note type.
        async with anki_write_batch(client):
            restyled = await restyle(client, build_specs(theme))
    except HTTPException as exc:
        failure = exc.detail
    except Exception as exc:
        failure = anki_api.note_type_error(exc).detail
    if failure:
        logger.info(f"Card theme saved; Anki not restyled: {failure}")
    return {**_out(theme), "restyled": restyled, "anki": failure}


_FONTS = card_theme.font_files()


@router.get("/fonts/{name}")
async def font(name: str) -> Response:
    """A card font, for the in-app preview (Anki has them as media)."""
    if name not in _FONTS:
        raise HTTPException(404)
    return Response(
        _FONTS[name],
        media_type="font/woff2",
        # The preview frame is sandboxed (origin "null"); fonts load with CORS.
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )
