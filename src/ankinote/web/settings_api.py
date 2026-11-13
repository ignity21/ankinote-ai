"""Settings, model routes and "Test connection" endpoints.

Reads and writes the same ``settings.json`` the CLI and TUI use. API keys
are write-only: responses carry ``key_hint`` instead.
"""

from dataclasses import asdict
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ankinote.consts import (
    BETA_TARGET_LANGUAGES,
    NATIVE_LANGUAGES,
    TARGET_LANGUAGES,
    Language,
    language_pair_error,
)
from ankinote.model_presets import PRESETS, ROUTES, Route
from ankinote.model_routes import (
    InvalidDraftError,
    MissingKeyError,
    RouteDraft,
    apply_drafts,
    draft_to_profile,
    needs_setup,
    route_targets,
    route_view,
)
from ankinote.services import model_check
from ankinote.settings import Settings, load_settings, save_settings

UiLanguage = Literal["en", "zh-CN"]


class RouteIn(BaseModel):
    provider: str
    model: str = ""
    base_url: str = ""
    api_key: str | None = Field(
        default=None, description="Omit to keep the saved key for this provider."
    )

    def draft(self) -> RouteDraft:
        return RouteDraft(self.provider, self.model, self.base_url, self.api_key)


class RoutesIn(BaseModel):
    text: RouteIn
    image: RouteIn | None = None
    speech: RouteIn | None = None

    def drafts(self) -> dict[Route, RouteDraft | None]:
        return {
            route: None if (value := getattr(self, route)) is None else value.draft()
            for route in ROUTES
        }


class ListModelsIn(BaseModel):
    route: Route
    target: RouteIn


class SettingsPatch(BaseModel):
    ui_language: UiLanguage | None = None
    native_language: Language | None = None
    target_language: Language | None = None
    generate_image: bool | None = None


def _models(settings: Settings) -> dict:
    return {
        route: None if (view := route_view(settings, route)) is None else asdict(view)
        for route in ROUTES
    }


def _settings_out(settings: Settings) -> dict:
    return {
        "needs_setup": needs_setup(settings),
        "ui_language": settings.ui_language,
        "defaults": asdict(settings.defaults),
        "anki_backend": settings.anki_backend,
        "anki_collection_path": settings.anki_collection_path,
        "models": _models(settings),
    }


def _draft_error(exc: InvalidDraftError | MissingKeyError) -> HTTPException:
    code = "key_missing" if isinstance(exc, MissingKeyError) else "invalid"
    return HTTPException(
        status_code=422,
        detail={"code": code, "route": exc.route, "message": str(exc)},
    )


router = APIRouter(prefix="/api")


@router.get("/settings")
async def get_settings() -> dict:
    return _settings_out(load_settings())


@router.get("/languages")
async def languages() -> dict:
    """The native and target choices, and the saved pair."""
    defaults = load_settings().defaults
    return {
        "native": defaults.native_language,
        "target": defaults.target_language,
        "natives": [lang.value for lang in NATIVE_LANGUAGES],
        "targets": [
            {"id": lang.value, "beta": lang in BETA_TARGET_LANGUAGES}
            for lang in TARGET_LANGUAGES
        ],
    }


@router.patch("/settings")
async def patch_settings(patch: SettingsPatch) -> dict:
    settings = load_settings()
    if patch.native_language is not None or patch.target_language is not None:
        # Check the pair the patch leaves behind, including the saved half.
        native = patch.native_language or Language(settings.defaults.native_language)
        target = patch.target_language or Language(settings.defaults.target_language)
        if code := language_pair_error(native, target):
            raise HTTPException(
                422,
                detail={"code": code, "detail": f"{native} → {target}"},
            )
        settings.defaults.native_language = native.value
        settings.defaults.target_language = target.value
    if patch.generate_image is not None:
        settings.defaults.generate_image = patch.generate_image
    if patch.ui_language is not None:
        settings.ui_language = patch.ui_language
    save_settings(settings)
    return _settings_out(settings)


@router.get("/models/providers")
async def providers() -> list[dict]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "recommended": p.recommended,
            "models": p.models,
            "base_url": p.base_url,
            "key_url": p.key_url,
        }
        for p in PRESETS.values()
    ]


@router.put("/models")
async def put_models(routes: RoutesIn) -> dict:
    settings = load_settings()
    try:
        apply_drafts(settings, routes.drafts())
    except (InvalidDraftError, MissingKeyError) as exc:
        raise _draft_error(exc) from exc
    save_settings(settings)
    return _settings_out(settings)


@router.post("/models/test")
async def test_models(routes: RoutesIn) -> dict:
    settings = load_settings()
    try:
        targets = route_targets(settings, routes.drafts())
    except (InvalidDraftError, MissingKeyError) as exc:
        raise _draft_error(exc) from exc
    results = await model_check.check_routes(targets)
    return {route: asdict(result) for route, result in results.items()}


@router.post("/models/list")
async def list_models(body: ListModelsIn) -> dict:
    settings = load_settings()
    draft = body.target.draft()
    # The model doesn't matter for listing; any non-empty id validates.
    draft = RouteDraft(
        draft.provider, draft.model or "-", draft.base_url, draft.api_key
    )
    try:
        profile = draft_to_profile(settings, body.route, draft)
    except (InvalidDraftError, MissingKeyError) as exc:
        raise _draft_error(exc) from exc
    try:
        models = await model_check.list_route_models(
            body.route, draft.provider, profile
        )
    except (httpx.HTTPError, ValueError) as exc:
        failure = model_check.classify(exc, "")
        return {"models": [], "code": failure.code, "detail": failure.detail}
    return {"models": models, "code": "", "detail": ""}
