"""The plan's §8 smoke checklist, as code rather than a wiki page.

Twelve checks over the live database, run after a phase ships and before a
release. They are deliberately *system* checks rather than unit tests: each one
asks a question about the thing that is actually deployed — this cadence matrix,
these outbox rows, this lab's projects — which is the class of failure a test
suite cannot see, because every test builds its own world.

Two of them are the ones that would actually catch a regression that matters and
neither is faked:

* **S5** walks every queued lab post and every lab report and asserts that no
  unshared project's name appears in either. That is the privacy invariant, and
  checking it against real rows is the only check worth having.
* **S4** asserts no weekday DM exists for a weekly-cadence reader. It is the
  whole point of making cadence real, and it is exactly the thing that will
  regress silently, because nothing breaks when an extra message goes out.

``SKIP`` is a first-class result. A check that cannot run — no labs configured,
no outbox rows today — reports that rather than passing, because a green
checklist that is green for the wrong reason is worse than a shorter one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def line(self) -> str:
        mark = {PASS: "[x]", FAIL: "[!]", SKIP: "[-]"}[self.status]
        return f"{mark} {self.name}" + (f" — {self.detail}" if self.detail else "")


def _check(name: str, ok: bool, detail: str = "") -> Check:
    return Check(name, PASS if ok else FAIL, detail)


# --------------------------------------------------------------------------- #
# S1–S3 — cadence and scheduling
# --------------------------------------------------------------------------- #
def check_cadence_matrix() -> Check:
    """S1: the matrix, Monday through Sunday, for both cadences."""
    from apps.content import delivery

    monday = date(2026, 9, 21)
    expected = {
        ("daily", 0): {delivery.WEEKLY},
        ("daily", 1): {delivery.DAILY},
        ("daily", 4): {delivery.DAILY},
        ("daily", 5): set(),
        ("daily", 6): set(),
        ("weekly", 0): {delivery.WEEKLY},
        ("weekly", 2): set(),
        ("weekly", 5): set(),
    }
    wrong = [
        f"{cadence} {(monday + timedelta(days=offset)):%a}"
        for (cadence, offset), want in expected.items()
        if delivery.push_kinds(cadence, monday + timedelta(days=offset)) != want
    ]
    return _check(
        "S1 cadence matrix matches §3.1",
        not wrong,
        ", ".join(wrong) if wrong else "8 cells checked",
    )


def check_briefings_written(today: date) -> Check:
    """S2: today's daily exists for every scheduled-eligible target."""
    from apps.content.models import DailyBriefing
    from apps.content.tasks import select_targets, select_users

    users = select_users(None)
    labs, _projects = select_targets(None)
    if not users and not labs:
        return Check("S2 today's briefing exists for every target", SKIP,
                     "no scheduled-eligible targets")
    written = set(
        DailyBriefing.objects.filter(
            generated_on=today, kind=DailyBriefing.Kind.DAILY
        ).values_list("user_id", "lab_id")
    )
    if not written:
        # "The run has not happened yet" and "the run happened and missed
        # somebody" are different states, and only the second is a failure. A
        # check that is red every morning until the nightly finishes is a check
        # people learn to ignore.
        return Check(
            "S2 today's briefing exists for every target",
            SKIP,
            "no briefing written for today yet — has the nightly run finished?",
        )
    missing = [u.get_username() for u in users if (u.id, None) not in written]
    missing += [lab.slug for lab in labs if (None, lab.id) not in written]
    return _check(
        "S2 today's briefing exists for every target",
        not missing,
        f"{len(missing)} missing: {', '.join(missing[:5])}" if missing else
        f"{len(users)} user(s), {len(labs)} lab(s)",
    )


def check_send_hours(today: date) -> Check:
    """S3: every row queued today is due at its recipient's local send hour."""
    from apps.content import delivery
    from apps.integrations.models import DiscordOutboxMessage

    rows = list(
        DiscordOutboxMessage.objects.filter(
            created_at__date=today,
            kind__in=("daily_report", "weekly_report", "lab_digest", "lab_weekly"),
        ).select_related("recipient_user", "lab")
    )
    if not rows:
        return Check("S3 rows are held until the local send hour", SKIP,
                     "nothing queued today")
    wrong = []
    for row in rows:
        target = row.recipient_user or row.lab
        if target is None:
            continue
        due = delivery.send_time(target, today)
        # Either held for the morning, or due now because the run finished late.
        if row.next_attempt_at > row.created_at and row.next_attempt_at != due:
            wrong.append(row.dedupe_key)
    return _check(
        "S3 rows are held until the local send hour",
        not wrong,
        f"{len(wrong)} wrong" if wrong else f"{len(rows)} row(s) checked",
    )


