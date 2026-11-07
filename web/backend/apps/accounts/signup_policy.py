"""Who may create an account on this instance, and whether they must verify.

The operator decides in ``mycelium.toml`` (``[signup]``; see
``config/instance.py``):

``closed``  only an admin creates accounts (``make admin``, the admin page).
``invite``  an invite link or email from someone already inside.
``code``    the shared access code in ``.env`` (``SIGNUP_ACCESS_CODE``), or an
            invite. The only mode with the brute-force shadow ban, because it is
            the only one with a secret to guess.
``domain``  any address at ``signup.allowed_domains`` (or a subdomain), or an
            invite. Proving the domain means proving the address, so this mode
            always verifies by email.
``open``    anyone.

An invite is accepted in every mode except ``closed``.

**Verification is activation, and it is optional.** With
``signup.verify_email`` off (the default outside the ``institution`` profile)
an account is active the moment it exists — nothing waits on a mail server.
``Profile.is_verified`` keeps its narrower meaning either way: *this address
was proved*, which is what institution affiliation and collaborator search
rely on, so it is never set without a real proof.
"""

from __future__ import annotations

from django.conf import settings

CLOSED, INVITE, CODE, DOMAIN, OPEN = "closed", "invite", "code", "domain", "open"


def mode() -> str:
    return str(getattr(settings, "SIGNUP_MODE", CODE) or CODE)


def verification_required() -> bool:
    """Whether an account must answer a mailed code before it is active."""
    return bool(getattr(settings, "SIGNUP_VERIFY_EMAIL", False)) or mode() == DOMAIN


def allowed_domains() -> list[str]:
    domains = getattr(settings, "SIGNUP_ALLOWED_DOMAINS", None) or []
    return [d.lstrip("@").lower() for d in domains]


def domain_allowed(email: str) -> bool:
    """Whether ``email`` is at an allowed domain or one of its subdomains."""
    _, _, host = str(email or "").strip().lower().rpartition("@")
    if not host:
        return False
    return any(host == d or host.endswith(f".{d}") for d in allowed_domains())


def public_policy() -> dict:
    """What the signed-out sign-up page needs to render the right form."""
    current = mode()
    return {
        "mode": current,
        "verify_email": verification_required(),
        "domains": allowed_domains() if current == DOMAIN else [],
    }


#: The refusal for each mode a self sign-up (no invite) cannot pass.
REFUSALS = {
    CLOSED: (
        "signup_closed",
        "Sign-up is closed on this instance. Ask an administrator for an account.",
    ),
    INVITE: (
        "invite_required",
        "Sign-up on this instance is by invitation. Ask someone already here "
        "to invite you.",
    ),
}
