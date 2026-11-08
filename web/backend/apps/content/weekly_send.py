"""Deliver the Monday weekly to Discord — a DM, and a lab's channel.

The cadence matrix (:mod:`apps.content.delivery`) says Monday is the weekly for
**both** cadences, which is what makes the weekly the one message every reader
gets: a weekly-cadence reader's only Discord message of the week, and a
daily-cadence reader's Monday, in place of that day's daily rather than beside it
(invariant 3).

Everything else is the daily's machinery, deliberately: the same outbox, the same
``not_before`` holding the row until the recipient's local morning, the same
attachment directory and retention sweep, the same dedupe-key idempotency. A
second delivery path for a second report is a second set of bugs.

The one thing that is not shared is the dedupe key, which is keyed on the week's
**Monday** rather than on the day the send ran. A weekly re-run on Tuesday after
an outage re-finds Monday's row instead of queueing a second copy of the week.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from apps.content import delivery, discord_embeds, reminders_discord
from apps.content.daily_report import compile_report_for_lab, compile_report_for_user
from apps.content.daily_report_pdf import render_report_pdf
from apps.integrations.services import outbox, resolve

logger = logging.getLogger(__name__)

WEEKLY_TITLE = "Your weekly research report"
LAB_WEEKLY_MESSAGE = "This week's full report is attached."


@dataclass
class WeeklySendSummary:
    eligible: int = 0
    sent: int = 0
    unreachable: int = 0
    errors: int = 0
    error_detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "sent": self.sent,
            "unreachable": self.unreachable,
            "errors": self.errors,
        }


def _report_dir() -> Path:
    from apps.content.daily_report_send import _report_dir as shared

    return shared()


def eligible_weekly_recipients(usernames: list[str] | None, *, on: date | None = None):
    """Who gets a weekly DM this Monday.

    The same four gates as the daily, with the cadence one asking for the weekly
    instead — so this is the weekly-cadence readers, and only them. A daily
    subscriber's Monday is a daily like any other day; the weekly is the *other*
    option at sign-up, not a thing that lands on top of the one they chose.
    """
    from tools.recommendation.tasks import select_users

    users = select_users(usernames)
    due = [
        user
        for user in users
        if delivery.WEEKLY
        in delivery.push_kinds(
            delivery.user_cadence(user), on or delivery.local_today(user)
        )
    ]
    reachable = resolve.report_recipient_user_ids(due)
    return [user for user in due if user.id in reachable]


def _weekly_body(user_or_lab, *, is_lab: bool):
    """The report data behind the weekly's post, with the weekly body attached.

    The document is the daily renderer over the weekly's markdown, which is the
    plan's own choice (6.3): the two reports share a grammar and a layout, and a
    second renderer would drift from the first within a release.
    """
    from tools.retrieval.models import DailyBriefing

    data = (
        compile_report_for_lab(user_or_lab)
        if is_lab
        else compile_report_for_user(user_or_lab)
    )
    owner = {"lab": user_or_lab} if is_lab else {"user": user_or_lab}
    weekly = DailyBriefing.latest_for(DailyBriefing.Kind.WEEKLY, **owner)
    if weekly is not None:
        data.briefing_markdown = weekly.body
        data.briefing_origin = weekly.origin
    return data, weekly


def send_weekly_discord_reports(
    usernames: list[str] | None = None,
    *,
    on: date | None = None,
    log=logger.info,
) -> WeeklySendSummary:
    """Queue every eligible person's weekly. Never raises."""
    summary = WeeklySendSummary()
    recipients = eligible_weekly_recipients(usernames, on=on)
    summary.eligible = len(recipients)
    if not recipients:
        return summary

    workdir = _report_dir()
    workdir.mkdir(parents=True, exist_ok=True)
    for user in recipients:
        try:
            local_date = on or delivery.local_today(user)
            monday = _monday(local_date)
            data, weekly = _weekly_body(user, is_lab=False)
            if weekly is None:
                # No weekly was written for this Monday. Sending the daily under
                # a weekly heading would be a worse answer than silence.
                summary.unreachable += 1
                continue
            filename = f"mylo-weekly-{user.get_username()}-{monday:%Y-%m-%d}.pdf"
            path = workdir / filename
            _write(path, render_report_pdf(data))
            outcome = reminders_discord.send_personal_report(
                user,
                title=WEEKLY_TITLE,
                body=data.message_body(),
                filename=filename,
                attachment_path=str(path),
                dedupe_key=delivery.weekly_report_key(user, monday),
                kind="weekly_report",
                embed=discord_embeds.personal_report_embed(
                    data, data.stats, "weekly", alerts=_alerts({"target_user": user})
                ),
                not_before=delivery.send_time(user, local_date),
            )
            if getattr(outcome, "ok", False):
                summary.sent += 1
            else:
                path.unlink(missing_ok=True)
                summary.unreachable += 1
        except Exception as exc:  # noqa: BLE001 — one reader never sinks the batch
            summary.errors += 1
            summary.error_detail.append(f"{user.get_username()}: {exc}")
            logger.warning("weekly send failed for %s", user, exc_info=True)
    log(f"weekly report: {summary.sent} queued, {summary.unreachable} unreachable")
    return summary


