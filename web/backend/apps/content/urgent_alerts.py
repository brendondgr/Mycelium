"""The one message a weekly-cadence reader gets between Mondays.

Choosing Weekly means "do not interrupt me". Honouring that absolutely would
mean a deadline moving from November to next Friday on something the reader
saved goes unmentioned for six days, by which time it is not worth mentioning.
That is the single case where silence costs something irreversible, and it is the
only exception (open decision OD2).

Every clause of the rule is load-bearing, and the rule is narrow on purpose:

* **Opt-in.** ``WatchPreference.urgent_alerts``, off by default. Nobody is
  surprised by a message they asked not to receive.
* **Weekly cadence only.** A daily-cadence reader hears about a moved deadline in
  the next morning's daily, so a second message would be the same news twice.
* **Between Mondays only.** ``push_kinds`` answers ``URGENT`` for a weekly-cadence
  reader on any day that is not their Monday, and this reads that answer rather
  than deciding its own. Monday itself carries the weekly, which already says it.
* **A deadline that actually moved**, on an item the reader **saved**, due inside
  their **own buffer**. Three filters, and the alert engine already applies all
  three — this module sends what ``deadline_moved`` fired, it does not re-derive
  the rule.
* **Once per alert, forever.** The dedupe key is the alert's own identity, not
  the day, so a deadline that is re-read every night raises one message and a
  deadline that moves twice raises two.

It is not a small daily. It carries one embed, no attachment, and no statistics:
a reader who asked not to be interrupted is being interrupted, and the message
should cost them one glance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from tools.retrieval.models import ProjectAlert

from apps.content import delivery
from apps.content.alert_report import TRIGGER_LABELS, block_for
from apps.content.reminders_discord import BRAND_COLOR, escape_mentions

logger = logging.getLogger(__name__)

TITLE = "A deadline moved on something you saved"


@dataclass
class UrgentSummary:
    considered: int = 0
    sent: int = 0
    unreachable: int = 0
    errors: int = 0
    error_detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "considered": self.considered,
            "sent": self.sent,
            "unreachable": self.unreachable,
            "errors": self.errors,
        }


def urgent_embed(alert: ProjectAlert) -> dict:
    """One moved deadline, in one glance.

    No statistics and no attachment. A reader who asked not to be interrupted is
    being interrupted; the message owes them the fact and nothing else.
    """
    block = block_for(alert)
    evidence = alert.evidence or {}
    direction = "earlier" if evidence.get("moved_earlier") else "later"
    days = evidence.get("days")
    when = (
        f"{days} day{'' if days == 1 else 's'} away"
        if isinstance(days, int)
        else "soon"
    )
    linked = (
        f"[{escape_mentions(block.title)}]({block.url})"
        if block.url
        else escape_mentions(block.title)
    )
    return {
        "title": TITLE,
        "description": (
            f"{linked} — its deadline moved {direction}, from "
            f"{evidence.get('previous_due_date', '—')} to "
            f"{evidence.get('due_date', '—')}. That is {when}."
        ),
        "color": BRAND_COLOR,
        "footer": {
            "text": (
                f"{block.project_label} · "
                f"{TRIGGER_LABELS.get(alert.trigger, alert.trigger)} · "
                "you asked to hear about these between weeklies"
            )
        },
    }


def eligible_alerts(user, *, on: date) -> list[ProjectAlert]:
    """This person's un-delivered urgent alerts, if they are due one at all.

    Returns nothing — without touching the database — for anyone whose cadence,
    opt-in or weekday says no. The cadence matrix is asked rather than
    re-implemented, so "no weekend messages" stays one rule in one place.
    """
    kinds = delivery.push_kinds(
        delivery.user_cadence(user),
        on,
        urgent_opt_in=delivery.user_urgent_alerts(user),
    )
    if delivery.URGENT not in kinds:
        return []
    return list(
        ProjectAlert.objects.filter(
            target_user=user,
            trigger=ProjectAlert.Trigger.DEADLINE_MOVED,
            status=ProjectAlert.Status.OPEN,
            fired_on=on,
        ).select_related("project", "content")
    )


def send_urgent_alerts(
    usernames: list[str] | None = None, *, on: date | None = None
) -> UrgentSummary:
    """Queue every due urgent alert. Never raises."""
    from tools.recommendation.tasks import select_users

    from apps.content.reminders_discord import send_personal_report

    summary = UrgentSummary()
    for user in select_users(usernames):
        local_date = on or delivery.local_today(user)
        for alert in eligible_alerts(user, on=local_date):
            summary.considered += 1
            try:
                outcome = send_personal_report(
                    user,
                    title=TITLE,
                    body="",
                    filename="",
                    attachment_path="",
                    # Keyed on the alert, not the day: a deadline re-read every
                    # night raises one message, and one that moves twice raises
                    # two.
                    dedupe_key=delivery.urgent_alert_key(user, str(alert.id)),
                    kind="urgent_alert",
                    embed=urgent_embed(alert),
                    not_before=delivery.send_time(user, local_date),
                )
            except Exception as exc:  # noqa: BLE001 — one reader never sinks it
                summary.errors += 1
                summary.error_detail.append(f"{user.get_username()}: {exc}")
                logger.warning("urgent alert failed for %s", user, exc_info=True)
                continue
            if getattr(outcome, "ok", False):
                summary.sent += 1
                alert.delivered_in = [
                    *(alert.delivered_in or []),
                    f"urgent:{local_date.isoformat()}",
                ]
                alert.save(update_fields=["delivered_in", "updated_at"])
            else:
                summary.unreachable += 1
    return summary
