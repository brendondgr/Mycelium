"""Is Mylo making correct changes? The measures and the harm checks (Plan 10).

Everything here is a query over what the feature already records — the
labelled answers (``ValidationRecord``), the changes that took effect
(``AppliedChange``), the questions (``PendingSuggestion``), the observations
and the retractions. Nothing is sampled or estimated, and nothing reads a
person's words: there are none to read.

**Measures** (reported, no bar here — the bars live in each experiment's
protocol):

- *Validation precision* — of the questions answered yes or no, the share
  answered yes, by understanding kind, by force, by where it was heard, by
  lab, and by where it was answered. The primary number: a kind with low
  precision gets a higher floor or stops being asked.
- *Maintenance burden* — profile edits per person, questions asked against
  answered, and the undo rate on confirmed changes.

**Harm checks** — each must be zero. Each returns its count and up to five
example ids, never text.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import (
    AppliedChange,
    Observation,
    PendingSuggestion,
    Retraction,
    ValidationRecord,
)

YES = ("confirmed", "corrected")
NO = ("rejected",)

#: Changes a person made by acting on the web ("include it after all") are
#: their own confirmation; everything else needs an answered question, an
#: accepted proposal, or to be a fact they told Mylo.
_WEB_ACTIONS = ("exploration_confirmed", "exploration_kept", "exploration_dropped")

#: A quotation long enough to be somebody's words rather than a term.
_QUOTED = re.compile(r"[\"“]([^\"”]{30,})[\"”]")


def _rate(yes: int, no: int) -> float | None:
    return round(yes / (yes + no), 4) if yes + no else None


# -- measures ------------------------------------------------------------------


def validation_precision(*, since=None, until=None) -> dict:
    """Of the answers that were a yes or a no, the share that was yes."""
    records = ValidationRecord.objects.all()
    if since is not None:
        records = records.filter(created_at__gte=since)
    if until is not None:
        records = records.filter(created_at__lt=until)
    records = list(records.select_related("suggestion", "suggestion__finding"))
    observations = _observations_for(records)

    groups: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    totals = Counter()
    for record in records:
        totals[record.verdict] += 1
        if record.verdict not in YES + NO:
            continue
        answer = "yes" if record.verdict in YES else "no"
        rows = observations.get(record.pk, [])
        keys = {
            "kind": record.understanding_kind or record.kind,
            "surface": record.surface or "unknown",
            "force": _dominant(row.force for row in rows),
            "heard_in": _dominant(row.place_kind for row in rows),
            "lab": _dominant(
                getattr(row.source, "lab_id", None) or "none" for row in rows
            ),
        }
        for dimension, value in keys.items():
            groups[dimension][str(value)][answer] += 1
    yes = sum(totals[v] for v in YES)
    no = sum(totals[v] for v in NO)
    return {
        "precision": _rate(yes, no),
        "answered_yes": yes,
        "answered_no": no,
        "verdicts": dict(totals),
        "by": {
            dimension: {
                value: {
                    "yes": counts["yes"],
                    "no": counts["no"],
                    "precision": _rate(counts["yes"], counts["no"]),
                }
                for value, counts in sorted(values.items())
            }
            for dimension, values in groups.items()
        },
    }


def _observations_for(records) -> dict[int, list]:
    wanted: dict[int, list[int]] = {}
    for record in records:
        finding = (
            getattr(record.suggestion, "finding", None)
            if record.suggestion_id
            else None
        )
        ids = list(getattr(finding, "observation_ids", None) or [])
        if not ids:
            ids = list((record.finding_snapshot or {}).get("observation_ids") or [])
        wanted[record.pk] = ids
    every = {i for ids in wanted.values() for i in ids}
    rows = {
        row.pk: row
        for row in Observation.objects.filter(pk__in=every).select_related("source")
    }
    return {pk: [rows[i] for i in ids if i in rows] for pk, ids in wanted.items()}


def _dominant(values) -> str:
    counts = Counter(str(value) for value in values if value)
    return counts.most_common(1)[0][0] if counts else "unknown"


def maintenance(*, since, until) -> dict:
    """Edits, questions and undos over a window."""
    edits = AppliedChange.objects.filter(
        kind=AppliedChange.Kind.PROFILE_EDIT,
        created_at__gte=since,
        created_at__lt=until,
    )
    people = edits.values("user").distinct().count()
    days = max((until - since).days, 1)
    asked = PendingSuggestion.objects.filter(asked_at__gte=since, asked_at__lt=until)
    confirming = AppliedChange.objects.filter(
        created_at__gte=since, created_at__lt=until
    ).exclude(kind=AppliedChange.Kind.UNDONE)
    return {
        "profile_edits": edits.count(),
        "people_with_edits": people,
        "profile_edits_per_person_per_30d": (
            round(edits.count() / people * 30 / days, 3) if people else None
        ),
        "questions_asked": asked.count(),
        "questions_answered": asked.filter(
            state=PendingSuggestion.State.ANSWERED
        ).count(),
        "changes": confirming.count(),
        "changes_undone": confirming.filter(undone_at__isnull=False).count(),
        "undo_rate": (
            round(
                confirming.filter(undone_at__isnull=False).count() / confirming.count(),
                4,
            )
            if confirming.count()
            else None
        ),
    }


# -- harm checks ---------------------------------------------------------------


def _result(ids) -> dict:
    ids = list(ids)
    return {"count": len(ids), "examples": ids[:5]}


def stated_field_without_a_yes() -> dict:
    """A profile or project-state edit with no yes behind it."""
    bad = AppliedChange.objects.filter(
        Q(kind=AppliedChange.Kind.PROFILE_EDIT)
        & (
            Q(suggestion__isnull=True)
            | ~Q(suggestion__verdict__in=YES)
            | ~Q(suggestion__state=PendingSuggestion.State.ANSWERED)
        )
        | Q(kind=AppliedChange.Kind.STATE_EDIT, proposal_id="")
    )
    return _result(bad.values_list("pk", flat=True))


def change_without_a_confirmation() -> dict:
    """Anything that took effect with no answered yes, accepted proposal, web
    action of the person's own, or fact they told Mylo."""
    ok = (
        # Stated-field edits are the stricter check above; counting them here
        # too would count one violation twice (EXP-2026-09-018, before its run).
        Q(kind__in=[AppliedChange.Kind.PROFILE_EDIT, AppliedChange.Kind.STATE_EDIT])
        | Q(
            suggestion__verdict__in=YES,
            suggestion__state=PendingSuggestion.State.ANSWERED,
        )
        | ~Q(proposal_id="")
        | Q(kind__in=_WEB_ACTIONS, surface="web")
        | Q(kind=AppliedChange.Kind.DEVELOPMENT_RECORDED, surface="told")
        | Q(kind=AppliedChange.Kind.UNDONE)
        # "Keep" and "let go" answer a review question; a no is the answer.
        | Q(kind=AppliedChange.Kind.EXPLORATION_DROPPED, suggestion__state="answered")
    )
    return _result(AppliedChange.objects.exclude(ok).values_list("pk", flat=True))


