"""Tests for fellowship ingest: upsert, first_seen immutability, prune.

Injected embedder (no fastembed), in-memory Django DB (pytest-django @django_db),
no network.

Relocated from ``test_pivot_ingest.py``'s ``ingest_pivot`` fellowship coverage
(plan Phase 6 — the deletion of Pivot-RP): ``ingest_pivot`` used to handle both
Pivot's grant/conference upserts and the Illinois Fellowship Finder's, keyed on
the same ``(source, external_id)`` upsert and the same type-scoped
``prune_expired``. Now that grants/conferences ingest through the open
collector's own ``tools.retrieval.collect.ingest`` (plan Phase 4), this module
exercises the fellowship-only slice — :func:`tools.retrieval.fellowships.ingest
.ingest_fellowships` — and the cross-type prune coverage through
``tools.retrieval.collect.ingest.prune_expired``, the one ``prune_expired`` every
opportunity type converges on regardless of which module upserted it.
"""

import pytest

from tools.retrieval.collect.ingest import prune_expired
from tools.retrieval.fellowships.ingest import ingest_fellowships
from tools.retrieval.models import ContentItem

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


def _grant_item(gid="g1", source="grants:test", *, prune_after="2027-01-01"):
    """A ``ContentItem`` grant row, built directly — this file only exercises the
    fellowship ingest path; grants are seeded straight through the ORM to test
    cross-type prune coverage without pulling in the collector's own mapper."""
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source=source,
        external_id=gid,
        metadata={"title": f"Test Grant {gid}", "prune_after": prune_after},
    )


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fellowship_ingest_creates_with_illinois_source():
    summary = ingest_fellowships(
        [_fellowship()],
        embedder=_fake_embedder,
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


# ---------------------------------------------------------------------------
# first_seen immutability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_seen_immutable_across_fellowship_reingest():
    ingest_fellowships([_fellowship()], embedder=_fake_embedder, today=TODAY)
    first = ContentItem.objects.get(external_id="f1").metadata["first_seen"]

    # Re-ingest same id with a changed field.
    ingest_fellowships(
        [_fellowship(title="Changed Title")], embedder=_fake_embedder, today=TODAY
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
    ingest_fellowships(
        [
            _fellowship("future", deadline_date="2026-12-01"),
            _fellowship("past", deadline_date="2025-01-01"),
            _fellowship("rolling", deadline_type="rolling", deadline_date=""),
            _fellowship("continuous", deadline_type="continuous", deadline_date=""),
        ],
        embedder=_fake_embedder,
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
def test_prune_covers_both_grants_and_fellowships():
    """``tools.retrieval.collect.ingest.prune_expired`` is type-scoped, so a grant
    row (upserted by an entirely different module) and a fellowship row (upserted
    here) are both covered by the one call — the convergence plan Phase 4/6 exist
    to guarantee."""
    _grant_item("gpast", prune_after="2025-01-01")
    _grant_item("gfuture", prune_after="2027-01-01")
    ingest_fellowships(
        [
            _fellowship("fpast", deadline_date="2025-01-01"),
            _fellowship("ffuture", deadline_date="2027-01-01"),
        ],
        embedder=_fake_embedder,
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

    summary = ingest_fellowships([grant_rec], embedder=_fake_embedder, today=TODAY)
    assert summary.created == 0
    assert summary.skipped == 1
    assert ContentItem.objects.filter(external_id="gfellowship").count() == 0
