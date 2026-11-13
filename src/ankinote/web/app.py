"""FastAPI app serving the JSON API and the built frontend.

The frontend lives in ``frontend/`` and builds into ``DIST_DIR``. In
development, run the Vite dev server instead; it proxies ``/api`` here.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from ankinote import __version__
from ankinote.services.anki_factory import stop_anki_backend
from ankinote.utils.httpcli import close_session, init_session
from ankinote.web import (
    anki_api,
    card_theme_api,
    cards_api,
    note_types_api,
    settings_api,
)

DIST_DIR = Path(__file__).parent / "dist"

_NOT_BUILT = (
    "The web frontend has not been built.\n"
    "From a source checkout, run `make web-build`, or use `make web-dev` "
    "while developing.\n"
)


def _api() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def unknown(path: str) -> Response:
        # Keep unknown API paths out of the SPA fallback below.
        return Response(
            content='{"detail":"Not Found"}',
            status_code=404,
            media_type="application/json",
        )

    return router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared HTTP session (AnkiConnect) and one Anki backend per process.
    init_session()
    await anki_api.start_backend()
    try:
        yield
    finally:
        await stop_anki_backend()
        await close_session()


def create_app(dist_dir: Path = DIST_DIR) -> FastAPI:
    app = FastAPI(
        title="ankinote", version=__version__, docs_url="/api/docs", lifespan=_lifespan
    )
    app.include_router(settings_api.router)
    app.include_router(anki_api.router)
    app.include_router(cards_api.router)
    app.include_router(note_types_api.router)
    app.include_router(card_theme_api.router)
    app.include_router(_api())

    index = dist_dir / "index.html"
    if (dist_dir / "assets").is_dir():
        # Vite fingerprints everything under assets/, so it may be cached.
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"))

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if not index.is_file():
            return PlainTextResponse(_NOT_BUILT, status_code=503)
        # Client-side routes all load the same page; never cache it so a new
        # build's asset names are picked up.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
