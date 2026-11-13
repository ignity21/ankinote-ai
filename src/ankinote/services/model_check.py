"""Check that a provider key works, and list the models it can use.

"Test connection" in the wizard and in Settings → Models runs one check per
route, concurrently:

- text: a real, tiny chat completion, so the result covers the key, the
  model id, billing and quota;
- image and speech: the model must appear in the provider's model list for
  this key (for Google Cloud TTS: a voice of that family must exist). That
  costs nothing, unlike generating an image, but cannot catch a model the
  account has no quota for, e.g. Gemini images on the free tier.

Failures are reported as a ``code`` the frontend turns into a sentence, plus
the provider's own message as ``detail``.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

import httpx
from litellm import exceptions as llm_errors

from ankinote.model_presets import CUSTOM_PRESET, PRESETS, Route
from ankinote.services.ai import DISABLE_REASONING, GenerationTimeoutError
from ankinote.services.provider_factory import build_text_service
from ankinote.settings import ProviderProfile, fetch_fal_image_model_ids

CHECK_TIMEOUT_SECONDS = 30
_DETAIL_LIMIT = 300
# Fal serves models from fal.run but lists them here.
FAL_MODELS_BASE = "https://api.fal.ai/v1"

type Status = Literal["ok", "failed", "unverified", "off"]
type Checked = Literal["generated", "listed", ""]
type FailureCode = Literal[
    "",
    "auth",
    "api_disabled",
    "billing",
    "model_not_found",
    "quota",
    "timeout",
    "unreachable",
    "cannot_list",
    "error",
]


@dataclass(frozen=True, slots=True)
class RouteCheck:
    """Outcome of checking one route."""

    status: Status
    model: str = ""
    checked: Checked = ""
    code: FailureCode = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RouteTarget:
    """A route to check: which preset serves it, and the profile to use."""

    preset: str
    profile: ProviderProfile


OFF = RouteCheck(status="off")


def _short(text: str) -> str:
    # Drop LiteLLM's "litellm.AuthenticationError: " style prefixes.
    text = re.sub(r"^(litellm\.\w+:\s*)+", "", " ".join(text.split()))
    return text if len(text) <= _DETAIL_LIMIT else text[: _DETAIL_LIMIT - 1] + "…"


def _looks_like_bad_key(message: str) -> bool:
    # Gemini answers an invalid key with 400 INVALID_ARGUMENT, not 401.
    lowered = message.lower()
    return "api key not valid" in lowered or "api_key_invalid" in lowered


def _api_disabled(message: str) -> bool:
    # Google: the key's project has not enabled this API.
    lowered = message.lower()
    return "service_disabled" in lowered or "has not been used in project" in lowered


def _needs_billing(message: str) -> bool:
    # Gemini's free tier has a zero quota for some models (images).
    lowered = message.lower()
    return "free_tier" in lowered and "limit: 0" in lowered


def _failure(model: str, code: FailureCode, detail: str = "") -> RouteCheck:
    return RouteCheck(status="failed", model=model, code=code, detail=_short(detail))


_TIMEOUTS = (
    TimeoutError,
    GenerationTimeoutError,
    llm_errors.Timeout,
    httpx.TimeoutException,
)
_BY_TYPE: tuple[
    tuple[type[BaseException] | tuple[type[BaseException], ...], FailureCode], ...
] = (
    ((llm_errors.AuthenticationError, llm_errors.PermissionDeniedError), "auth"),
    (llm_errors.NotFoundError, "model_not_found"),
    (llm_errors.RateLimitError, "quota"),
    ((llm_errors.APIConnectionError, httpx.TransportError), "unreachable"),
)
_BY_STATUS: dict[int, FailureCode] = {401: "auth", 403: "auth", 429: "quota"}


def _code_from_message(message: str) -> FailureCode:
    if _api_disabled(message):
        return "api_disabled"
    if _needs_billing(message):
        return "billing"
    if _looks_like_bad_key(message):
        return "auth"
    return ""


def classify(exc: BaseException, model: str) -> RouteCheck:
    """Map a provider or network error to a failure code."""
    if isinstance(exc, _TIMEOUTS):
        return _failure(model, "timeout")
    status: int | None = getattr(exc, "status_code", None)
    message = str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        status, message = exc.response.status_code, exc.response.text
    # The message is more specific than the type: Gemini sends a bad key as
    # 400, a disabled API as 403 and a free-tier zero quota as 429.
    if code := _code_from_message(message):
        return _failure(model, code, message)
    for types, code in _BY_TYPE:
        if isinstance(exc, types):
            return _failure(model, code, message)
    if isinstance(status, int) and status in _BY_STATUS:
        return _failure(model, _BY_STATUS[status], message)
    if isinstance(exc, httpx.HTTPStatusError):
        return _failure(model, "error", f"HTTP {status}: {message}")
    return _failure(model, "error", message or type(exc).__name__)


async def check_text(profile: ProviderProfile) -> RouteCheck:
    """Send a one-word prompt and expect any answer back."""
    service = build_text_service(profile)
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await service.generate_text(
                model=profile.model,
                messages=[{"role": "user", "content": "Reply with the word OK."}],
                temperature=0,
                reasoning_effort=DISABLE_REASONING,
            )
    except Exception as exc:
        return classify(exc, profile.model)
    return RouteCheck(status="ok", model=profile.model, checked="generated")


def _list_url_and_auth(
    preset_id: str, profile: ProviderProfile
) -> tuple[str, dict[str, str], dict[str, str]]:
    provider = PRESETS[preset_id].litellm_provider
    base = profile.base_url.rstrip("/")
    key = profile.api_key
    if preset_id == "google_tts":
        return f"{base}/voices", {}, {"key": key}
    if provider == "gemini":
        return f"{base}/models", {}, {"key": key, "pageSize": "1000"}
    if provider == "anthropic":
        return (
            f"{base}/models",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"limit": "1000"},
        )
    return f"{base}/models", {"Authorization": f"Bearer {key}"}, {}


async def fetch_model_list(preset_id: str, profile: ProviderProfile) -> list[dict]:
    """Return the raw model entries the provider lists for this key."""
    url, headers, params = _list_url_and_auth(preset_id, profile)
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers=headers, params=params or None)
        response.raise_for_status()
        payload = response.json()
    entries = payload.get("models") or payload.get("data") or payload.get("voices")
    return [entry for entry in entries or [] if isinstance(entry, dict)]


def _entry_id(entry: dict) -> str:
    raw = entry.get("id") or entry.get("name") or ""
    return str(raw).removeprefix("models/")


def _voice_family(name: str) -> str:
    """``en-US-Chirp3-HD-Aoede`` → ``Chirp3-HD``; ``""`` for other names."""
    parts = name.split("-")
    return "-".join(parts[2:-1]) if len(parts) >= 4 else ""


async def fetch_model_ids(
    route: Route, preset_id: str, profile: ProviderProfile
) -> list[str]:
    """Bare ids of the models this key can use (voice families for Google TTS)."""
    if preset_id == "fal":
        return await fetch_fal_image_model_ids(
            api_base=FAL_MODELS_BASE, api_key=profile.api_key
        )
    entries = await fetch_model_list(preset_id, profile)
    if preset_id == "google_tts":
        families = {_voice_family(str(entry.get("name", ""))) for entry in entries}
        return sorted(family for family in families if family)
    if PRESETS[preset_id].litellm_provider == "gemini" and route != "speech":
        # Speech models are served by the Interactions API instead.
        entries = [
            entry
            for entry in entries
            if "generateContent" in entry.get("supportedGenerationMethods", [])
        ]
    return [model_id for entry in entries if (model_id := _entry_id(entry))]


def _bare(model: str, preset_id: str) -> str:
    return model.removeprefix(PRESETS[preset_id].model_prefix).removeprefix("openai/")


async def check_listed(
    route: Route, preset_id: str, profile: ProviderProfile
) -> RouteCheck:
    """Check that the provider lists ``profile.model`` for this key."""
    model = profile.model
    try:
        ids = set(await fetch_model_ids(route, preset_id, profile))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and preset_id == CUSTOM_PRESET:
            # Plenty of OpenAI-compatible servers have no /models endpoint.
            return RouteCheck(status="unverified", model=model, code="cannot_list")
        return classify(exc, model)
    except Exception as exc:
        return classify(exc, model)
    if _bare(model, preset_id) not in ids:
        return _failure(model, "model_not_found")
    return RouteCheck(status="ok", model=model, checked="listed")


async def check_route(route: Route, target: RouteTarget | None) -> RouteCheck:
    """Check one route; ``None`` means the route is off."""
    if target is None:
        return OFF
    if not target.profile.model:
        return _failure("", "model_not_found")
    if route == "text":
        return await check_text(target.profile)
    return await check_listed(route, target.preset, target.profile)


async def check_routes(
    targets: dict[Route, RouteTarget | None],
) -> dict[Route, RouteCheck]:
    """Check every route concurrently."""
    routes = list(targets)
    results = await asyncio.gather(
        *(check_route(route, targets[route]) for route in routes)
    )
    return dict(zip(routes, results, strict=True))


# Words that mark a model as serving something other than the route asked
# about. Lists are only suggestions; the model field stays free text.
_NOT_TEXT = (
    "image",
    "tts",
    "audio",
    "embed",
    "live",
    "realtime",
    "transcribe",
    "whisper",
    "dall-e",
    "moderation",
    "search",
    "imagen",
    "veo",
    "aqa",
)


def _serves(route: Route, model_id: str, preset_id: str) -> bool:
    lowered = model_id.lower()
    if preset_id in {CUSTOM_PRESET, "deepseek", "anthropic", "fal", "google_tts"}:
        # Single-purpose lists, or ids that say nothing about the route.
        return True
    if route == "image":
        return "image" in lowered or "dall-e" in lowered
    if route == "speech":
        return "tts" in lowered
    return not any(word in lowered for word in _NOT_TEXT)


async def list_route_models(
    route: Route, preset_id: str, profile: ProviderProfile
) -> list[str]:
    """Model ids this key can use for ``route``, recommended one first."""
    preset = PRESETS[preset_id]
    ids = await fetch_model_ids(route, preset_id, profile)
    found = sorted(
        preset.model_prefix + model_id
        for model_id in ids
        if _serves(route, model_id, preset_id)
    )
    recommended = preset.models.get(route)
    if recommended:
        found = [recommended, *(model for model in found if model != recommended)]
    return found
