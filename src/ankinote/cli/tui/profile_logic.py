"""Pure add/remove/rename logic for provider profile dicts.

Shared by the text- and image-profile TUI menus so both offer the same CRUD
semantics as the Web UI's ``RouteRack`` — only the vendor catalog and model
list differ, and those stay in each caller.
"""

from ankinote.settings import ProviderProfile


def add_profile(
    providers: dict[str, ProviderProfile],
    *,
    name: str,
    vendor: str,
    base_url: str,
    model_options: list[str],
) -> ProviderProfile:
    """Create and register a new profile, defaulting to the first model option."""
    if name in providers:
        raise ValueError(f"a profile named {name!r} already exists")
    profile = ProviderProfile(
        vendor=vendor,
        model=model_options[0] if model_options else "",
        base_url=base_url,
    )
    providers[name] = profile
    return profile


def remove_profile(
    providers: dict[str, ProviderProfile], active: str, name: str
) -> str:
    """Delete ``name``, returning the (possibly updated) active profile name.

    Refuses to delete the last remaining profile — at least one must exist
    for generation commands to fall back to.
    """
    if len(providers) <= 1:
        raise ValueError("cannot remove the last remaining profile")
    del providers[name]
    return next(iter(providers)) if active == name else active


def rename_profile(
    providers: dict[str, ProviderProfile], active: str, old_name: str, new_name: str
) -> str:
    """Rename ``old_name`` to ``new_name``, returning the (possibly updated) active name."""
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("name must not be empty")
    if new_name != old_name and new_name in providers:
        raise ValueError(f"a profile named {new_name!r} already exists")
    providers[new_name] = providers.pop(old_name)
    return new_name if active == old_name else active