def personal_in_lab_reports(lab_reports=None) -> dict:
    """A personal change's row in any lab report's "What changed".

    ``lab_reports`` is ``[(id, body)]`` — the content side passes the stored
    lab reports in, because this app may not import it. ``None`` means the
    check was not run, which is reported rather than counted as zero.
    """
    if lab_reports is None:
        return {"count": None, "examples": [], "not_run": True}
    personal = list(
        AppliedChange.objects.filter(
            Q(visibility="personal")
            | Q(
                kind__in=[
                    "exploration_confirmed",
                    "exploration_kept",
                    "exploration_dropped",
                    "understanding_confirmed",
                    "profile_edit",
                ]
            )
        ).values_list("pk", "topic")
    )
    lab_visible = set(
        AppliedChange.objects.filter(visibility="lab").values_list("topic", flat=True)
    )
    bad = []
    for briefing_id, body in lab_reports:
        rows = _what_changed_rows(body or "")
        for pk, topic in personal:
            if topic in lab_visible:
                continue  # the same words may be a lab change's too
            if any(_row_is_about(row, topic) for row in rows):
                bad.append(f"briefing:{briefing_id}:change:{pk}")
    return _result(bad)


def _what_changed_rows(body: str) -> list[str]:
    lines = body.splitlines()
    rows: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line.strip() in ("## What changed", "## Needs your attention")
            continue
        if inside and line.startswith("- "):
            rows.append(line)
    return rows


def _row_is_about(row: str, topic: str) -> bool:
    return f"**{topic}** —" in row or f"— {topic} —" in row or f"({topic})" in row


def questions_over_the_daily_cap() -> dict:
    """More questions asked of one person on one day than the cap allows."""
    cap = int(getattr(settings, "AMBIENT_QUESTIONS_PER_DAY", 2))
    per_day = Counter(
        (user_id, timezone.localtime(asked_at).date())
        for user_id, asked_at in PendingSuggestion.objects.filter(
            asked_at__isnull=False
        ).values_list("user_id", "asked_at")
    )
    return _result(
        f"user:{user}:{day.isoformat()}:{n}"
        for (user, day), n in per_day.items()
        if n > cap
    )


def quoted_words_outside_the_buffer() -> dict:
    """A long quotation in anything Mylo wrote down — the one place somebody's
    words could have leaked into the durable record."""
    from .models import Finding

    bad = [
        f"observation:{pk}"
        for pk, text, explanation in Observation.objects.values_list(
            "pk", "text", "explanation"
        )
        if _QUOTED.search(text or "") or _QUOTED.search(explanation or "")
    ]
    bad += [
        f"finding:{pk}"
        for pk, text in Finding.objects.exclude(explanation="").values_list(
            "pk", "explanation"
        )
        if _QUOTED.search(text or "")
    ]
    return _result(bad)


