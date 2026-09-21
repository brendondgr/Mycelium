"""Where a person's email places them: an institution is proved, never typed.

A person is "at" an institution only when the address they verified belongs to
it — its domain, or a parent of it, is in the affiliation directory the app's
institution search already uses (``web/app/public/data/institutions.json``,
built by ``npm run institutions``). ``Profile.institution`` is a mirror of that
derivation, written only by :func:`sync`; nobody can claim an institution they
cannot receive mail at, and a personal address (``gmail.com``) places nobody.

The country the institution sits in is the only *location* Mycelium knows, so
it follows the same rule. Collaboration scope (``apps.collab``) reads both from
here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

#: The refusal code an API returns for an institution a request tried to type.
REFUSAL_CODE = "institution_from_email"


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


def verified(user) -> Institution | None:
    """The institution the account's *verified* address places it at."""
    profile = getattr(user, "profile", None)
    if profile is None or not profile.is_verified or not user.email:
        return None
    return resolve_email(user.email)


def granted(user) -> str:
    """The institution an operator granted this account, or ``""``."""
    profile = getattr(user, "profile", None)
    return (getattr(profile, "institution_granted", "") or "") if profile else ""


def sync(user) -> str:
    """Write ``Profile.institution`` from the grant, else the verified address.

    Still the one writer of the field, and still never the subject: a value here
    is either *proved* (an address they answered resolves to it) or *granted* (a
    named operator said so, recorded on the profile and in the audit log). A
    grant wins, because it exists precisely for the accounts the derivation
    cannot place — otherwise re-syncing on every verification would erase it.

    Saves only that column, and only when it changed, so it is safe to call on
    every read that needs the answer.
    """
    name = granted(user)
    if not name:
        found = verified(user)
        name = found.name if found else ""
    profile = user.profile
    if profile.institution != name:
        profile.institution = name
        # A queryset update: the institution is not part of the embedded
        # surface, so the profile's pre-save re-embedding has nothing to do.
        type(profile).objects.filter(pk=profile.pk).update(institution=name)
    return name


def grant(user, name: str, *, actor=None) -> str:
    """Grant ``user`` an institution the directory would not give them.

    ``name`` is resolved against the affiliation directory, so a grant can only
    name an institution Mycelium already knows — an operator may place someone,
    not invent somewhere. Returns the canonical name that was written.
    """
    from .services import record_audit_event

    wanted = (name or "").strip()
    if not wanted:
        raise ValueError("An institution name is required.")
    canonical = next(
        (
            found.name
            for found in directory().values()
            if found.name.casefold() == wanted.casefold()
        ),
        None,
    )
    if canonical is None:
        raise ValueError(
            f"{wanted!r} is not in the affiliation directory. "
            "Add it to web/scripts/data/research-institutions.json first."
        )
    profile = user.profile
    profile.institution_granted = canonical
    profile.institution_granted_by = actor
    profile.institution_granted_at = timezone.now()
    type(profile).objects.filter(pk=profile.pk).update(
        institution_granted=canonical,
        institution_granted_by=actor,
        institution_granted_at=profile.institution_granted_at,
    )
    record_audit_event(
        actor=actor,
        action="account.institution.grant",
        target_type="user",
        target_id=str(user.pk),
        metadata={"institution": canonical},
    )
    return sync(user)


def revoke_grant(user, *, actor=None) -> str:
    """Drop a grant, falling the account back to whatever its address proves."""
    from .services import record_audit_event

    profile = user.profile
    previous = profile.institution_granted
    profile.institution_granted = ""
    profile.institution_granted_by = None
    profile.institution_granted_at = None
    type(profile).objects.filter(pk=profile.pk).update(
        institution_granted="",
        institution_granted_by=None,
        institution_granted_at=None,
    )
    record_audit_event(
        actor=actor,
        action="account.institution.grant.revoked",
        target_type="user",
        target_id=str(user.pk),
        metadata={"institution": previous},
    )
    return sync(user)


def verified_then_sync(user) -> None:
    """After an address is proved: mirror the institution, then tell listeners.

    Deferred to commit so a rolled-back verification changes nothing.
    """
    from .signals import email_verified

    def _run() -> None:
        sync(user)
        email_verified.send(sender=user.__class__, user=user)

    transaction.on_commit(_run)


def refusal(user, typed: str) -> str | None:
    """Why ``typed`` cannot be this account's institution, or ``None`` if it may.

    An empty value, the institution already held, or the one an unverified
    address will prove is accepted as a no-op — nothing is written — so an older
    client that resends what it was shown does not break.
    """
    typed = (typed or "").strip()
    # A grant is what the account actually holds, so resending it is the same
    # no-op as resending a derived value — otherwise the one account that needed
    # an exception could not save its own profile form.
    awarded = granted(user)
    held = awarded or (found.name if (found := verified(user)) else "")
    pending = resolve_email(user.email)
    if not typed or typed.casefold() in {
        held.casefold(),
        (pending.name if pending else held).casefold(),
    }:
        return None
    if awarded:
        return (
            f"Your institution is set to {awarded} by an administrator. "
            "Ask them to change it."
        )
    if held:
        return (
            f"Your institution comes from your verified email: {held}. To be "
            f"listed at {typed}, change your email to an address there."
        )
    if pending and not getattr(user.profile, "is_verified", False):
        return (
            f"Confirm your email first: {pending.name} is shown once you do. "
            f"To be listed at {typed}, sign up with an address there."
        )
    return (
        "Your email isn't at an institution we recognise, so none can be "
        f"shown. To be listed at {typed}, change your email to an address there."
    )