def send_lab_weeklies(labs, *, on: date | None = None) -> WeeklySendSummary:
    """Queue every eligible lab's weekly to its channel. Never raises."""
    from apps.content.lab_digest import eligible_labs

    summary = WeeklySendSummary()
    eligible = eligible_labs(labs, on=on, kind=delivery.WEEKLY)
    summary.eligible = len(eligible)
    if not eligible:
        return summary

    workdir = _report_dir()
    workdir.mkdir(parents=True, exist_ok=True)
    for lab in eligible:
        try:
            local_date = on or delivery.local_today(lab)
            monday = _monday(local_date)
            channel_id = resolve.get_updates_channel_for_lab(lab)
            if not channel_id:
                summary.unreachable += 1
                continue
            data, weekly = _weekly_body(lab, is_lab=True)
            if weekly is None:
                summary.unreachable += 1
                continue
            outbox.enqueue_channel(
                dedupe_key=delivery.lab_weekly_key(lab, monday),
                kind="lab_weekly",
                channel_id=channel_id,
                lab=lab,
                embed=discord_embeds.lab_post_embed(
                    data, data.stats, "weekly", alerts=_alerts({"target_lab": lab})
                ),
                subject_type="lab_weekly",
                subject_id=str(lab.id),
                not_before=delivery.send_time(lab, local_date),
            )
            filename = f"mylo-weekly-{lab.slug}-{monday:%Y-%m-%d}.pdf"
            path = workdir / filename
            _write(path, render_report_pdf(data))
            outbox.enqueue_channel(
                # A distinct key from the post above, or the attachment would
                # dedupe against it and never be queued at all.
                dedupe_key=f"{delivery.lab_weekly_key(lab, monday)}:pdf",
                kind="lab_weekly",
                channel_id=channel_id,
                lab=lab,
                content=LAB_WEEKLY_MESSAGE,
                attachment_path=str(path),
                attachment_filename=path.name,
                subject_type="lab_weekly",
                subject_id=str(lab.id),
                # One second later, so the outbox — which claims by
                # (next_attempt_at, id) — posts the file under the post it
                # belongs to once both are held for the same local hour.
                not_before=delivery.send_time(lab, local_date)
                + timedelta(seconds=1),
            )
            summary.sent += 1
        except Exception as exc:  # noqa: BLE001
            summary.errors += 1
            summary.error_detail.append(f"{lab.slug}: {exc}")
            logger.warning("lab weekly send failed for %s", lab, exc_info=True)
    return summary


def _alerts(target_filter: dict):
    """This week's open alerts, as the post's attention lines."""
    from apps.content.alert_report import block_for, discord_lines, open_alerts

    return discord_lines([block_for(alert) for alert in open_alerts(target_filter)])


def _monday(value: date) -> date:
    from apps.content.weekly_build import week_start

    return week_start(value)


def _write(path: Path, payload: bytes) -> None:
    """Atomic, because the path is deterministic per (target, week).

    A re-run would otherwise truncate a file the drain might be reading at that
    moment; ``os.replace`` means a reader sees one whole PDF or the other, never
    half of each.
    """
    staged = path.with_name(path.name + ".part")
    staged.write_bytes(payload)
    os.replace(staged, path)
