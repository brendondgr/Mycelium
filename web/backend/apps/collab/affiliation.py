"""Where a person's **verified** email places them: institution and country.

Collaboration scope ("my institution", "my country") must not be something a
person can type, or anyone could claim any institution (design §7, "Verified
scope"). So it is derived from the domain of an email address the account has
verified, matched against the affiliation directory the app's institution
picker already uses (``web/app/public/data/institutions.json``, built by
``npm run institutions``) — one source, read here rather than copied.

A subdomain resolves to its institution (``cs.ox.ac.uk`` → Oxford) by walking
up the labels; a personal address (``gmail.com``) resolves to nothing, and a
person with no verified institution has no institution or country scope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .models import VerifiedAffiliation


@dataclass(frozen=True)
class Institution:
    domain: str
    name: str
    country: str


@lru_cache(maxsize=1)
def _directory(path: str) -> dict[str, Institution]:
    data = json.loads(Path(path).read_text())
    index: dict[str, Institution] = {}
    for name, country, domain, _region, _kind in data.get("items") or []:
        if domain:
            index[domain.lower()] = Institution(domain.lower(), name, country or "")
    for primary, alternates in (data.get("alt_domains") or {}).items():
        institution = index.get(primary.lower())
        if institution is None:
            continue
        for alternate in alternates or []:
            index.setdefault(alternate.lower(), institution)
    return index


def directory() -> dict[str, Institution]:
    return _directory(str(settings.COLLAB_INSTITUTIONS_PATH))


def resolve_domain(domain: str) -> Institution | None:
    """The institution a domain belongs to, walking up subdomains."""
    labels = (domain or "").lower().strip(".").split(".")
    index = directory()
    # Never below two labels: "ac.uk" or "edu" is not an institution.
    for start in range(0, max(0, len(labels) - 1)):
        candidate = ".".join(labels[start:])
        if candidate.count(".") < 1:
            break
        if candidate in index:
            return index[candidate]
    return None


def resolve_email(email: str) -> Institution | None:
    if "@" not in (email or ""):
        return None
    return resolve_domain(email.rsplit("@", 1)[1])


def refresh(user) -> VerifiedAffiliation | None:
    """Derive (or clear) a person's verified affiliation from their account.

    Only a verified address counts. Returns the row, or ``None`` when the
    account is not verified — and then any stale row is removed, because an
    email changed and not yet re-verified must not keep an old scope.
    """
    profile = getattr(user, "profile", None)
    if profile is None or not profile.is_verified or not user.email:
        VerifiedAffiliation.objects.filter(user=user).delete()
        return None
    found = resolve_email(user.email)
    row, _ = VerifiedAffiliation.objects.update_or_create(
        user=user,
        defaults={
            "email": user.email.lower(),
            "domain": found.domain if found else "",
            "institution": found.name if found else "",
            "country": found.country if found else "",
        },
    )
    return row
