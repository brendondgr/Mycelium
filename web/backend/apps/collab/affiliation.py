"""Where a person's **verified** email places them: institution and country.

Collaboration scope ("my institution", "my country") must not be something a
person can type, or anyone could claim any institution (design §7, "Verified
scope"). So it is derived from the domain of an email address the account has
verified, matched against the affiliation directory by the resolver in
:mod:`apps.accounts.institution` — the same derivation that writes a person's
shown institution, so the two can never disagree.

A subdomain resolves to its institution (``cs.ox.ac.uk`` → Oxford) by walking
up the labels; a personal address (``gmail.com``) resolves to nothing, and a
person with no verified institution has no institution or country scope.
"""

from __future__ import annotations

from apps.accounts import institution as _institution
from apps.accounts.institution import (  # noqa: F401 - the resolver, re-exported
    Institution,
    directory,
    resolve_domain,
    resolve_email,
)

from .models import VerifiedAffiliation


def refresh(user) -> VerifiedAffiliation | None:
    """Derive (or clear) a person's verified affiliation from their account.

    Only a verified address counts. Returns the row, or ``None`` when the
    account is not verified — and then any stale row is removed, because an
    email changed and not yet re-verified must not keep an old scope.
    """
    profile = getattr(user, "profile", None)
    if profile is not None:
        _institution.sync(user)
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


def on_email_verified(sender, user, **kwargs) -> None:
    """Re-derive the affiliation the moment an address is proved."""
    refresh(user)
