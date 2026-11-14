"""The card theme API: save a theme, restyle what Anki has, preview it."""

from typing import Any

import httpx
import pytest

from ankinote.card_theme import font_files
from ankinote.config import envs
from ankinote.services.anki_factory import get_shared_runtime
from tests.web.anki_fakes import builtin, login


async def test_default_theme_is_the_default_palette(api: httpx.AsyncClient) -> None:
    body = (await api.get("/api/card-theme")).json()
    assert (body["light"], body["dark"]) == ("rose-pine", "rose-pine")
    assert body["palettes"] == ["kanagawa", "tokyo-night", "gruvbox", "rose-pine"]


async def test_restyles_only_the_note_types_anki_has(
    api: httpx.AsyncClient, ankiweb: dict[str, Any]
) -> None:
    await builtin(api)
    await login(api)
    created = await api.post("/api/anki/note-types/word")
    assert created.json()["result"] == "created"

    response = await api.put(
        "/api/card-theme", json={"light": "gruvbox", "dark": "rose-pine"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restyled"] == ["word"]
    assert body["anki"] is None

    status = {i["key"]: i for i in (await api.get("/api/anki/note-types")).json()}
    assert status["word"]["state"] == "synced"  # Anki has the new CSS
    # Restyling never creates a note type (or adds cards to one).
    assert status["phrase"]["state"] == "missing"

    runtime = get_shared_runtime()
    assert runtime is not None
    have = await runtime.submit(
        lambda col: [col.media.have(name) for name in font_files()]
    )
    assert all(have)


async def test_theme_is_saved_while_anki_is_unreachable(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(envs, "ANKI_BACKEND", "connect")
    monkeypatch.setattr(envs, "ANKI_CONNECT_URL", "http://127.0.0.1:9")
    response = await api.put(
        "/api/card-theme", json={"light": "tokyo-night", "dark": "gruvbox"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["restyled"] == []
    assert response.json()["anki"]["code"] == "unreachable"
    saved = (await api.get("/api/card-theme")).json()
    assert (saved["light"], saved["dark"]) == ("tokyo-night", "gruvbox")


async def test_unknown_palette_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.put(
        "/api/card-theme", json={"light": "solarized", "dark": "kanagawa"}
    )
    assert response.status_code == 422
    assert (await api.get("/api/card-theme")).json()["light"] == "rose-pine"


async def test_sample_previews_a_theme_before_it_is_saved(
    api: httpx.AsyncClient,
) -> None:
    saved = (await api.get("/api/note-types/word/sample")).json()["css"]
    preview = (await api.get("/api/note-types/word/sample?light=gruvbox")).json()
    assert "light: rose-pine" in saved
    assert "light: gruvbox · dark: rose-pine" in preview["css"]
    assert (
        preview["cards"]
        == (await api.get("/api/note-types/word/sample")).json()["cards"]
    )
    # The preview frame loads the fonts from the app, not from Anki's media.
    assert 'url("/api/card-theme/fonts/_ankinote-' in preview["css"]
    bad = await api.get("/api/note-types/word/sample?dark=solarized")
    assert bad.status_code == 422


async def test_fonts_are_served_for_the_preview(api: httpx.AsyncClient) -> None:
    name = next(iter(font_files()))
    response = await api.get(f"/api/card-theme/fonts/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"
    assert response.content == font_files()[name]
    # The preview frame is sandboxed (origin "null"), and fonts load with CORS.
    assert response.headers["access-control-allow-origin"] == "*"
    assert (await api.get("/api/card-theme/fonts/nope.woff2")).status_code == 404
