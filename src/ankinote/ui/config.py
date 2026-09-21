"""Configuration persistence for the GUI."""

import functools
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

from ankinote.config import envs

# Vendor templates — the ones the GUI offers directly in the "Add provider"
# dialog (autofills Base URL + drives model discovery/fetch heuristics for a
# new profile). Anything else is reached by picking ``CUSTOM_VENDOR`` instead.
#
# Model lists here are only a fallback: `get_provider_models` first pulls the
# provider's chat models from litellm's bundled catalog and uses these curated
# ids only when that lookup fails or turns up empty.
PROVIDERS: dict[str, dict] = {
    "OpenAI": {
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4.1"],
        "env_key": "OPENAI_API_KEY",
        "litellm_provider": "openai",
        "model_prefix": None,
        "api_base": "https://api.openai.com/v1",
    },
    "Anthropic": {
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250514",
        ],
        "env_key": "ANTHROPIC_API_KEY",
        "litellm_provider": "anthropic",
        "model_prefix": None,
        "api_base": "https://api.anthropic.com/v1",
    },
    "Gemini": {
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.5-pro-exp-03-25",
        ],
        "env_key": "GEMINI_API_KEY",
        "litellm_provider": "gemini",
        "model_prefix": "gemini/",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
    },
}

# Sentinel vendor for a user-supplied OpenAI-compatible endpoint (custom base
# URL + arbitrary model id), e.g. a local vLLM/Ollama/LM Studio server, a
# third-party OpenAI-compatible API, or a second account on a vendor not in
# ``PROVIDERS``/``IMAGE_PROVIDERS``. Offered alongside the curated vendors in
# the "Add provider" dialog for both text and image profiles.
CUSTOM_VENDOR = "Custom / Other"
CUSTOM_VENDOR_TEMPLATE: dict = {
    "models": [],
    "env_key": None,
    "litellm_provider": "openai",
    "model_prefix": None,
    "api_base": "",
}

# Substrings that disqualify an otherwise "chat" mode model from the
# picker — these variants require request shapes our generators don't send.
_EXCLUDED_NAME_SUBSTRINGS = ("-audio-", "-search-", "/container")


def _discover_models(
    litellm_provider: str, predicate: Callable[[str, dict], bool]
) -> tuple[str, ...]:
    """Filter litellm's bundled model catalog down to one provider's ids."""
    try:
        import litellm
    except ImportError:
        return ()

    models = [
        name
        for name, info in litellm.model_cost.items()
        if isinstance(info, dict)
        and info.get("litellm_provider") == litellm_provider
        and predicate(name, info)
    ]
    return tuple(sorted(models))


@functools.cache
def _discover_chat_models(
    litellm_provider: str, model_prefix: str | None
) -> tuple[str, ...]:
    """Pull the current chat-capable model ids for a provider from litellm's catalog."""

    def is_chat_model(name: str, info: dict) -> bool:
        return (
            info.get("mode") == "chat"
            and not name.startswith("ft:")
            and not any(sub in name for sub in _EXCLUDED_NAME_SUBSTRINGS)
            and (model_prefix is None or name.startswith(model_prefix))
        )

    return _discover_models(litellm_provider, is_chat_model)


def get_provider_models(provider: str) -> list[str]:
    """Return the current list of selectable chat model ids for a vendor."""
    info = PROVIDERS[provider]
    models = list(_discover_chat_models(info["litellm_provider"], info["model_prefix"]))
    return models or list(info["models"])


def _provider_request_headers_params(
    litellm_provider: str, api_key: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Build the auth headers/query params for a provider's model-list endpoint."""
    if litellm_provider == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, {
            "limit": "1000"
        }
    if litellm_provider in {"gemini", "vertex_ai"}:
        return {}, {"key": api_key, "pageSize": "1000"}
    return {"Authorization": f"Bearer {api_key}"}, {}


async def _fetch_models_payload(
    api_base: str, litellm_provider: str, api_key: str
) -> dict:
    """GET a provider's model-list endpoint and return the decoded JSON.

    Handles the OpenAI-compatible ``GET /models`` shape (OpenAI, DeepSeek,
    vLLM, LM Studio, …), Anthropic's ``/v1/models``, and Gemini's
    ``/v1beta/models``. Raises ``httpx`` errors when the request fails.
    """
    import httpx

    headers, params = _provider_request_headers_params(litellm_provider, api_key)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{api_base.rstrip('/')}/models", headers=headers, params=params or None
        )
        response.raise_for_status()
        return response.json()