def observations_after_opt_out() -> dict:
    """An observation from before an opt-out-with-deletion that still exists."""
    bad = []
    for retraction in Retraction.objects.filter(
        reason=Retraction.Reason.OPT_OUT, user__isnull=False
    ):
        bad += [
            f"observation:{pk}"
            for pk in Observation.objects.filter(
                speaker_id=retraction.user_id, recorded_at__lt=retraction.created_at
            ).values_list("pk", flat=True)
        ]
    return _result(bad)


def observations_of_unlinked_people() -> dict:
    """An observation about a Discord speaker who never linked an identity.

    (A person who lapsed to a free tier keeps what Mylo understood, paused, by
    design; so the tier half of this check is a count, not a violation.)
    """
    from apps.integrations.models import DiscordIdentity

    linked = set(DiscordIdentity.objects.values_list("user_id", flat=True))
    bad = (
        Observation.objects.filter(source__kind__startswith="discord")
        .exclude(speaker_id__in=linked)
        .values_list("pk", flat=True)
    )
    return _result(bad)


def free_tier_speakers() -> dict:
    """People with observations whose effective tier is now free (paused)."""
    from django.contrib.auth.models import User

    from .eligibility import tier_is_paid

    speakers = User.objects.filter(
        pk__in=Observation.objects.values("speaker_id").distinct()
    )
    return _result(f"user:{user.pk}" for user in speakers if not tier_is_paid(user))


def declined_asked_again_within_30_days() -> dict:
    """A topic someone said no to, asked again inside the rest."""
    rest = timedelta(days=30)
    noes = PendingSuggestion.objects.filter(
        verdict__in=NO, answered_at__isnull=False, concept__isnull=False
    ).values_list("pk", "user_id", "concept_id", "relation", "answered_at")
    bad = []
    for pk, user, concept, relation, answered_at in noes:
        again = PendingSuggestion.objects.filter(
            user_id=user,
            concept_id=concept,
            relation=relation,
            asked_at__gt=answered_at,
            asked_at__lt=answered_at + rest,
        ).exclude(pk=pk)
        bad += [f"suggestion:{other}" for other in again.values_list("pk", flat=True)]
    return _result(bad)


def covered_topic_asked() -> dict:
    """A question about something the person had already declared, or their
    papers already show, when it was asked."""
    from django.contrib.auth.models import User

    from apps.knowledge.read import own_edges

    bad = []
    rows = list(
        PendingSuggestion.objects.filter(
            asked_at__isnull=False,
            concept__isnull=False,
            kind__in=["interest", "skill"],
        ).values_list("pk", "user_id", "concept_id", "asked_at")
    )
    held: dict[int, dict[int, object]] = {}
    for user in User.objects.filter(pk__in={row[1] for row in rows}):
        # Read through the knowledge core's door: the earliest declared or
        # demonstrated edge per concept, whatever the relation — the same
        # rule deliberation uses before asking.
        first: dict[int, object] = {}
        for edge in own_edges(user):
            if edge.tier in ("declared", "demonstrated"):
                seen = first.get(edge.concept_id)
                if seen is None or edge.first_seen < seen:
                    first[edge.concept_id] = edge.first_seen
        held[user.pk] = first
    for pk, user_id, concept_id, asked_at in rows:
        since = held.get(user_id, {}).get(concept_id)
        if since is not None and since < asked_at:
            bad.append(f"suggestion:{pk}")
    return _result(bad)


def rule_written_observations() -> dict:
    """An observation not written by the model (no rule fallback, by design)."""
    return _result(
        Observation.objects.filter(origin="rule").values_list("pk", flat=True)
    )


HARM_CHECKS = {
    "stated_field_without_a_yes": stated_field_without_a_yes,
    "change_without_a_confirmation": change_without_a_confirmation,
    "personal_in_lab_reports": personal_in_lab_reports,
    "questions_over_the_daily_cap": questions_over_the_daily_cap,
    "quoted_words_outside_the_buffer": quoted_words_outside_the_buffer,
    "observations_after_opt_out": observations_after_opt_out,
    "observations_of_unlinked_people": observations_of_unlinked_people,
    "declined_asked_again_within_30_days": declined_asked_again_within_30_days,
    "covered_topic_asked": covered_topic_asked,
    "rule_written_observations": rule_written_observations,
}


def harm_checks(*, lab_reports=None) -> dict:
    out = {
        name: (check(lab_reports) if name == "personal_in_lab_reports" else check())
        for name, check in HARM_CHECKS.items()
    }
    out["_total"] = sum(result["count"] or 0 for result in out.values())
    out["_info"] = {"free_tier_speakers_paused": free_tier_speakers()}
    return out


def report(*, since=None, until=None, lab_reports=None) -> dict:
    """The whole evaluation: measures and harm checks, as one JSON-able dict."""
    until = until or timezone.now()
    since = since or until - timedelta(days=28)
    return {
        "window": [since.isoformat(), until.isoformat()],
        "validation_precision": validation_precision(since=since, until=until),
        "maintenance": maintenance(since=since, until=until),
        "harm_checks": harm_checks(lab_reports=lab_reports),
    }
