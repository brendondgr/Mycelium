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
