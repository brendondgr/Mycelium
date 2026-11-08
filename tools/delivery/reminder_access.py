"""Who may set a deadline reminder — the one place that answers it.

A reminder is a *Discord-delivered, paid* capability, so two independent conditions
must both hold before one can be created:

* **Discord is synced.** Personal reminders DM a person, so the person needs an
  ACTIVE :class:`DiscordIdentity`. Lab reminders post to a channel, so the *lab*
  needs an active guild link — the creating manager's own identity is irrelevant to
  whether the message can be delivered.
* **A paid plan covers the actor.** Expressed as
  :data:`~apps.billing.entitlements.Feature.DEADLINE_REMINDERS`, never as a
  tier-name comparison (architecture decision A1). For a user this resolves through
  ``covering_subscriptions``, which already unions their personal plan with any
  **active seat** they hold — so a researcher whose lab pays for their membership is
  individually entitled without any special case here.

Both the create path (:mod:`tools.delivery.reminders`) and the read surface the UI
locks its button with (``GET /api/reminders/access/``) call these functions, so the
affordance the user sees and the rule the server enforces cannot drift apart.

Discord state is read only through :mod:`apps.integrations.services.resolve` — the
single ORM boundary for the Discord side. This module imports no integration model.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.billing.entitlements import Feature, has_feature, lab_has_feature
from apps.integrations.services import resolve as discord_resolve


class Reason:
    """Why access was refused — a stable slug the UI branches its copy on."""

    NONE = ""
    PLAN = "plan"
    DISCORD = "discord"
    PLAN_AND_DISCORD = "plan_and_discord"


_DETAIL = {
    Reason.NONE: "",
    Reason.PLAN: (
        "Deadline reminders are part of a paid plan. Upgrade, or ask a lab manager "
        "to cover your membership."
    ),
    Reason.DISCORD: (
        "Connect Discord to receive reminders — Mylo delivers them there."
    ),
    Reason.PLAN_AND_DISCORD: (
        "Deadline reminders need a paid plan and a connected Discord account."
    ),
}

_LAB_DETAIL = {
    Reason.NONE: "",
    Reason.PLAN: "This lab's plan does not include deadline reminders.",
    Reason.DISCORD: (
        "This lab has no Discord server connected, so there is nowhere to post a "
        "reminder."
    ),
    Reason.PLAN_AND_DISCORD: (
        "This lab needs a paid plan and a connected Discord server before it can "
        "use deadline reminders."
    ),
}


@dataclass(frozen=True)
class ReminderAccess:
    """Whether reminders are available, and — when not — precisely what is missing.

    Both halves are reported even when access is granted, so the UI can name the one
    thing to fix rather than showing a generic "unavailable".
    """

    allowed: bool
    plan_ok: bool
    discord_ok: bool
    reason: str
    detail: str

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "plan_ok": self.plan_ok,
            "discord_ok": self.discord_ok,
            "reason": self.reason,
            "detail": self.detail,
        }


def _build(plan_ok: bool, discord_ok: bool, details: dict) -> ReminderAccess:
    if plan_ok and discord_ok:
        reason = Reason.NONE
    elif not plan_ok and not discord_ok:
        reason = Reason.PLAN_AND_DISCORD
    elif not plan_ok:
        reason = Reason.PLAN
    else:
        reason = Reason.DISCORD
    return ReminderAccess(
        allowed=plan_ok and discord_ok,
        plan_ok=plan_ok,
        discord_ok=discord_ok,
        reason=reason,
        detail=details[reason],
    )


def user_plan_allows_reminders(user) -> bool:
    """Whether a paid plan covers this user (their own, or a seat someone pays for)."""
    return has_feature(user, Feature.DEADLINE_REMINDERS)


def user_discord_linked(user) -> bool:
    """Whether the user has an ACTIVE Discord identity Mylo could DM."""
    return discord_resolve.active_identity_for_user(user) is not None


def personal_reminder_access(user) -> ReminderAccess:
    """Whether ``user`` may set a reminder for themselves (DM delivery)."""
    return _build(
        user_plan_allows_reminders(user), user_discord_linked(user), _DETAIL
    )


def lab_plan_allows_reminders(lab) -> bool:
    """Whether the lab's own (or its department's) plan includes reminders."""
    return lab_has_feature(lab, Feature.DEADLINE_REMINDERS)


def lab_discord_linked(lab) -> bool:
    """Whether the lab has a live Discord server bound.

    ``PENDING_SETUP`` does not count: the bot is in the guild but no manager has
    claimed the link, so posting to it would be unauthorized-by-omission. A
    ``KICKED`` link is plainly dead. The *channel* binding is deliberately not
    required — a reminder with no announcement channel still writes its in-app
    notification, and ``/setup`` can bind the channel later without invalidating
    reminders already set.
    """
    return discord_resolve.lab_guild_is_active(lab)


def lab_reminder_access(lab) -> ReminderAccess:
    """Whether reminders may be set for ``lab`` (channel delivery).

    Authorization (who may act *for* the lab) is a separate question answered by
    ``user_can_edit_lab_profile``; this is only about the lab's capability.
    """
    return _build(lab_plan_allows_reminders(lab), lab_discord_linked(lab), _LAB_DETAIL)
