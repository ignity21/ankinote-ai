"""Read-only provider profile discovery, mainly for scripted/agent use.

Lets a caller enumerate the ``--profile``/``--image-profile`` names
``word``/``phrase``/``sentence``/``stem`` accept (see ``cli/factory.py``)
without parsing ``settings.json`` itself. Never prints ``api_key``.
"""

import json

import click

from ankinote.settings import ProviderProfile, Settings, load_settings


def _profile_row(name: str, profile: ProviderProfile, active_name: str) -> dict:
    return {
        "name": name,
        "vendor": profile.vendor,
        "model": profile.model,
        "base_url": profile.base_url,
        "active": name == active_name,
    }


def _profiles_payload(settings: Settings) -> dict:
    return {
        "text_providers": [
            _profile_row(name, profile, settings.active_text_provider)
            for name, profile in settings.text_providers.items()
        ],
        "image_providers": [
            _profile_row(name, profile, settings.active_image_provider)
            for name, profile in settings.image_providers.items()
        ],
    }


def _echo_table(kind: str, rows: list[dict]) -> None:
    click.echo(f"{kind}:")
    if not rows:
        click.echo("  (none configured)")
        return
    for row in rows:
        marker = " (active)" if row["active"] else ""
        click.echo(
            f"  {row['name']}{marker} — vendor={row['vendor']} model={row['model']}"
        )


@click.group()
def profiles() -> None:
    """Inspect configured provider profiles (read-only)."""


@profiles.command("list")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON instead of a human-readable table.",
)
def list_profiles(as_json: bool) -> None:
    """List text and image provider profiles from settings.json.

    Never includes ``api_key`` — pass a profile's ``name`` to the
    ``--profile``/``--image-profile`` flags on the generation commands.
    """
    payload = _profiles_payload(load_settings())
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    _echo_table("Text providers", payload["text_providers"])
    _echo_table("Image providers", payload["image_providers"])