def _prefixed_names(names: list[str], model_prefix: str | None) -> list[str]:
    """Ensure each id carries the prefix litellm expects (e.g. ``gemini/…``)."""
    prefix = model_prefix or ""
    return sorted(
        {name if name.startswith(prefix) else prefix + name for name in names if name}
    )


async def fetch_model_ids(
    *,
    litellm_provider: str,
    api_base: str,
    api_key: str,
    model_prefix: str | None = None,
) -> list[str]:
    """Ask a provider's HTTP API for the model ids it currently serves."""
    payload = await _fetch_models_payload(api_base, litellm_provider, api_key)

    if litellm_provider in {"gemini", "vertex_ai"}:
        names = [
            entry.get("name", "").removeprefix("models/")
            for entry in payload.get("models", [])
            if "generateContent" in entry.get("supportedGenerationMethods", [])
        ]
    else:
        names = [
            entry["id"]
            for entry in payload.get("data", [])
            if isinstance(entry, dict) and entry.get("id")
        ]

    return _prefixed_names(names, model_prefix)


def _gemini_image_names(entries: list[dict]) -> list[str]:
    """Prefer entries marked for image generation; else fall back to all."""
    has_filter = any(
        "imageGeneration" in entry.get("supportedGenerationMethods", [])
        for entry in entries
    )
    return [
        entry.get("name", "").removeprefix("models/")
        for entry in entries
        if not has_filter
        or "imageGeneration" in entry.get("supportedGenerationMethods", [])
    ]


def _openai_image_names(entries: list[dict]) -> list[str]:
    """Prefer dall-e/gpt-image ids when present; else fall back to all ids."""
    valid = [entry for entry in entries if isinstance(entry, dict) and entry.get("id")]
    has_filter = any(entry["id"].startswith(("dall-e", "gpt-image")) for entry in valid)
    return [
        entry["id"]
        for entry in valid
        if not has_filter or entry["id"].startswith(("dall-e", "gpt-image", "image"))
    ]


async def fetch_image_model_ids(
    *,
    litellm_provider: str,
    api_base: str,
    api_key: str,
    model_prefix: str | None = None,
) -> list[str]:
    """Ask a provider's HTTP API for image-generation model ids it serves.

    When a provider explicitly marks which models support image generation,
    only those are returned. Otherwise, all models are returned as a fallback.
    """
    if litellm_provider == "fal_ai":
        return await fetch_fal_image_model_ids(api_base=api_base, api_key=api_key)

    payload = await _fetch_models_payload(api_base, litellm_provider, api_key)
    if litellm_provider in {"gemini", "vertex_ai"}:
        names = _gemini_image_names(payload.get("models", []))
    else:
        names = _openai_image_names(payload.get("data", []))

    return _prefixed_names(names, model_prefix)


