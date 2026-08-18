"""Configuration persistence for the GUI."""

import functools
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Built-in LLM provider definitions.
# Model lists are discovered live from litellm's bundled model catalog
# (see `get_provider_models`) — these are only used as a fallback if that
# lookup fails or turns up empty.
PROVIDERS: dict[str, dict] = {
    "OpenAI": {
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4.1"],
        "env_key": "OPENAI_API_KEY",
        "litellm_provider": "openai",
        "model_prefix": None,
    },
    "Anthropic": {
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250514",
        ],
        "env_key": "ANTHROPIC_API_KEY",
        "litellm_provider": "anthropic",
        "model_prefix": None,
    },
    "Google": {
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.5-pro-exp-03-25",
        ],
        "env_key": "GEMINI_API_KEY",
        "litellm_provider": "gemini",
        "model_prefix": "gemini/",
    },
    "DeepSeek": {
        "models": ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"],
        "env_key": "DEEPSEEK_API_KEY",
        "litellm_provider": "deepseek",
        "model_prefix": "deepseek/",
    },
}

# Sentinel provider name for a user-supplied OpenAI-compatible endpoint
# (custom base URL + arbitrary model id), e.g. a local vLLM/Ollama/LM Studio
# server or a third-party OpenAI-compatible API.
CUSTOM_PROVIDER = "Custom (OpenAI-compatible)"
CUSTOM_API_KEY_STORAGE_KEY = "CUSTOM_API_KEY"

# Substrings that disqualify an otherwise "chat" mode model from the
# picker — these variants require request shapes our generators don't send.
_EXCLUDED_NAME_SUBSTRINGS = ("-audio-", "-search-", "/container")


@functools.lru_cache(maxsize=None)
def _discover_chat_models(litellm_provider: str, model_prefix: str | None) -> tuple[str, ...]:
    """Pull the current chat-capable model ids for a provider from litellm's catalog."""
    try:
        import litellm
    except ImportError:
        return ()

    models: list[str] = []
    for name, info in litellm.model_cost.items():
        if not isinstance(info, dict):
            continue
        if info.get("litellm_provider") != litellm_provider:
            continue
        if info.get("mode") != "chat":
            continue
        if name.startswith("ft:"):
            continue
        if any(sub in name for sub in _EXCLUDED_NAME_SUBSTRINGS):
            continue
        if model_prefix is not None and not name.startswith(model_prefix):
            continue
        models.append(name)
    return tuple(sorted(models))


def get_provider_models(provider: str) -> list[str]:
    """Return the current list of selectable chat model ids for a provider."""
    info = PROVIDERS[provider]
    models = list(_discover_chat_models(info["litellm_provider"], info["model_prefix"]))
    return models or list(info["models"])


DEFAULT_IMAGE_MODELS: list[str] = [
    "gemini/gemini-3.1-flash-lite-image",
    "gemini/gemini-2.0-flash-exp-image",
]


@dataclass
class DefaultsConfig:
    native_language: str = "Chinese(Simplified)"
    target_language: str = "English"
    generate_image: bool = True


@dataclass
class Settings:
    provider: str = "OpenAI"
    text_model: str = "gpt-4o"
    image_model: str = "gemini/gemini-3.1-flash-lite-image"
    image_size: int = 512
    custom_base_url: str = ""
    api_keys: dict[str, str] = field(default_factory=dict)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


def _get_config_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"
    return base / "ankinote"


def _get_config_path() -> Path:
    return _get_config_dir() / "settings.json"


def load_settings() -> Settings:
    """Load settings from ~/.config/ankinote/settings.json."""
    path = _get_config_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults_data = data.get("defaults", {})
        defaults = DefaultsConfig(**defaults_data)
        return Settings(
            provider=data.get("provider", "OpenAI"),
            text_model=data.get("text_model", "gpt-4o"),
            image_model=data.get("image_model", "gemini/gemini-3.1-flash-lite-image"),
            image_size=data.get("image_size", 512),
            custom_base_url=data.get("custom_base_url", ""),
            api_keys=data.get("api_keys", {}),
            defaults=defaults,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to ~/.config/ankinote/settings.json."""
    config_dir = _get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "provider": settings.provider,
        "text_model": settings.text_model,
        "image_model": settings.image_model,
        "image_size": settings.image_size,
        "custom_base_url": settings.custom_base_url,
        "api_keys": settings.api_keys,
        "defaults": asdict(settings.defaults),
    }
    path = _get_config_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply_env(settings: Settings) -> None:
    """Set API keys from settings into os.environ (for litellm / Google TTS)."""
    for key, value in settings.api_keys.items():
        if value:
            os.environ[key] = value