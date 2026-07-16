"""Encryption for OAuth tokens at rest.

Discord user-OAuth access/refresh tokens are bearer credentials: anyone holding
one can act as that user against Discord until it expires or is revoked. They must
not sit in the database in plaintext. ``EncryptedTextField`` transparently Fernet-
encrypts on write and decrypts on read, so callers see a normal string.

Key resolution (``_fernet``):
  1. ``settings.DISCORD_TOKEN_ENC_KEY`` when set — a urlsafe-base64 32-byte Fernet
     key, distinct from the bot token, rotated independently in production.
  2. Otherwise a key *derived* from ``SECRET_KEY`` (sha256 → urlsafe-b64). This keeps
     dev and tests working with no extra config while still never storing plaintext;
     production is expected to set an explicit key.

Ciphertext is non-deterministic (Fernet embeds a timestamp + IV), so an encrypted
column cannot be filtered/joined on — that is fine, tokens are only ever read back
for a specific row, never queried by value.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

# Marks a stored value as ciphertext this field produced, so a plaintext value
# written before encryption was enabled (or a blank) is passed through untouched
# rather than mis-decrypted into garbage.
_PREFIX = "fernet:"


def _fernet() -> Fernet:
    key = getattr(settings, "DISCORD_TOKEN_ENC_KEY", "") or ""
    if not key:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    if isinstance(key, str):
        key = key.encode("ascii")
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """A TextField whose value is Fernet-encrypted in the database."""

    description = "Text stored Fernet-encrypted at rest"

    def get_prep_value(self, value):  # type: ignore[override]
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        token = _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")
        return _PREFIX + token

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):  # type: ignore[override]
        return self._decrypt(value)

    @staticmethod
    def _decrypt(value):
        if value is None or value == "":
            return value
        if not str(value).startswith(_PREFIX):
            # Legacy / pre-encryption plaintext — return as-is.
            return value
        token = str(value)[len(_PREFIX) :].encode("ascii")
        try:
            return _fernet().decrypt(token).decode("utf-8")
        except InvalidToken:
            # Wrong/rotated key: refuse to surface ciphertext as if it were the
            # token. Treat as absent so the caller re-links rather than sending a
            # broken bearer to Discord.
            return ""
