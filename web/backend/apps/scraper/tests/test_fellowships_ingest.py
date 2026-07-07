"""Tests for fellowship ingest: upsert, first_seen immutability, prune.

Uses the same pattern as ``test_pivot_ingest.py`` — injected embedder (no
fastembed), in-memory Django DB (pytest-django @django_db), no network.

Verifies the generalized source field: fellowships use
``source="illinois-fellowship-finder"`` while grants still use ``source="pivot"``.
"""

import pytest

from apps.content.models import ContentItem
from apps.scraper.pivot.ingest import ingest_pivot, prune_expired

TODAY = "2026-07-06"

ILLINOIS_SOURCE = "illinois-fellowship-finder"


def _fake_embedder(texts):
    return [[float(len(t)), 1.0, 2.0] for t in texts]


def _fellowship(fid="f1", deadline_type="true", deadline_date="2026-12-01", **over):
    """Minimal fellowship record matching the illinois output shape."""
    rec = {
        "id": fid,
        "source": ILLINOIS_SOURCE,
        "source_url": f"https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/{fid}",
        "external_url": "https://example.com/fellowship",
        "title": f"Test Fellowship {fid}",
        "award_class": "fellowship",
        "deadline": {
            "type": deadline_type,
            "date": deadline_date,
            "previous_date": "",
            "raw": deadline_date,
        },
        "award_amount": {
            "kind": "exact",
            "currency": "USD",
            "min": 10000,
            "max": 10000,
            "raw": "$10,000",
            "note": "",
        },
        "eligibility": ["Must be enrolled in a doctoral program."],
        "facets": {
            "field": ["Humanities"],
            "citizenship": ["US Citizens, Nationals, or Permanent Residents"],
            "stage": ["Dissertation Research"],
            "award_type": ["Fellowship/Grant"],
            "limits": [],
            "other": [],
        },
        "flags": {
            "requires_us_citizenship": True,
            "open_to_international": False,
            "masters": False,
            "doctoral": True,
            "postdoc": False,
        },
        "description": "A test fellowship for doctoral students.",
        "blurb": "Fellowship for doctoral students.",
        "note": "",
        "contact_email": "info@example.com",
        "scraped_at": "2026-07-06T00:00:00+00:00",
    }
    rec.update(over)
    return rec


def _grant(gid="g1", deadline_date="2026-11-12"):
    """A minimal Pivot grant record (source="pivot")."""
    return {
        "id": gid,
        "title": "Test Grant",
        "sponsor": "Test Sponsor",
        "amount": "$50,000",
        "website": "https://example.com",
        "deadline": "12 Nov 2026",
        "deadline_date": deadline_date,
        "matched_topics": "AI",
        "ai_summary": "",
        "abstract": "",
        "url": f"https://pivot.proquest.com/funding_opps/{gid}",
    }


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fellowship_ingest_creates_with_illinois_source():
    summary = ingest_pivot(
        [("fellowships", _fellowship())],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    assert summary.created == 1
    assert summary.embedded == 1

    obj = ContentItem.objects.get(external_id="f1")
    assert obj.type == ContentItem.Type.FELLOWSHIP
    assert obj.source == ILLINOIS_SOURCE
    assert obj.metadata["award_class"] == "fellowship"
    assert obj.metadata["first_seen"]
    assert obj.embedding is not None


@pytest.mark.django_db
def test_grant_uses_pivot_source():
    summary = ingest_pivot(
        [("grants", _grant())],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    assert summary.created == 1
    obj = ContentItem.objects.get(external_id="g1")
    assert obj.source == "pivot"


@pytest.mark.django_db
def test_mixed_ingest_different_sources():
    summary = ingest_pivot(
        [
            ("grants", _grant()),
            ("fellowships", _fellowship()),
        ],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    assert summary.created == 2
    assert ContentItem.objects.filter(source="pivot").count() == 1
    assert ContentItem.objects.filter(source=ILLINOIS_SOURCE).count() == 1


# ---------------------------------------------------------------------------
# first_seen immutability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_seen_immutable_across_fellowship_reingest():
    ingest_pivot(
        [("fellowships", _fellowship())],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    first = ContentItem.objects.get(external_id="f1").metadata["first_seen"]

    # Re-ingest same id with a changed field.
    ingest_pivot(
        [("fellowships", _fellowship(title="Changed Title"))],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    obj = ContentItem.objects.get(external_id="f1")
    assert obj.metadata["first_seen"] == first  # immutable
    assert obj.metadata["title"] == "Changed Title"  # other fields update
    assert ContentItem.objects.filter(external_id="f1").count() == 1  # no duplicate


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prune_removes_expired_true_fellowship():
    ingest_pivot(
        [
            ("fellowships", _fellowship("future", deadline_date="2026-12-01")),
            ("fellowships", _fellowship("past", deadline_date="2025-01-01")),
            ("fellowships", _fellowship(
                "rolling", deadline_type="rolling", deadline_date=""
            )),
            ("fellowships", _fellowship(
                "continuous", deadline_type="continuous", deadline_date=""
            )),
        ],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    removed = prune_expired(today=TODAY)
    assert removed == 1  # only "past" had prune_after in the past

    remaining = set(
        ContentItem.objects.filter(source=ILLINOIS_SOURCE).values_list(
            "external_id", flat=True
        )
    )
    assert "future" in remaining
    assert "rolling" in remaining
    assert "continuous" in remaining
    assert "past" not in remaining


@pytest.mark.django_db
def test_prune_covers_both_sources():
    ingest_pivot(
        [
            ("grants", _grant("gpast", deadline_date="2025-01-01")),
            ("fellowships", _fellowship("fpast", deadline_date="2025-01-01")),
            ("grants", _grant("gfuture", deadline_date="2027-01-01")),
            ("fellowships", _fellowship("ffuture", deadline_date="2027-01-01")),
        ],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    removed = prune_expired(today=TODAY)
    assert removed == 2  # one past grant + one past fellowship

    remaining = set(ContentItem.objects.values_list("external_id", flat=True))
    assert "gfuture" in remaining
    assert "ffuture" in remaining
    assert "gpast" not in remaining
    assert "fpast" not in remaining


# ---------------------------------------------------------------------------
# grant exclusion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_grant_class_fellowships_excluded_at_ingest():
    grant_rec = _fellowship("gfellowship")
    grant_rec["award_class"] = "grant"

    summary = ingest_pivot(
        [("fellowships", grant_rec)],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    assert summary.created == 0
    assert summary.skipped == 1
    assert ContentItem.objects.filter(external_id="gfellowship").count() == 0
