"""
Encryption for the secret store (docs/HOOKS.md Part 1).

Secrets are encrypted at rest with Fernet (AES-128-CBC + HMAC). Keys are
versioned so they can be rotated without downtime: new ciphertext is written
under the current key; old ciphertext records which key encrypted them and is
decryptable until re-encrypted.

Configuration (settings):
    SECRETS_ENCRYPTION_KEYS         {version:int -> urlsafe-base64 32-byte key}
    SECRETS_ENCRYPTION_KEY_CURRENT  the version new secrets encrypt under

Fails closed: if no keys are configured, encryption raises rather than
storing plaintext.
"""
from __future__ import annotations

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


class SecretsNotConfigured(RuntimeError):
    """Raised when secret encryption is used without a configured key."""


def _keys() -> dict[int, str]:
    keys = getattr(settings, "SECRETS_ENCRYPTION_KEYS", None) or {}
    if not keys:
        raise SecretsNotConfigured(
            "SECRETS_ENCRYPTION_KEYS is not configured — refusing to store secrets. "
            "Set a key before using the secret store."
        )
    return keys


def current_key_version() -> int:
    keys = _keys()
    version = getattr(settings, "SECRETS_ENCRYPTION_KEY_CURRENT", None)
    if version not in keys:
        # Default to the highest configured version.
        version = max(keys)
    return version


def encrypt(plaintext: str) -> tuple[bytes, int]:
    """Return (ciphertext, key_version). Raises SecretsNotConfigured if no key."""
    version = current_key_version()
    f = Fernet(_keys()[version])
    return f.encrypt(plaintext.encode()), version


def decrypt(ciphertext: bytes, key_version: int) -> str:
    """Decrypt ciphertext previously produced under key_version."""
    keys = _keys()
    key = keys.get(key_version)
    if key is None:
        raise SecretsNotConfigured(
            f"No encryption key configured for version {key_version}; "
            "cannot decrypt this secret (was the key retired?)."
        )
    try:
        return Fernet(key).decrypt(bytes(ciphertext)).decode()
    except InvalidToken as exc:  # wrong key / corrupted data
        raise SecretsNotConfigured("Secret could not be decrypted with the configured key.") from exc


def generate_key() -> str:
    """Convenience for ops: a fresh urlsafe-base64 Fernet key."""
    return Fernet.generate_key().decode()


def redact(text: str, secret_values) -> str:
    """Replace any known secret value in `text` with a placeholder.

    Run over every hook execution log, error message, and audit payload before
    it is persisted, so a resolved secret can never leak through observability.
    """
    if not text:
        return text
    out = text
    for value in secret_values:
        if value:
            out = out.replace(value, "«redacted»")
    return out