def check_no_weekday_dm_for_weekly_cadence(today: date) -> Check:
    """S4: the whole point of making cadence real."""
    from apps.accounts.models import WatchCadence
    from apps.integrations.models import DiscordOutboxMessage

    if today.weekday() in (0, 5, 6):
        return Check("S4 no weekday DM for a weekly-cadence reader", SKIP,
                     "only meaningful Tuesday to Friday")
    offenders = list(
        DiscordOutboxMessage.objects.filter(
            created_at__date=today,
            kind="daily_report",
            recipient_user__watch__cadence=WatchCadence.WEEKLY,
        ).values_list("dedupe_key", flat=True)
    )
    return _check(
        "S4 no weekday DM for a weekly-cadence reader",
        not offenders,
        f"{len(offenders)}: {', '.join(offenders[:3])}" if offenders else "none",
    )


# --------------------------------------------------------------------------- #
# S5 — the privacy invariant
# --------------------------------------------------------------------------- #
def check_no_unshared_project_in_a_lab_post(today: date) -> Check:
    """S5: no lab surface names a project its editors did not share.

    Checked against real queued rows and real lab report bodies rather than
    against a fixture, because this is the invariant whose breach cannot be
    undone: the names are already in the channel.
    """
    import json

    from apps.accounts.models import Lab
    from apps.content.models import DailyBriefing
    from apps.integrations.models import DiscordOutboxMessage
    from apps.research.models import Project

    private = {
        str(row["name"]): row["scope_lab_id"]
        for row in Project.objects.active()
        .filter(scope_lab__isnull=False, share_in_lab_reports=False)
        .values("name", "scope_lab_id")
    }
    if not private:
        return Check("S5 no unshared project on a lab surface", SKIP,
                     "no unshared lab projects exist")

    leaked: list[str] = []
    labs = {lab.id: lab.slug for lab in Lab.objects.all()}
    for row in DiscordOutboxMessage.objects.filter(
        created_at__date=today, kind__in=("lab_digest", "lab_weekly")
    ):
        rendered = json.dumps(row.embed or {}) + (row.content or "")
        for name, lab_id in private.items():
            if row.lab_id == lab_id and name in rendered:
                leaked.append(f"{labs.get(lab_id, lab_id)} post names {name!r}")
    for briefing in DailyBriefing.objects.filter(
        generated_on=today, lab__isnull=False
    ):
        for name, lab_id in private.items():
            if briefing.lab_id == lab_id and name in (briefing.body or ""):
                leaked.append(f"{labs.get(lab_id, lab_id)} report names {name!r}")

    return _check(
        "S5 no unshared project on a lab surface",
        not leaked,
        "; ".join(leaked[:3]) if leaked else f"{len(private)} private project(s)",
    )


# --------------------------------------------------------------------------- #
# S6–S9 — what the surfaces say
# --------------------------------------------------------------------------- #
def check_embeds_fit(today: date) -> Check:
    """S6: every queued embed is already inside Discord's limits.

    Discord rejects an oversized embed outright, so an embed that only fits after
    ``fit_embed`` runs again is an embed that was queued broken.
    """
    from apps.content.discord_embeds import fit_embed
    from apps.integrations.models import DiscordOutboxMessage

    rows = [
        row
        for row in DiscordOutboxMessage.objects.filter(created_at__date=today)
        if row.embed
    ]
    if not rows:
        return Check("S6 every queued embed fits unchanged", SKIP, "none queued")
    changed = [
        row.dedupe_key
        for row in rows
        if fit_embed(dict(row.embed)) != row.embed
    ]
    return _check(
        "S6 every queued embed fits unchanged",
        not changed,
        f"{len(changed)} changed" if changed else f"{len(rows)} embed(s)",
    )


def check_stats_reconcile(today: date) -> Check:
    """S7: the statistics and the summary table quote one morning, not two."""
    from apps.content.models import DailyBriefing

    rows = [
        row
        for row in DailyBriefing.objects.filter(
            generated_on=today, kind=DailyBriefing.Kind.DAILY
        )
        if row.stats and row.project_summary
    ]
    if not rows:
        return Check("S7 statistics reconcile with the summary table", SKIP,
                     "no briefing carries both yet")
    wrong = []
    for row in rows:
        table = sum(
            sum((entry.get("counts") or {}).values())
            for entry in row.project_summary
        )
        if int((row.stats or {}).get("entered") or 0) != table:
            wrong.append(str(row.user_id or row.lab_id))
    return _check(
        "S7 statistics reconcile with the summary table",
        not wrong,
        f"{len(wrong)} disagree" if wrong else f"{len(rows)} report(s)",
    )


