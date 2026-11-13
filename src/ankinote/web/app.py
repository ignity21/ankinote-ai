"""FastAPI app serving the JSON API and the built frontend.

The frontend lives in ``frontend/`` and builds into ``DIST_DIR``. In
development, run the Vite dev server instead; it proxies ``/api`` here.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from ankinote import __version__
from ankinote.web import settings_api

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


def create_app(dist_dir: Path = DIST_DIR) -> FastAPI:
    app = FastAPI(title="ankinote", version=__version__, docs_url="/api/docs")
    app.include_router(settings_api.router)
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
