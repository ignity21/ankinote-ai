"""Read and write the text / image / speech routes as the wizard sees them.

A route is served by one provider profile. The wizard and Settings → Models
describe each route as a draft (preset, model, base URL, key); this module
turns drafts into ordinary profiles and back. API keys never leave the
server: views carry only a hint of the saved key, and a draft without a key
reuses the saved one for the same provider.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

from ankinote.model_presets import (
    CUSTOM_PRESET,
    CUSTOM_VENDOR,
    PRESETS,
    ROUTES,
    Route,
    preset_for,
)
from ankinote.services.model_check import RouteTarget
from ankinote.settings import (
    ProviderProfile,
    Settings,
    active_profile,
    route_profiles,
    set_active_profile,
    unique_name,
)


class MissingKeyError(ValueError):
    """A draft has no key and there is no saved key for its provider."""

    def __init__(self, route: Route) -> None:
        self.route = route
        super().__init__(f"No API key for the {route} route")


class InvalidDraftError(ValueError):
    """A draft names an unknown preset, a route it can't serve, or no model."""

    def __init__(self, route: Route, reason: str) -> None:
        self.route = route
        super().__init__(f"{route}: {reason}")


@dataclass(frozen=True, slots=True)
class RouteDraft:
    """One route as the user set it up. ``api_key=None`` keeps the saved key."""

    provider: str
    model: str
    base_url: str = ""
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class RouteView:
    """One saved route, safe to send to the browser."""

    profile: str
    provider: str
    model: str
    base_url: str
    key_hint: str
    follows_preset: bool


def key_hint(key: str) -> str:
    """Enough of a key to recognise it, never enough to use it."""
    if not key:
        return ""
    return f"…{key[-4:]}" if len(key) >= 12 else "…"


def _profile_preset(profile: ProviderProfile) -> str:
    return profile.preset or preset_for(profile.vendor, profile.base_url).id


def route_view(settings: Settings, route: Route) -> RouteView | None:
    profile = active_profile(settings, route)
    if profile is None:
        return None
    name = {
        "text": settings.active_text_provider,
        "image": settings.active_image_provider,
        "speech": settings.active_speech_provider,
    }[route]
    return RouteView(
        profile=name,
        provider=_profile_preset(profile),
        model=profile.model,
        base_url=profile.base_url,
        key_hint=key_hint(profile.api_key),
        follows_preset=bool(profile.preset),
    )


def needs_setup(settings: Settings) -> bool:
    """True until the text route can reach a model: the wizard's trigger."""
    profile = active_profile(settings, "text")
    if profile is None or not profile.model:
        return True
    if profile.vendor == CUSTOM_VENDOR:
        return not profile.base_url
    return not profile.api_key


def _same_endpoint(profile: ProviderProfile, provider: str, base_url: str) -> bool:
    if _profile_preset(profile) != provider:
        return False
    if provider != CUSTOM_PRESET:
        return True
    return profile.base_url.rstrip("/") == base_url.rstrip("/")


def _saved_key(settings: Settings, provider: str, base_url: str) -> str | None:
    """A saved key for this provider, from any route's active profile."""
    for route in ROUTES:
        profile = active_profile(settings, route)
        if profile and profile.api_key and _same_endpoint(profile, provider, base_url):
            return profile.api_key
    return None


def draft_to_profile(
    settings: Settings, route: Route, draft: RouteDraft
) -> ProviderProfile:
    """Validate a draft and fill in what the preset and saved settings know."""
    preset = PRESETS.get(draft.provider)
    if preset is None:
        raise InvalidDraftError(route, f"unknown provider {draft.provider!r}")
    if preset.id != CUSTOM_PRESET and route not in preset.models:
        raise InvalidDraftError(route, f"{preset.label} has no {route} models")
    model = draft.model.strip()
    if not model:
        raise InvalidDraftError(route, "no model")
    base_url = (draft.base_url.strip() if preset.id == CUSTOM_PRESET else "") or (
        preset.base_url
    )
    if not base_url:
        raise InvalidDraftError(route, "no base URL")

    key = draft.api_key.strip() if draft.api_key is not None else None
    if not key:
        key = _saved_key(settings, preset.id, base_url)
    # A local OpenAI-compatible server may need no key at all.
    if key is None and preset.id != CUSTOM_PRESET:
        raise MissingKeyError(route)

    follows = preset.id != CUSTOM_PRESET and model == preset.models.get(route)
    return ProviderProfile(
        vendor=preset.vendor,
        model=model,
        base_url=base_url,
        api_key=key or "",
        preset=preset.id if follows else "",
    )


def route_targets(
    settings: Settings, drafts: dict[Route, RouteDraft | None]
) -> dict[Route, RouteTarget | None]:
    """Resolve drafts into what :func:`check_routes` needs."""
    return {
        route: None
        if draft is None
        else RouteTarget(draft.provider, draft_to_profile(settings, route, draft))
        for route, draft in drafts.items()
    }


def _profile_name(profile: ProviderProfile, provider: str) -> str:
    if provider == CUSTOM_PRESET:
        return urlparse(profile.base_url).hostname or "Custom"
    return PRESETS[provider].label


def _is_unusable(profile: ProviderProfile) -> bool:
    """Built-in default profiles that were never given a key."""
    return profile.vendor != CUSTOM_VENDOR and not profile.api_key


def apply_drafts(
    settings: Settings, drafts: dict[Route, RouteDraft | None]
) -> Settings:
    """Save each route's draft as a profile and make it the active one.

    A profile with the same name and vendor is overwritten (pasting a new
    Gemini key replaces the old Gemini profile); otherwise the name gets a
    suffix. ``None`` turns a route off; text can't be turned off.
    """
    if drafts.get("text", RouteDraft("", "")) is None:
        raise InvalidDraftError("text", "the text route can't be turned off")
    resolved = {
        route: (
            draft,
            None if draft is None else draft_to_profile(settings, route, draft),
        )
        for route, draft in drafts.items()
    }
    for route, (draft, profile) in resolved.items():
        profiles = route_profiles(settings, route)
        if draft is None or profile is None:
            set_active_profile(settings, route, "")
        else:
            name = _profile_name(profile, draft.provider)
            existing = profiles.get(name)
            if existing is not None and existing.vendor != profile.vendor:
                name = unique_name(name, set(profiles))
            profiles[name] = profile
            set_active_profile(settings, route, name)
        active = active_profile(settings, route)
        for name in [n for n, p in profiles.items() if _is_unusable(p)]:
            if profiles[name] is not active:
                del profiles[name]
    return settings