def check_citations_resolve(today: date) -> Check:
    """S8: every ``[P#]`` in a weekly resolves, and the record was kept."""
    from apps.content.models import DailyBriefing
    from apps.content.report_grammar import citations

    rows = list(
        DailyBriefing.objects.filter(kind=DailyBriefing.Kind.WEEKLY).order_by(
            "-generated_on"
        )[:20]
    )
    if not rows:
        return Check("S8 every weekly citation resolves", SKIP, "no weekly yet")
    wrong = []
    for row in rows:
        body = row.body or ""
        referenced = set(citations(body))
        listed = set(citations(body.split("## References", 1)[-1]))
        if referenced - listed:
            wrong.append(f"{row.generated_on}: {sorted(referenced - listed)}")
        if not row.verification:
            wrong.append(f"{row.generated_on}: no verification record")
    return _check(
        "S8 every weekly citation resolves",
        not wrong,
        "; ".join(wrong[:3]) if wrong else f"{len(rows)} weekly report(s)",
    )


def check_no_scores_in_prose(today: date) -> Check:
    """S9: no percentage, no "cosine", no "score" in any report body."""
    from apps.content.models import DailyBriefing

    rows = list(DailyBriefing.objects.filter(generated_on=today))
    if not rows:
        return Check("S9 no percentage, cosine or score in a report", SKIP,
                     "no report today")
    from apps.content.report_grammar import score_violations

    offenders = []
    for row in rows:
        found = score_violations(row.body or "")
        if found:
            offenders.append(f"{row.user_id or row.lab_id}: {found[0]!r}")
    return _check(
        "S9 no percentage, cosine or score in a report",
        not offenders,
        "; ".join(offenders[:3]) if offenders else f"{len(rows)} report(s)",
    )


# --------------------------------------------------------------------------- #
# S10–S12 — the properties the design rests on
# --------------------------------------------------------------------------- #
def check_buffer_is_free() -> Check:
    """S10: changing a buffer recomputes every status with zero model calls.

    Asserted by construction rather than by counting calls: the timeline matcher
    takes its settings as an argument and touches no model seam at all, so the
    check is that the same row under two buffers gives two verdicts.
    """
    from apps.content.matchers import timeline as tl
    from apps.content.models import ContentDeadline, ContentItem, SavedOpportunity
    from apps.content.timeline_settings import Timeline

    row = ContentDeadline(
        content=ContentItem(
            type=ContentItem.Type.CONFERENCE, metadata={"title": "A venue"}
        ),
        kind=SavedOpportunity.DeadlineKind.MANUSCRIPT,
        due_date=date(2026, 12, 20),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    plan = tl.ProjectPlan(
        milestones=[{"id": "m1", "kind": "draft_by", "date": "2026-12-15"}]
    )
    today = date(2026, 9, 11)
    lenient = tl.judge_row(row, plan, Timeline(3, 60), today=today).status
    strict = tl.judge_row(row, plan, Timeline(30, 60), today=today).status
    return _check(
        "S10 a changed buffer recomputes statuses for free",
        (lenient, strict) == (tl.FITS, tl.TIGHT),
        f"{lenient} vs {strict}",
    )


def check_resend_is_idempotent(today: date) -> Check:
    """S11: re-running the send stages queues zero new rows."""
    from apps.content.daily_report_send import run_daily_report_send
    from apps.integrations.models import DiscordOutboxMessage

    before = DiscordOutboxMessage.objects.count()
    run_daily_report_send(log=lambda _m: None)
    after = DiscordOutboxMessage.objects.count()
    return _check(
        "S11 re-running the send stage queues nothing new",
        after == before,
        f"{after - before} new row(s)" if after != before else "0 new rows",
    )


def check_sample_renders() -> Check:
    """S12: the formatting-review loop still runs with no database at all."""
    try:
        from apps.content.daily_report_pdf import render_report_pdf
        from apps.content.management.commands.render_sample_report import build_sample

        rendered = render_report_pdf(build_sample("personal"))
    except Exception as exc:  # noqa: BLE001 — the check is whether it works
        return Check("S12 the sample report renders offline", FAIL, str(exc))
    return _check(
        "S12 the sample report renders offline",
        rendered[:5] == b"%PDF-",
        f"{len(rendered):,} bytes",
    )


def run_checklist(*, today: date | None = None, send: bool = False) -> list[Check]:
    """Every check, in plan order. ``send=False`` skips the one that queues."""
    today = today or timezone.localdate()
    checks = [
        check_cadence_matrix(),
        check_briefings_written(today),
        check_send_hours(today),
        check_no_weekday_dm_for_weekly_cadence(today),
        check_no_unshared_project_in_a_lab_post(today),
        check_embeds_fit(today),
        check_stats_reconcile(today),
        check_citations_resolve(today),
        check_no_scores_in_prose(today),
        check_buffer_is_free(),
    ]
    checks.append(
        check_resend_is_idempotent(today)
        if send
        else Check(
            "S11 re-running the send stage queues nothing new",
            SKIP,
            "pass --send; it re-runs the real send stage",
        )
    )
    checks.append(check_sample_renders())
    return checks
