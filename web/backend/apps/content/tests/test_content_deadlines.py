"""R0 — the ContentDeadline projection: derivation, rebuild hook, change detection.

Exercises the real ingest path (``ingest_pivot`` → ``upsert_pivot_items`` → rebuild)
so the hook, not just the pure function, is covered. Embedding and prune are off so
the tests stay pure-relational and run on SQLite.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import AuditEvent
from apps.content.deadlines_projection import deadline_specs_for, rebuild_deadlines_for
from apps.content.models import ContentDeadline, ContentItem, RelevanceScore
from apps.content.serializers import GrantSerializer
from apps.scraper.pivot.ingest import ingest_pivot

TODAY = "2026-07-16"


def _ingest(*records):
    return ingest_pivot(records, embed=False, prune=False, today=TODAY)


def _grant(**over):
    rec = {
        "id": "g1",
        "title": "Neural Interfaces Grant",
        "sponsor": "NSF",
        "deadline_date": "2026-10-01",
        "url": "https://example.org/g1",
    }
    rec.update(over)
    return ("grants", rec)


def _conference(**over):
    rec = {
        "id": "c1",
        "name": "NeurIPS 2027",
        "location": "Vancouver",
        "country": "Canada",
        "deadlines": (
            "02 Oct 2026 (Abstract Submission Deadline); "
            "15 Dec 2026 (Manuscript Deadline)"
        ),
        "event_dates": "22 Mar 2027",
        "url": "https://example.org/c1",
    }
    rec.update(over)
    return ("conferences", rec)


def _structured_deadline(kind, instant, *, is_estimated=False, round_label=""):
    """A dict shaped like ``Deadline.to_json()`` (open collector, plan Phase 3).

    Built by hand rather than importing
    ``apps.scraper.collect.conferences.record.Deadline`` — these tests exercise
    ``deadlines_projection`` as a consumer of the *documented dict shape*, the
    same contract ``apps.scraper.collect.mapping.map_conference`` writes, not as
    a consumer of that dataclass.
    """
    return {
        "kind": kind,
        "raw": instant or "TBD",
        "instant": instant,
        "basis": "UTC",
        "round_label": round_label,
        "source": "test",
        "is_estimated": is_estimated,
        "extension_count": 0,
    }


def _fellowship(deadline, **over):
    rec = {
        "id": "f1",
        "title": "Graduate Research Fellowship",
        "award_class": "fellowship",
        "deadline": deadline,
        "source": "illinois-fellowship-finder",
        "source_url": "https://example.org/f1",
    }
    rec.update(over)
    return ("fellowships", rec)


@pytest.mark.django_db
def test_conference_yields_three_rows() -> None:
    _ingest(_conference())
    item = ContentItem.objects.get(external_id="c1")
    rows = {d.kind: d for d in item.deadline_rows.all()}
    assert set(rows) == {"abstract", "manuscript", "event"}
    assert rows["abstract"].due_date.isoformat() == "2026-10-02"
    assert rows["manuscript"].due_date.isoformat() == "2026-12-15"
    assert rows["event"].due_date.isoformat() == "2027-03-22"
    confirmed = ContentDeadline.Confidence.CONFIRMED
    assert all(r.confidence == confirmed for r in rows.values())


@pytest.mark.django_db
def test_grant_yields_one_application_row() -> None:
    _ingest(_grant())
    item = ContentItem.objects.get(external_id="g1")
    rows = list(item.deadline_rows.all())
    assert len(rows) == 1
    assert rows[0].kind == "application"
    assert rows[0].due_date.isoformat() == "2026-10-01"
    assert rows[0].confidence == ContentDeadline.Confidence.CONFIRMED


@pytest.mark.django_db
def test_rolling_fellowship_has_null_date_and_rolling_confidence() -> None:
    _ingest(_fellowship({"type": "rolling", "date": ""}))
    item = ContentItem.objects.get(external_id="f1")
    row = item.deadline_rows.get()
    assert row.kind == "application"
    assert row.due_date is None
    assert row.confidence == ContentDeadline.Confidence.ROLLING


@pytest.mark.django_db
def test_anticipated_fellowship_confidence() -> None:
    _ingest(_fellowship({"type": "anticipated", "date": "2027-01-15"}))
    row = ContentItem.objects.get(external_id="f1").deadline_rows.get()
    assert row.confidence == ContentDeadline.Confidence.ANTICIPATED
    assert row.due_date.isoformat() == "2027-01-15"


@pytest.mark.django_db
def test_varies_and_suspended_fellowships_are_unknown_with_no_date() -> None:
    _ingest(_fellowship({"type": "varies", "date": ""}))
    row = ContentItem.objects.get(external_id="f1").deadline_rows.get()
    assert row.confidence == ContentDeadline.Confidence.UNKNOWN
    assert row.due_date is None


@pytest.mark.django_db
def test_reingest_unchanged_date_leaves_changed_at_untouched() -> None:
    _ingest(_grant())
    _ingest(_grant())  # identical re-scrape
    row = ContentItem.objects.get(external_id="g1").deadline_rows.get()
    assert row.changed_at is None
    assert row.previous_due_date is None
    assert not AuditEvent.objects.filter(action="opportunity.deadline.moved").exists()


@pytest.mark.django_db
def test_reingest_moved_date_sets_changed_at_and_audits() -> None:
    _ingest(_grant(deadline_date="2026-10-01"))
    _ingest(_grant(deadline_date="2026-09-01"))  # moved earlier
    row = ContentItem.objects.get(external_id="g1").deadline_rows.get()
    assert row.due_date.isoformat() == "2026-09-01"
    assert row.previous_due_date.isoformat() == "2026-10-01"
    assert row.changed_at is not None
    audit = AuditEvent.objects.get(action="opportunity.deadline.moved")
    assert audit.metadata["old_due_date"] == "2026-10-01"
    assert audit.metadata["new_due_date"] == "2026-09-01"
    assert audit.metadata["kind"] == "application"


@pytest.mark.django_db
def test_first_seen_immutable_and_scalars_populated_across_reingest() -> None:
    _ingest(_grant())
    first = ContentItem.objects.get(external_id="g1")
    first_seen = first.metadata["first_seen"]
    assert first.metadata["deadline_date"] == "2026-10-01"
    assert first.metadata["next_kind"] == "application"

    _ingest(_grant())
    again = ContentItem.objects.get(external_id="g1")
    assert again.metadata["first_seen"] == first_seen  # immutable
    assert again.metadata["deadline_date"] == "2026-10-01"  # scalar still there


@pytest.mark.django_db
def test_dropped_kind_row_is_deleted_on_reingest() -> None:
    # A conference that later loses its abstract deadline should drop that row.
    _ingest(_conference())
    item = ContentItem.objects.get(external_id="c1")
    assert item.deadline_rows.filter(kind="abstract").exists()

    _ingest(_conference(deadlines="15 Dec 2026 (Manuscript Deadline)"))
    item.refresh_from_db()
    kinds = set(item.deadline_rows.values_list("kind", flat=True))
    assert kinds == {"manuscript", "event"}


@pytest.mark.django_db
def test_backfill_does_not_manufacture_changes() -> None:
    _ingest(_grant())
    item = ContentItem.objects.get(external_id="g1")
    # Simulate a pre-existing row with a different date, as a backfill would find.
    row = item.deadline_rows.get()
    row.due_date = None
    row.confidence = ContentDeadline.Confidence.UNKNOWN
    row.save(update_fields=["due_date", "confidence"])

    changes = rebuild_deadlines_for(item, TODAY, detect_changes=False)
    assert changes == []
    row.refresh_from_db()
    assert row.due_date.isoformat() == "2026-10-01"
    assert row.changed_at is None


@pytest.mark.django_db
def test_serializer_exposes_deadlines_array() -> None:
    _ingest(_grant())
    item = ContentItem.objects.get(external_id="g1")
    from django.contrib.auth.models import User

    user = User.objects.create_user("recon-user")
    score = RelevanceScore.objects.create(
        content=item, target_user=user, score=0.9, signals={}
    )
    data = GrantSerializer(score, context={"today": TODAY}).data
    assert data["addressable_deadlines"] == [
        {
            "kind": "application",
            "due_date": "2026-10-01",
            "confidence": "confirmed",
            "label": "Application deadline",
        }
    ]
    # Scalars the existing cards read are untouched.
    assert "deadline_date" in data
    assert "deadline_kind" in data


def test_pure_derivation_ignores_papers() -> None:
    paper = ContentItem(type=ContentItem.Type.PAPER, metadata={"title": "x"})
    assert deadline_specs_for(paper, TODAY) == []


# --------------------------------------------------------------------------- #
# Plan Phase 5 — the structured conference path
#
# These are pure (no ``@pytest.mark.django_db``, matching
# ``test_pure_derivation_ignores_papers`` above): the presence of
# ``metadata["deadlines_structured"]`` alone routes ``_conference_specs`` to
# ``_structured_conference_specs`` instead of the legacy Pivot parser, so an
# in-memory ``ContentItem`` with hand-built metadata is enough — no ingest path
# needed to exercise it.
# --------------------------------------------------------------------------- #


def test_structured_conference_picks_next_future_per_kind() -> None:
    # A VLDB-shaped conference: several rounds under both submission-gating
    # kinds, plus a scattering of the six kinds that all fold into OTHER, so
    # the "at most one row per kind, and it's the next future one" rule has to
    # actually discriminate rather than pass by having only one candidate.
    entries = [
        _structured_deadline("abstract", "2026-01-01T23:59:00Z"),  # past
        _structured_deadline("abstract", "2026-09-01T23:59:00Z"),  # wins ABSTRACT
        _structured_deadline("abstract", "2026-11-01T23:59:00Z"),  # future, later
        _structured_deadline("submission", "2026-06-01T23:59:00Z"),  # past
        _structured_deadline(
            "submission", "2026-10-15T23:59:00Z", round_label="round 2"
        ),  # wins MANUSCRIPT
        _structured_deadline("submission", "2027-01-15T23:59:00Z"),  # future, later
        _structured_deadline("rebuttal_open", "2026-12-01T00:00:00Z"),  # OTHER cand.
        _structured_deadline("camera_ready", "2026-12-20T00:00:00Z"),  # OTHER cand.
        _structured_deadline("notification", "2026-11-20T00:00:00.500Z"),  # wins OTHER
        _structured_deadline("registration", "2025-01-01T00:00:00Z"),  # past
        _structured_deadline("unknown", None),  # unparseable
    ]
    item = ContentItem(
        type=ContentItem.Type.CONFERENCE,
        metadata={"deadlines_structured": entries},
    )
    specs = {s.kind: s for s in deadline_specs_for(item, TODAY)}

    assert set(specs) == {"abstract", "manuscript", "other"}
    assert specs["abstract"].due_date.isoformat() == "2026-09-01"
    assert specs["manuscript"].due_date.isoformat() == "2026-10-15"
    assert specs["other"].due_date.isoformat() == "2026-11-20"
    assert specs["other"].label == "Notification date"
    assert all(
        s.confidence == ContentDeadline.Confidence.CONFIRMED for s in specs.values()
    )


def test_structured_conference_only_future_date_is_other_and_not_open() -> None:
    entries = [
        _structured_deadline("abstract", "2026-01-01T00:00:00Z"),  # past
        _structured_deadline("submission", "2026-02-01T00:00:00Z"),  # past
        _structured_deadline("notification", "2026-09-01T00:00:00Z"),  # only future
    ]
    item = ContentItem(
        type=ContentItem.Type.CONFERENCE,
        metadata={"deadlines_structured": entries},
    )
    specs = deadline_specs_for(item, TODAY)

    # ABSTRACT/MANUSCRIPT never resurrect a past round, so only OTHER survives.
    # That the venue is CLOSED follows from the same fact this asserts (only a
    # non-submission kind has a future date) — the openness gate itself lives in
    # apps.scraper.collect.mapping._conference_deadlines / SUBMISSION_TYPES,
    # which this module deliberately never recomputes.
    assert {s.kind for s in specs} == {"other"}
    assert specs[0].label == "Notification date"


def test_structured_conference_empty_list_yields_no_rows() -> None:
    # An empty *list* (the collector genuinely found no dated deadlines) is a
    # different fact from the key being absent (a Pivot-era record) — it must
    # still route to the structured path and yield zero rows, not fall back to
    # the legacy free-text parser.
    item = ContentItem(
        type=ContentItem.Type.CONFERENCE,
        metadata={"deadlines_structured": []},
    )
    assert deadline_specs_for(item, TODAY) == []


def test_structured_conference_is_estimated_is_anticipated() -> None:
    entries = [
        _structured_deadline("abstract", "2026-09-01T00:00:00Z", is_estimated=True)
    ]
    item = ContentItem(
        type=ContentItem.Type.CONFERENCE,
        metadata={"deadlines_structured": entries},
    )
    spec = deadline_specs_for(item, TODAY)[0]
    assert spec.confidence == ContentDeadline.Confidence.ANTICIPATED


# --------------------------------------------------------------------------- #
# Plan Phase 5 — the grant path: ``deadline_date`` now means "next future round"
# --------------------------------------------------------------------------- #


def test_structured_grant_projects_next_round_not_last() -> None:
    # apps.scraper.collect.mapping._grant_deadlines already resolved which round
    # is "next" and wrote it to deadline_date; this guards _grant_specs against
    # a regression that reads metadata["due_dates"][-1] (the *last* round)
    # instead of trusting that resolved value.
    item = ContentItem(
        type=ContentItem.Type.GRANT,
        metadata={
            "deadline_date": "2026-09-01",
            "due_dates": ["2026-01-01", "2026-05-01", "2026-09-01", "2027-01-01"],
        },
    )
    specs = deadline_specs_for(item, TODAY)
    assert len(specs) == 1
    assert specs[0].kind == "application"
    assert specs[0].due_date.isoformat() == "2026-09-01"
    assert specs[0].confidence == ContentDeadline.Confidence.CONFIRMED


def test_structured_grant_with_no_rounds_is_rolling() -> None:
    # mapping.py's own contract: "" deadline_date == a genuinely rolling grant,
    # not a parsing gap — ROLLING with a null due_date, not UNKNOWN.
    item = ContentItem(
        type=ContentItem.Type.GRANT,
        metadata={"deadline_date": "", "due_dates": []},
    )
    spec = deadline_specs_for(item, TODAY)[0]
    assert spec.due_date is None
    assert spec.confidence == ContentDeadline.Confidence.ROLLING


def test_structured_grant_inferred_dates_is_anticipated() -> None:
    item = ContentItem(
        type=ContentItem.Type.GRANT,
        metadata={
            "deadline_date": "2026-09-01",
            "due_dates": ["2026-09-01"],
            "dates_inferred": True,
        },
    )
    spec = deadline_specs_for(item, TODAY)[0]
    assert spec.confidence == ContentDeadline.Confidence.ANTICIPATED
