"""Re-render and re-deliver one target's daily report, on demand.

The nightly chain sends every eligible reader their report once. This is the
operator's way to send *one* of them again — after a bad run, a fixed profile, a
Discord outage, or simply to see what a given person actually receives.

Two flows, deliberately named apart, because they are not the same delivery:

* :func:`resend_user_report` — a **DM** to one person.
* :func:`repost_lab_report` — a **post** to one lab's bound updates channel.

Both do the whole job rather than just re-queuing yesterday's bytes: the written
briefing is regenerated over the target's current Top-25, the PDF is rendered from
that, and the result is queued. ``regenerate=False`` keeps the stored briefing when
the point is to re-deliver exactly what was written earlier.

**Why the old commands appeared to do nothing.** ``send_daily_discord_reports
--user x`` and ``send_lab_digests --lab y`` both existed and both ran clean. The
outbox is idempotent on ``dedupe_key``, and the daily key is ``…:<today>``, so a
same-day re-send re-found the row that had already been delivered that morning,
queued nothing, and reported success. These flows take their own key
(:func:`apps.integrations.services.resolve.next_resend_key`) so a re-send is a real
send.

**What still stops a send, loudly.** A reader who has no Discord identity, has
opted out, or is on a plan without scheduled reports does not get one — those are
their decisions, not the operator's. The difference from before is that each is
*reported* as the reason rather than silently reducing the recipient list to zero.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class ResendOutcome:
    """What happened, in enough detail for an operator to act on it."""

    key: str  # username or lab slug
    kind: str  # "user" | "lab"
    ok: bool = False
    #: Why it did not send. Empty when it did.
    blocked_by: str = ""
    regenerated: bool = False
    briefing_origin: str = ""
    pdf_path: str = ""
    dedupe_key: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    new_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "target": self.key,
            "kind": self.kind,
            "ok": self.ok,
            "blocked_by": self.blocked_by,
            "regenerated": self.regenerated,
            "briefing_origin": self.briefing_origin,
            "pdf_path": self.pdf_path,
            "dedupe_key": self.dedupe_key,
            "top_25_shown": self.counts,
            "entered_today": self.new_counts,
        }

    def summary(self) -> str:
        if self.ok:
            shown = sum(self.counts.values())
            entered = sum(self.new_counts.values())
            return (
                f"{self.key}: queued — {shown} item(s) across the top lists, "
                f"{entered} of them new today ({self.dedupe_key})"
            )
        return f"{self.key}: not sent — {self.blocked_by}"


def _report_dir(override: str | None = None) -> Path:
    """Where the rendered PDF waits for the drain (the shared outbox directory)."""
    if override:
        return Path(override)
    return Path(getattr(settings, "DISCORD_OUTBOX_ATTACHMENT_DIR", "data/outbox"))


def _shown_per_category(data) -> dict[str, int]:
    """How many items the reader's own part of the report actually lists."""
    part = data.personal
    return {} if part is None else {c: len(items) for c, items in part.items.items()}


