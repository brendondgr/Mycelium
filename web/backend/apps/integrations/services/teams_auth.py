"""Bot Framework authentication for Teams (ambient Plan 11).

Inbound: every request to the messaging endpoint carries a JWT signed by the
Bot Framework. It is verified here before anything is read:
- the signature (RS256), against the key named by the token's ``kid``, taken
  from the keys the OpenID configuration publishes and cached for a day (one
  refetch when an unknown ``kid`` appears, because keys roll);
- the issuer;
- the audience, which must be this app's id;
- the expiry and not-before, with five minutes of clock skew;
- the ``serviceUrl`` claim, which must match the activity's own.

Outbound: a bot token from the client-credentials grant, cached until shortly
before it expires. Only ``cryptography`` and the standard library are used.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.core.cache import cache

_SKEW = 300
_KEYS_CACHE = "teams:jwks"
_TOKEN_CACHE = "teams:bot-token"


class InvalidToken(Exception):
    pass


def _b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode())


def _keys(*, refresh: bool = False) -> dict:
    """``{kid: jwk}`` from the published configuration."""
    if not refresh:
        cached = cache.get(_KEYS_CACHE)
        if cached:
            return cached
    config = _fetch_json(settings.TEAMS_OPENID_CONFIG_URL)
    jwks = _fetch_json(config["jwks_uri"])
    keys = {key["kid"]: key for key in jwks.get("keys", []) if key.get("kid")}
    cache.set(_KEYS_CACHE, keys, 24 * 3600)
    return keys


def _public_key(jwk: dict):
    n = int.from_bytes(_b64url(jwk["n"]), "big")
    e = int.from_bytes(_b64url(jwk["e"]), "big")
    return rsa.RSAPublicNumbers(e, n).public_key()


def verify(
    authorization: str, *, service_url: str, now: float | None = None, keys=None
) -> dict:
    """The token's claims, or :class:`InvalidToken`."""
    if not authorization.startswith("Bearer "):
        raise InvalidToken("no bearer token")
    token = authorization[len("Bearer ") :].strip()
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url(header_b64))
        claims = json.loads(_b64url(payload_b64))
        signature = _b64url(signature_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidToken("malformed") from exc
    if header.get("alg") != "RS256":
        raise InvalidToken("unexpected algorithm")
    kid = header.get("kid", "")
    known = keys if keys is not None else _keys()
    if kid not in known and keys is None:
        known = _keys(refresh=True)
    jwk = known.get(kid)
    if jwk is None:
        raise InvalidToken("unknown key")
    try:
        _public_key(jwk).verify(
            signature,
            f"{header_b64}.{payload_b64}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise InvalidToken("bad signature") from exc
    now = now if now is not None else time.time()
    if claims.get("iss") != settings.TEAMS_TOKEN_ISSUER:
        raise InvalidToken("wrong issuer")
    if not settings.TEAMS_APP_ID or claims.get("aud") != settings.TEAMS_APP_ID:
        raise InvalidToken("wrong audience")
    if float(claims.get("exp", 0)) < now - _SKEW:
        raise InvalidToken("expired")
    if float(claims.get("nbf", 0)) > now + _SKEW:
        raise InvalidToken("not yet valid")
    claimed = claims.get("serviceurl") or claims.get("serviceUrl")
    if claimed and claimed.rstrip("/") != (service_url or "").rstrip("/"):
        raise InvalidToken("service url mismatch")
    return claims


def bot_token() -> str:
    """A bearer token for calls to the Connector API (client credentials)."""
    cached = cache.get(_TOKEN_CACHE)
    if cached:
        return cached
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.TEAMS_APP_ID,
            "client_secret": settings.TEAMS_APP_PASSWORD,
            "scope": "https://api.botframework.com/.default",
        }
    ).encode()
    request = urllib.request.Request(
        settings.TEAMS_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        body = json.loads(response.read().decode())
    token = str(body.get("access_token") or "")
    cache.set(_TOKEN_CACHE, token, max(60, int(body.get("expires_in", 3600)) - 300))
    return token
