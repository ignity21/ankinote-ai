"""Encrypted export/import of the GUI's provider configuration.

The bundle carries only the parts a user needs to reproduce their setup on
another machine — text and image provider profiles (vendor, model, base URL,
API key) and the Google TTS key — encrypted with a passphrase so the file is
safe to move through channels the plaintext ``settings.json`` is not.

Format (UTF-8 JSON, the file itself):

    {
      "format": "ankinote-config",
      "version": 1,
      "kdf": {"name": "scrypt", "n": 32768, "r": 8, "p": 1, "salt": "<b64>"},
      "cipher": "AES-256-GCM",
      "nonce": "<b64>",
      "ciphertext": "<b64>"
    }

The header (everything except ``nonce``/``ciphertext``) is authenticated as
AES-GCM associated data, so tampering with the KDF parameters is detected on
import just like tampering with the ciphertext.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from ankinote.ui.config import ProviderProfile, Settings

BUNDLE_FORMAT = "ankinote-config"
BUNDLE_VERSION = 1

_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_BYTES = 32
_SALT_BYTES = 16
_NONCE_BYTES = 12

MIN_PASSPHRASE_LENGTH = 8


class ConfigTransferError(Exception):
    """Base class for export/import failures."""


class ConfigImportError(ConfigTransferError):
    """The bundle could not be read: wrong passphrase, corrupt, or not ours."""


@dataclass
class ConfigBundle:
    """The decrypted, still-untrusted contents of an import file."""

    text_providers: dict[str, ProviderProfile] = field(default_factory=dict)
    image_providers: dict[str, ProviderProfile] = field(default_factory=dict)
    google_tts_key: str = ""

    @property
    def profile_count(self) -> int:
        return len(self.text_providers) + len(self.image_providers)


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: object) -> bytes:
    if not isinstance(text, str):
        raise ConfigImportError("Malformed configuration file.")
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise ConfigImportError("Malformed configuration file.") from exc


def _derive_key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    kdf = Scrypt(salt=salt, length=_KEY_BYTES, n=n, r=r, p=p)
    return kdf.derive(passphrase.encode("utf-8"))


def _header(salt: bytes) -> dict[str, Any]:
    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "kdf": {
            "name": "scrypt",
            "n": _SCRYPT_N,
            "r": _SCRYPT_R,
            "p": _SCRYPT_P,
            "salt": _b64e(salt),
        },
        "cipher": "AES-256-GCM",
    }


def _aad(header: dict[str, Any]) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _profile_payload(profile: ProviderProfile) -> dict[str, str]:
    return {
        "vendor": profile.vendor,
        "model": profile.model,
        "base_url": profile.base_url,
        "api_key": profile.api_key,
    }


def _profile_from_payload(value: object) -> ProviderProfile:
    if not isinstance(value, dict):
        raise ConfigImportError("Malformed configuration file.")
    payload = cast(dict[str, object], value)
    return ProviderProfile(
        vendor=str(payload.get("vendor", "")),
        model=str(payload.get("model", "")),
        base_url=str(payload.get("base_url", "")),
        api_key=str(payload.get("api_key", "")),
    )


def _profiles_from_payload(value: object) -> dict[str, ProviderProfile]:
    if not isinstance(value, dict):
        raise ConfigImportError("Malformed configuration file.")
    return {
        name: _profile_from_payload(profile)
        for name, profile in value.items()
        if isinstance(name, str)
    }


def export_config(settings: Settings, passphrase: str) -> bytes:
    """Encrypt the transferable slice of ``settings`` into a bundle file.

    Raises:
        ConfigTransferError: If the passphrase is too short.
    """
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise ConfigTransferError(
            f"Passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters."
        )

    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    key = _derive_key(passphrase, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)

    payload = {
        "text_providers": {
            name: _profile_payload(p) for name, p in settings.text_providers.items()
        },
        "image_providers": {
            name: _profile_payload(p) for name, p in settings.image_providers.items()
        },
        "google_tts_key": settings.api_keys.get("GOOGLE_TTS_KEY", ""),
    }

    header = _header(salt)
    ciphertext = AESGCM(key).encrypt(
        nonce, json.dumps(payload).encode("utf-8"), _aad(header)
    )
    return json.dumps(
        {**header, "nonce": _b64e(nonce), "ciphertext": _b64e(ciphertext)}, indent=2
    ).encode("utf-8")


def _parse_document(blob: bytes) -> dict[str, Any]:
    """Decode the outer JSON envelope and check the format/version markers."""
    try:
        document = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ConfigImportError("This is not an ankinote configuration file.") from exc
    if not isinstance(document, dict) or document.get("format") != BUNDLE_FORMAT:
        raise ConfigImportError("This is not an ankinote configuration file.")
    if document.get("version") != BUNDLE_VERSION:
        raise ConfigImportError(
            f"Unsupported configuration version {document.get('version')!r}."
        )
    return document


def _parse_kdf_header(
    document: dict[str, Any],
) -> tuple[dict[str, Any], bytes, int, int, int]:
    """Validate the KDF parameters and rebuild the header used as AAD."""
    kdf = document.get("kdf")
    if not isinstance(kdf, dict) or kdf.get("name") != "scrypt":
        raise ConfigImportError("Malformed configuration file.")
    try:
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigImportError("Malformed configuration file.") from exc

    salt = _b64d(kdf.get("salt"))
    header = {
        "format": document["format"],
        "version": document["version"],
        "kdf": {"name": "scrypt", "n": n, "r": r, "p": p, "salt": kdf.get("salt")},
        "cipher": document.get("cipher"),
    }
    return header, salt, n, r, p


def _decrypt_payload(
    header: dict[str, Any],
    salt: bytes,
    n: int,
    r: int,
    p: int,
    nonce: bytes,
    ciphertext: bytes,
    passphrase: str,
) -> dict[str, Any]:
    """Derive the key, decrypt, and parse the inner JSON payload."""
    try:
        key = _derive_key(passphrase, salt, n, r, p)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, _aad(header))
    except InvalidTag as exc:
        raise ConfigImportError(
            "Wrong passphrase, or the file has been modified."
        ) from exc
    except ValueError as exc:
        raise ConfigImportError("Malformed configuration file.") from exc

    try:
        payload = json.loads(plaintext)
    except ValueError as exc:
        raise ConfigImportError("Malformed configuration file.") from exc
    if not isinstance(payload, dict):
        raise ConfigImportError("Malformed configuration file.")
    return payload


def import_config(blob: bytes, passphrase: str) -> ConfigBundle:
    """Decrypt and parse a bundle file.

    Raises:
        ConfigImportError: If the file is not an ankinote bundle, the passphrase
            is wrong, or the contents are tampered with or corrupt.
    """
    document = _parse_document(blob)
    header, salt, n, r, p = _parse_kdf_header(document)
    nonce = _b64d(document.get("nonce"))
    ciphertext = _b64d(document.get("ciphertext"))
    payload = _decrypt_payload(header, salt, n, r, p, nonce, ciphertext, passphrase)

    return ConfigBundle(
        text_providers=_profiles_from_payload(payload.get("text_providers", {})),
        image_providers=_profiles_from_payload(payload.get("image_providers", {})),
        google_tts_key=str(payload.get("google_tts_key", "")),
    )


def merge_bundle(settings: Settings, bundle: ConfigBundle) -> Settings:
    """Merge ``bundle`` into ``settings`` by profile name, returning a new value.

    Provider profiles are merged by name: a bundled name that already exists is
    overwritten, a new one is added. The active-provider selections, generation
    defaults, UI language, image size, and any other stored keys are left as
    they are. The Google TTS key is replaced only when the bundle carries a
    non-empty one.
    """
    text_providers = {**settings.text_providers, **bundle.text_providers}
    image_providers = {**settings.image_providers, **bundle.image_providers}

    api_keys = dict(settings.api_keys)
    if bundle.google_tts_key:
        api_keys["GOOGLE_TTS_KEY"] = bundle.google_tts_key

    return Settings(
        text_providers=text_providers,
        active_text_provider=settings.active_text_provider,
        image_providers=image_providers,
        active_image_provider=settings.active_image_provider,
        image_size=settings.image_size,
        api_keys=api_keys,
        defaults=settings.defaults,
        ui_language=settings.ui_language,
    )