def _write_pdf(workdir: Path, filename: str, pdf: bytes) -> Path:
    """Stage the PDF and move it into place.

    The path is deterministic per (target, day), so a re-send would otherwise
    truncate a file the drain might be reading at that moment. ``os.replace`` is
    atomic, so a reader sees one whole PDF or the other, never half of each.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / filename
    staged = path.with_name(path.name + ".part")
    staged.write_bytes(pdf)
    os.replace(staged, path)
    return path


# --------------------------------------------------------------------------- #
# A person: re-render and re-send the DM
# --------------------------------------------------------------------------- #
def resend_user_report(
    user,
    *,
    regenerate: bool = True,
    dry_run: bool = False,
    report_dir: str | None = None,
    complete=None,
) -> ResendOutcome:
    """Re-render one person's daily report and DM it to them again.

    Returns a :class:`ResendOutcome` rather than raising: an operator running this
    over a handful of people wants to see which ones were blocked and why, not to
    have the first blocked one end the command.
    """
    from apps.billing.entitlements import Feature, has_feature
    from apps.content import reminders_discord
    from apps.content.briefing import generate_briefing_for_user
    from apps.content.daily_report import compile_report_for_user
    from apps.content.daily_report_pdf import render_report_pdf
    from apps.content.daily_report_send import REPORT_TITLE
    from apps.integrations.services import resolve

    outcome = ResendOutcome(key=user.get_username(), kind="user")

    if not has_feature(user, Feature.SCHEDULED_REPORTS):
        outcome.blocked_by = (
            "their plan does not include scheduled reports, so Mylo does not push "
            "them a run"
        )
        return outcome
    if not resolve.report_recipient_user_ids([user]):
        outcome.blocked_by = (
            "no active Discord identity, opted out of the daily report, or a DM "
            "Discord has already refused"
        )
        return outcome

    if regenerate:
        briefing = generate_briefing_for_user(user, complete=complete)
        outcome.regenerated = True
        outcome.briefing_origin = briefing.origin

    data = compile_report_for_user(user)
    outcome.briefing_origin = outcome.briefing_origin or data.briefing_origin
    outcome.counts = _shown_per_category(data)
    outcome.new_counts = dict(data.personal.counts) if data.personal else {}

    filename = f"mylo-report-{user.get_username()}-{data.generated_on}.pdf"
    if dry_run:
        outcome.ok = False
        outcome.blocked_by = "dry run — rendered but not queued"
        outcome.pdf_path = str(_report_dir(report_dir) / filename)
        return outcome

    path = _write_pdf(_report_dir(report_dir), filename, render_report_pdf(data))
    outcome.pdf_path = str(path)
    outcome.dedupe_key = resolve.next_resend_key(
        f"daily_report:{user.id}:{data.generated_on}"
    )

    sent = reminders_discord.send_personal_report(
        user,
        title=REPORT_TITLE,
        body=data.summary_line() + "\nYour full report is attached as a PDF.",
        filename=filename,
        attachment_path=str(path),
        dedupe_key=outcome.dedupe_key,
    )
    outcome.ok = bool(getattr(sent, "ok", False))
    if not outcome.ok:
        # Nothing was queued, so nothing will ever read the file — drop it now
        # rather than leave it for a sweep that only knows about outbox rows.
        path.unlink(missing_ok=True)
        outcome.blocked_by = "Discord would not accept the DM (see the outbox log)"
    return outcome


# --------------------------------------------------------------------------- #
# A lab: re-render and re-post to the updates channel
# --------------------------------------------------------------------------- #
def repost_lab_report(
    lab,
    *,
    on: date | None = None,
    regenerate: bool = True,
    dry_run: bool = False,
    report_dir: str | None = None,
    complete=None,
) -> ResendOutcome:
    """Re-render one lab's daily report and post it to its updates channel again.

    The counts summary the nightly digest posts above the PDF is *not* re-posted: it
    describes the same day and would read as a second morning. What an operator is
    re-sending is the report.
    """
    from apps.billing.entitlements import Feature, lab_has_feature
    from apps.content.briefing import generate_briefing_for_lab
    from apps.content.daily_report import compile_report_for_lab
    from apps.content.daily_report_pdf import render_report_pdf
    from apps.content.lab_digest import REPORT_MESSAGE, report_filename
    from apps.integrations.services import outbox, resolve

    on = on or timezone.localdate()
    outcome = ResendOutcome(key=lab.slug, kind="lab")

    if not lab_has_feature(lab, Feature.BOT_SERVER):
        outcome.blocked_by = "the lab's plan does not include the Discord bot add-on"
        return outcome
    link = resolve.get_guild_link_for_lab(lab)
    if link is None or link.state != resolve.GUILD_ACTIVE:
        outcome.blocked_by = "the lab's Discord server link is not active"
        return outcome
    channel_id = resolve.get_updates_channel_for_lab(lab)
    if not channel_id:
        # A blank binding is a deliberate opt-out, and the nightly digest respects it
        # in silence. An operator who asked for this send is owed the reason.
        outcome.blocked_by = "the lab has no updates channel bound (run /setup)"
        return outcome

    if regenerate:
        briefing = generate_briefing_for_lab(lab, complete=complete)
        outcome.regenerated = True
        outcome.briefing_origin = briefing.origin

    data = compile_report_for_lab(lab)
    outcome.briefing_origin = outcome.briefing_origin or data.briefing_origin
    outcome.counts = _shown_per_category(data)
    outcome.new_counts = dict(data.personal.counts) if data.personal else {}

    filename = report_filename(lab, on)
    if dry_run:
        outcome.blocked_by = "dry run — rendered but not queued"
        outcome.pdf_path = str(_report_dir(report_dir) / filename)
        return outcome

    path = _write_pdf(_report_dir(report_dir), filename, render_report_pdf(data))
    outcome.pdf_path = str(path)
    outcome.dedupe_key = resolve.next_resend_key(
        f"lab_report:{lab.id}:{on:%Y-%m-%d}"
    )

    _row, created = outbox.enqueue_channel(
        dedupe_key=outcome.dedupe_key,
        kind="lab_report",
        channel_id=channel_id,
        lab=lab,
        content=REPORT_MESSAGE,
        attachment_path=str(path),
        attachment_filename=path.name,
        subject_type="lab_report",
        subject_id=str(lab.id),
    )
    outcome.ok = bool(created)
    if not outcome.ok:
        path.unlink(missing_ok=True)
        outcome.blocked_by = "the outbox already holds an identical queued row"
    return outcome