async def fetch_fal_image_model_ids(*, api_base: str, api_key: str) -> list[str]:
    """List active text-to-image endpoint IDs through Fal's Platform API.

    Fal's inference base (``https://fal.run``) is intentionally separate from
    this discovery base (``https://api.fal.ai/v1``). The API key is optional
    for this endpoint, although supplying it provides a higher rate limit.
    """
    import httpx

    headers = {"Authorization": f"Key {api_key}"} if api_key else {}
    params: dict[str, str] = {
        "category": "text-to-image",
        "status": "active",
        "limit": "100",
    }
    endpoint_ids: set[str] = set()
    cursor: str | None = None

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            if cursor is None:
                params.pop("cursor", None)
            else:
                params["cursor"] = cursor
            response = await client.get(
                f"{api_base.rstrip('/')}/models",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            models = payload.get("models", [])
            if not isinstance(models, list):
                raise TypeError("Fal model search returned an invalid models list")
            endpoint_ids.update(
                endpoint_id
                for entry in models
                if isinstance(entry, dict)
                and isinstance(
                    (endpoint_id := cast(dict[str, object], entry).get("endpoint_id")),
                    str,
                )
                and endpoint_id
            )
            next_cursor = payload.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            if next_cursor == cursor:
                raise ValueError("Fal model search returned a repeated cursor")
            cursor = next_cursor
    return sorted(endpoint_ids)


DEFAULT_IMAGE_MODELS: list[str] = [
    "gemini/gemini-3.1-flash-lite-image",
    "gemini/gemini-2.0-flash-exp-image",
    "gpt-image-1",
]

# Built-in image vendor templates, mirroring ``PROVIDERS``. Model lists are
# discovered live from litellm's catalog (see ``get_image_provider_models``);
# these are only the fallback when that lookup fails or turns up empty.
IMAGE_PROVIDERS: dict[str, dict] = {
    "OpenAI": {
        "models": ["gpt-image-1", "dall-e-3"],
        "env_key": "OPENAI_API_KEY",
        "litellm_provider": "openai",
        "model_prefix": None,
        "api_base": "https://api.openai.com/v1",
    },
    "Gemini": {
        "models": [
            "gemini/gemini-3.1-flash-lite-image",
            "gemini/gemini-2.5-flash-image",
            "gemini/imagen-3.0-generate-002",
        ],
        "env_key": "GEMINI_API_KEY",
        "litellm_provider": "gemini",
        "model_prefix": "gemini/",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
    },
    "Fal": {
        "models": ["fal_ai/fal-ai/flux/schnell"],
        "env_key": "FAL_AI_API_KEY",
        "litellm_provider": "fal_ai",
        "model_prefix": "fal_ai/",
        "api_base": "https://fal.run",
        "model_api_base": "https://api.fal.ai/v1",
    },
}

DEFAULT_IMAGE_PROVIDER = "Gemini"


@functools.cache
def _discover_image_models(
    litellm_provider: str, model_prefix: str | None
) -> tuple[str, ...]:
    """Pull the current image-generation model ids for a provider from litellm."""
    prefix = model_prefix or ""

    def is_image_model(name: str, info: dict) -> bool:
        # Drop litellm's size-/step-prefixed catalog variants
        # (e.g. "1024-x-1024/dall-e-2"). fal_ai's canonical model ids are
        # themselves slash-separated paths (e.g. "fal-ai/flux/schnell"), so
        # this "no nested slash" heuristic does not apply to it.
        return (
            info.get("mode") == "image_generation"
            and (model_prefix is None or name.startswith(model_prefix))
            and (litellm_provider == "fal_ai" or "/" not in name.removeprefix(prefix))
        )

    return _discover_models(litellm_provider, is_image_model)


def get_image_provider_models(provider: str) -> list[str]:
    """Return the selectable image model ids for a vendor.

    Curated defaults come first (they stay valid even if litellm's catalog
    lags), followed by any additional ids discovered in the catalog.
    """
    info = IMAGE_PROVIDERS[provider]
    discovered = _discover_image_models(info["litellm_provider"], info["model_prefix"])
    return list(dict.fromkeys([*info["models"], *discovered]))


def image_provider_for(model: str) -> str:
    """Return the :data:`IMAGE_PROVIDERS` key that owns an image model id.

    Matches by ``model_prefix`` first, then falls back to litellm's provider
    lookup, and finally to :data:`DEFAULT_IMAGE_PROVIDER` for unknown ids.
    """
    for name, info in IMAGE_PROVIDERS.items():
        prefix = info["model_prefix"]
        if prefix and model.startswith(prefix):
            return name
        if name == "Fal" and model.startswith("fal-ai/"):
            return name
    try:
        import litellm
    except ImportError:
        return DEFAULT_IMAGE_PROVIDER
    try:
        _, provider, _, _ = litellm.get_llm_provider(model)
    except litellm.exceptions.BadRequestError:
        return DEFAULT_IMAGE_PROVIDER
    for name, info in IMAGE_PROVIDERS.items():
        if info["litellm_provider"] == provider:
            return name
    return DEFAULT_IMAGE_PROVIDER


@dataclass
class DefaultsConfig:
    native_language: str = "Chinese(Simplified)"
    target_language: str = "English"
    generate_image: bool = True


@dataclass
class ProviderProfile:
    """One independently-configured provider profile.

    Every profile — whether created from a curated vendor template or as a
    fully custom endpoint (``vendor == CUSTOM_VENDOR``) — carries its own
    model, base URL, and API key, so multiple accounts of the same vendor can
    coexist and are each used explicitly at generation time (no shared
    env-var indirection).
    """

    vendor: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""


DEFAULT_TEXT_PROFILE_NAME = "OpenAI"
DEFAULT_IMAGE_PROFILE_NAME = "Gemini"


def _default_text_providers() -> dict[str, ProviderProfile]:
    info = PROVIDERS[DEFAULT_TEXT_PROFILE_NAME]
    return {
        DEFAULT_TEXT_PROFILE_NAME: ProviderProfile(
            vendor=DEFAULT_TEXT_PROFILE_NAME,
            model=info["models"][0],
            base_url=info["api_base"],
        )
    }


def _default_image_providers() -> dict[str, ProviderProfile]:
    info = IMAGE_PROVIDERS[DEFAULT_IMAGE_PROFILE_NAME]
    return {
        DEFAULT_IMAGE_PROFILE_NAME: ProviderProfile(
            vendor=DEFAULT_IMAGE_PROFILE_NAME,
            model=info["models"][0],
            base_url=info["api_base"],
        )
    }


def unique_name(base: str, taken: set[str]) -> str:
    """Return ``base``, or ``base`` with a disambiguating suffix if taken."""
    if base not in taken:
        return base
    n = 2
    while f"{base} ({n})" in taken:
        n += 1
    return f"{base} ({n})"


@dataclass
class Settings:
    text_providers: dict[str, ProviderProfile] = field(
        default_factory=_default_text_providers
    )
    active_text_provider: str = DEFAULT_TEXT_PROFILE_NAME
    image_providers: dict[str, ProviderProfile] = field(
        default_factory=_default_image_providers
    )
    active_image_provider: str = DEFAULT_IMAGE_PROFILE_NAME
    image_size: int = 512
    api_keys: dict[str, str] = field(default_factory=dict)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    ui_language: str = "en"


def _get_config_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"
    return base / "ankinote"


def _get_config_path() -> Path:
    return _get_config_dir() / "settings.json"


def _parse_profiles(raw: dict) -> dict[str, ProviderProfile]:
    return {
        name: ProviderProfile(
            vendor=value.get("vendor", ""),
            model=value.get("model", ""),
            base_url=value.get("base_url", ""),
            api_key=value.get("api_key", ""),
        )
        for name, value in raw.items()
        if isinstance(name, str) and isinstance(value, dict)
    }


def _settings_from_current_shape(data: dict) -> Settings:
    """Parse a settings.json already in the multi-profile shape."""
    text_providers = _parse_profiles(data.get("text_providers", {}))
    image_providers = _parse_profiles(data.get("image_providers", {}))
    return Settings(
        text_providers=text_providers or _default_text_providers(),
        active_text_provider=data.get("active_text_provider")
        or next(iter(text_providers), DEFAULT_TEXT_PROFILE_NAME),
        image_providers=image_providers or _default_image_providers(),
        active_image_provider=data.get("active_image_provider")
        or next(iter(image_providers), DEFAULT_IMAGE_PROFILE_NAME),
        image_size=data.get("image_size", 512),
        api_keys=data.get("api_keys", {}),
        defaults=DefaultsConfig(**data.get("defaults", {})),
        ui_language=data.get("ui_language", "en"),
    )


# Literals from the pre-profile settings.json shape, kept only so an old
# config file can still be recognized and migrated on first load.
_LEGACY_CUSTOM_PROVIDER = "Custom (OpenAI-compatible)"
_LEGACY_CUSTOM_API_KEY_STORAGE_KEY = "CUSTOM_API_KEY"


def _settings_from_legacy_shape(data: dict) -> Settings:
    """Migrate a pre-profile settings.json into the multi-profile shape.

    The old shape had a single active ``provider``/``text_model`` (plus an
    optional flat ``custom_providers`` dict of named custom endpoints) and a
    single active ``image_provider``/``image_model`` — each becomes one
    ``ProviderProfile`` here.
    """
    old_api_keys: dict = data.get("api_keys", {})
    old_custom_providers: dict = data.get("custom_providers", {})
    old_provider = data.get("provider", "OpenAI")
    old_text_model = data.get("text_model", "gpt-4o")

    text_providers: dict[str, ProviderProfile] = {}
    taken: set[str] = set()
    active_text_provider = ""

    if old_provider in PROVIDERS:
        info = PROVIDERS[old_provider]
        name = unique_name(old_provider, taken)
        taken.add(name)
        text_providers[name] = ProviderProfile(
            vendor=old_provider,
            model=old_text_model,
            base_url=info["api_base"],
            api_key=old_api_keys.get(info["env_key"], ""),
        )
        active_text_provider = name
    elif old_provider not in old_custom_providers:
        # The legacy single-custom-provider sentinel, or an unrecognized
        # provider string with no matching named profile.
        base_name = (
            "Custom"
            if old_provider in ("", _LEGACY_CUSTOM_PROVIDER)
            else str(old_provider)
        )
        name = unique_name(base_name, taken)
        taken.add(name)
        text_providers[name] = ProviderProfile(
            vendor=CUSTOM_VENDOR,
            model=old_text_model,
            base_url=data.get("custom_base_url", ""),
            api_key=old_api_keys.get(_LEGACY_CUSTOM_API_KEY_STORAGE_KEY, ""),
        )
        active_text_provider = name
    # else: old_provider names an entry in old_custom_providers, handled below.

    for cname, cvalue in old_custom_providers.items():
        if not isinstance(cname, str) or not isinstance(cvalue, dict):
            continue
        name = unique_name(cname, taken)
        taken.add(name)
        text_providers[name] = ProviderProfile(
            vendor=CUSTOM_VENDOR,
            model=cvalue.get("model", ""),
            base_url=cvalue.get("base_url", ""),
            api_key=cvalue.get("api_key", ""),
        )
        if cname == old_provider:
            active_text_provider = name

    old_image_model = data.get("image_model", "gemini/gemini-3.1-flash-lite-image")
    old_image_provider = data.get("image_provider") or image_provider_for(
        old_image_model
    )
    image_providers: dict[str, ProviderProfile] = {}
    active_image_provider = ""
    if old_image_provider in IMAGE_PROVIDERS:
        iinfo = IMAGE_PROVIDERS[old_image_provider]
        image_providers[old_image_provider] = ProviderProfile(
            vendor=old_image_provider,
            model=old_image_model,
            base_url=iinfo["api_base"],
            api_key=old_api_keys.get(iinfo["env_key"], ""),
        )
        active_image_provider = old_image_provider

    return Settings(
        text_providers=text_providers or _default_text_providers(),
        active_text_provider=active_text_provider
        or next(iter(text_providers), DEFAULT_TEXT_PROFILE_NAME),
        image_providers=image_providers or _default_image_providers(),
        active_image_provider=active_image_provider
        or next(iter(image_providers), DEFAULT_IMAGE_PROFILE_NAME),
        image_size=data.get("image_size", 512),
        api_keys={"GOOGLE_TTS_KEY": old_api_keys.get("GOOGLE_TTS_KEY", "")},
        defaults=DefaultsConfig(**data.get("defaults", {})),
        ui_language=data.get("ui_language", "en"),
    )


def load_settings() -> Settings:
    """Load settings from ~/.config/ankinote/settings.json.

    Transparently migrates a pre-profile settings.json (one active provider
    per kind, plus a flat ``custom_providers`` dict) into the current
    multi-profile shape. The file is rewritten in the new shape on next save.
    """
    path = _get_config_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "text_providers" in data:
            return _settings_from_current_shape(data)
        return _settings_from_legacy_shape(data)
    except json.JSONDecodeError, KeyError, TypeError:
        return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to ~/.config/ankinote/settings.json."""
    config_dir = _get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "text_providers": {
            name: asdict(profile) for name, profile in settings.text_providers.items()
        },
        "active_text_provider": settings.active_text_provider,
        "image_providers": {
            name: asdict(profile) for name, profile in settings.image_providers.items()
        },
        "active_image_provider": settings.active_image_provider,
        "image_size": settings.image_size,
        "api_keys": settings.api_keys,
        "defaults": asdict(settings.defaults),
        "ui_language": settings.ui_language,
    }
    path = _get_config_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply_env(settings: Settings) -> None:
    """Push the Google TTS API key into the running process.

    Provider-profile keys are now passed explicitly to each LiteLLM service
    call (see ``ProviderProfile``) rather than resolved via env-var
    indirection, so this only concerns the separate Google Cloud TTS
    integration.

    ``envs`` is a singleton whose attributes are bound once at import time, so
    updating only ``os.environ`` would leave a key entered in the UI (or pulled
    in via config import) invisible to :mod:`ankinote.services.tts`. Keep both
    in sync.
    """
    key = settings.api_keys.get("GOOGLE_TTS_KEY", "")
    if key:
        os.environ["GOOGLE_TTS_KEY"] = key
        envs.GOOGLE_TTS_KEY = key
