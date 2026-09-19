"""Auto-provision a login *and* a populated profile from one author identifier.

``provision_from_author`` is the single entry point the brief asks for: it
resolves an author, builds the interest draft (via the Phase C importer), creates
a ``User`` with generated credentials, writes a contract-valid ``Profile``
(interests, external ids), and returns the credentials. Both the
``provision_user`` management path and the import-from-author API call it.

The importer is injectable so the service is unit-tested offline with a canned
draft — no network.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify

from .author_works import store_author_works
from .intake import AuthorProfileDraft, import_author
from .interests import validate_interests
from .models import AcademicTitle, Profile

#: Generated logins are marked with this email domain so demo tooling can find
#: and clear them, mirroring the seeder's ``demo.mycelium.test`` convention.
DEFAULT_EMAIL_DOMAIN = "imported.mycelium.test"
# Unambiguous alphabet (no 0/O, 1/l/I), matching the seeder's passwords.
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 14

ImporterFn = Callable[[str, str], AuthorProfileDraft]


@dataclass(frozen=True)
class ProvisionedAuthor:
    """The result of provisioning: the user, profile, draft, and credentials."""

    user: User
    profile: Profile
    draft: AuthorProfileDraft
    credentials: dict[str, Any]


def _generate_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def _split_name(display_name: str) -> tuple[str, str]:
    parts = (display_name or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _unique_username(display_name: str, fallback: str) -> str:
    base = slugify(display_name).replace("-", ".") or slugify(fallback) or "author"
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def provision_from_author(
    identifier: str,
    source: str,
    *,
    importer: ImporterFn = import_author,
    email_domain: str = DEFAULT_EMAIL_DOMAIN,
    academic_title: str = AcademicTitle.RESEARCHER,
    password: str | None = None,
    statement: str = "",
) -> ProvisionedAuthor:
    """Create a login + populated profile from an external author id."""

    draft = importer(identifier, source)

    username = _unique_username(draft.display_name, identifier)
    raw_password = password or _generate_password()
    email = f"{username}@{email_domain}"
    first, last = _split_name(draft.display_name)
    interests = validate_interests(draft.to_interests(statement=statement))
    external = draft.external_ids

    with transaction.atomic():
        user = User(
            username=username, email=email, first_name=first, last_name=last
        )
        user.set_password(raw_password)
        user.save()  # post_save signal creates the Profile

        profile = user.profile
        profile.academic_title = academic_title
        profile.interests = interests
        profile.orcid = external.get("orcid", "")
        profile.openalex_id = external.get("openalex", "")
        profile.scholar_id = external.get("scholar", "")
        profile.save()  # triggers the embedding hook (Phase F)

    credentials = {
        "name": draft.display_name,
        "username": username,
        "email": email,
        "password": raw_password,
        "academic_title": academic_title,
        # Never the imported record's: an institution is proved by a verified
        # address (apps.accounts.institution), and this one is not verified.
        "institution": "",
        "orcid": profile.orcid,
        "openalex_id": profile.openalex_id,
        "scholar_id": profile.scholar_id,
    }
    # Keep the works the import already read (plan M9). Done here as well as in
    # the app's import endpoint, because an account provisioned from an author id
    # never passes through that endpoint at all.
    store_author_works(user, draft, source=source)

    return ProvisionedAuthor(
        user=user, profile=profile, draft=draft, credentials=credentials
    )
