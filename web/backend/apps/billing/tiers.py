"""Which tiers may be sold to which scope — the one rule behind "buy Lab on the lab".

A tier is not a free-floating price point; it names *who* is covered. Free and Spore
cover one researcher, so they belong on a personal (``scope_user``) subscription.
Mycelium Lab covers a team and is priced per member, so it only makes sense on a
``scope_lab`` plan, where the roster answers "how many people am I paying for". Canopy
is the department plan.

Letting an individual hold a Lab-tier *personal* plan breaks that: the plan would grant
team features to an account with no team, and there would be no roster to price it
against — the seat count would be one, forever, whatever the lab's real size. So the
purchase has to happen on a lab: the lab's own Billing page is the only place a Lab plan
is activated, and activation seats the lab's actual members (see
:func:`apps.billing.services.activate_lab_subscription`).

This module is the single statement of that rule. It is enforced at every point a plan
is *granted* — provisioning, the admin dashboard, and activation — rather than as a
database constraint, because the rule is about selling a plan, not about what rows may
exist: fixtures and historical rows stay readable, and the entitlement read path is
deliberately untouched (a downgrade must never lose data).
"""

from __future__ import annotations

from .models import Tier


class TierScopeError(ValueError):
    """A tier was assigned to a scope it is not sold to."""


#: One researcher pays for themselves.
PERSONAL_TIERS: frozenset[str] = frozenset({Tier.FREE, Tier.SPORE})

#: A lab plan covers a roster. Canopy is allowed here so a lab can be granted
#: department-level capability directly (e.g. a comped pilot) without inventing a
#: department for it; Lab is the normal case.
LAB_TIERS: frozenset[str] = frozenset({Tier.LAB, Tier.CANOPY})

#: Department routing is Canopy and only Canopy.
DEPARTMENT_TIERS: frozenset[str] = frozenset({Tier.CANOPY})

_BY_SCOPE: dict[str, frozenset[str]] = {
    "user": PERSONAL_TIERS,
    "lab": LAB_TIERS,
    "department": DEPARTMENT_TIERS,
}

_SCOPE_LABEL = {
    "user": "a personal account",
    "lab": "a lab",
    "department": "a department",
}


def tiers_for_scope(scope_type: str) -> frozenset[str]:
    """The tiers sold to ``scope_type`` (``user`` / ``lab`` / ``department``)."""
    return _BY_SCOPE.get(scope_type, PERSONAL_TIERS)


def tier_allowed_for_scope(scope_type: str, tier: str) -> bool:
    return tier in tiers_for_scope(scope_type)


def validate_tier_for_scope(scope_type: str, tier: str) -> None:
    """Raise :class:`TierScopeError` when ``tier`` is not sold to ``scope_type``.

    The message names the surface the caller should have used, since the usual cause is
    someone trying to grant a team plan to one person.
    """
    if tier_allowed_for_scope(scope_type, tier):
        return
    label = dict(Tier.choices).get(tier, tier)
    if scope_type == "user" and tier in LAB_TIERS:
        raise TierScopeError(
            f"{label} is a team plan and is activated on a lab, not on "
            f"{_SCOPE_LABEL['user']}. Create or open the lab and activate it there, "
            f"so the plan covers — and is priced by — the lab's actual members."
        )
    raise TierScopeError(
        f"{label} is not available for {_SCOPE_LABEL.get(scope_type, scope_type)}."
    )
