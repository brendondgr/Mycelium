"""Pivot grants/conferences ingest — fully offline (injected embedder, no browser).

Covers the port contract (:mod:`apps.scraper.pivot.records`), the upsert with
immutable ``first_seen``, and the prune of expired items — the three guarantees
the daily job relies on.
"""

import pytest
from django.contrib.auth.models import User

from apps.content.models import ContentItem, SavedOpportunity
from apps.scraper.pivot.ingest import ingest_pivot, prune_expired, upsert_pivot_items
from apps.scraper.pivot.normalize import normalize_amount
from apps.scraper.pivot.records import build_pivot_item

# A grant that put a whole budget paragraph in its Amount field (the real NIH
# Common Fund UG3/UH3 case) — the amount distiller must reduce this to a range.
_BUDGET_PROSE = (
    "The NIH Common Fund intends to commit funds for approximately 6-8 UG3/UH3 "
    "awards. Applicants should request a budget appropriate for the proposed "
    "scope of work, not to exceed $450,000 in direct costs per year for UG3 and "
    "$800,000 for UH3 phases. The total project period may not exceed six years."
)

TODAY = "2026-07-05"


def _fake_embedder(texts):
    # Deterministic, dependency-free stand-in for fastembed.
    return [[float(len(t)), 1.0, 2.0] for t in texts]


def _grant(gid="g1", deadline_date="2026-11-12", **over):
    rec = {
        "id": gid,
        "title": "Amazon Agentic AI Research Award",
        "sponsor": "Amazon",
        "amount": "Upper: $70,000 USD",
        "website": "https://amazon.science/x",
        "deadline": "12 Nov 2026",
        "deadline_date": deadline_date,
        "matched_topics": "Agentic AI; Knowledge Graphs",
        "ai_summary": "Funds agentic AI for science.",
        "abstract": "Full opportunity abstract about agentic AI and knowledge graphs.",
        "url": f"https://pivot.proquest.com/funding_opps/{gid}",
    }
    rec.update(over)
    return rec


def _conference(
    cid="c1",
    event_dates="2026-11-13",
    deadlines="2026-09-10 (Abstract Submission Deadline)",
    **over,
):
    rec = {
        "id": cid,
        "name": "AI in Healthcare Special Session 2026",
        "location": "Boston",
        "country": "USA",
        "event_dates": event_dates,
        "deadlines": deadlines,
        "scope": "Applications of AI in medical and healthcare settings.",
        "website": "",
        "keywords": "AI; health care",
        "organizers": "",
        "eligibility": "",
        "matched_subjects": "Artificial Intelligence; Health Care",
        "url": f"https://pivot.proquest.com/papers_invited/{cid}",
        "timeline": [],
    }
    rec.update(over)
    return rec


def test_build_grant_item_maps_fields():
    item = build_pivot_item("grants", _grant(), today=TODAY)
    assert item.type == "grant"
    assert item.external_id == "g1"
    assert item.title == "Amazon Agentic AI Research Award"
    assert item.subtitle == "Amazon"
    assert item.metadata["amount"] == "Upper: $70,000 USD"
    assert item.metadata["deadline_date"] == "2026-11-12"
    assert item.metadata["prune_after"] == "2026-11-12"
    assert item.metadata["next_kind"] == "application"
    assert "agentic ai" in item.text.lower()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$450,000", "$450,000"),  # tidy value: unchanged
        ("Upper: $70,000 USD", "Upper: $70,000 USD"),  # short prose: kept
        ("", ""),
        (_BUDGET_PROSE, "$450,000–$800,000"),  # paragraph -> range
        ("$450,000–$800,000", "$450,000–$800,000"),  # idempotent
        ("$1.5 million", "$1.5 million"),  # short, unchanged
        (  # long prose, one figure -> single amount
            "Applicants may request up to $2,500,000 in total costs over the "
            "full multi-year project period, subject to available funds.",
            "$2,500,000",
        ),
        (  # long prose with a scale word
            "The foundation expects to make several awards and anticipates "
            "committing roughly $3.5 million per awardee across the program.",
            "$3,500,000",
        ),
        (  # long prose naming no dollar figure -> dropped
            "Budget guidance will be provided to invited applicants after the "
            "preliminary review stage is complete; see the full solicitation.",
            "",
        ),
    ],
)
def test_normalize_amount_distills_prose(raw, expected):
    assert normalize_amount(raw) == expected


def test_build_grant_item_distills_budget_paragraph():
    item = build_pivot_item("grants", _grant(amount=_BUDGET_PROSE), today=TODAY)
    # The stored amount is the concise range, and the paragraph never leaks into
    # the embedding/BM25 document text.
    assert item.metadata["amount"] == "$450,000–$800,000"
    assert "not to exceed" not in item.text
    assert "total project period" not in item.text.lower()


def test_build_conference_item_parses_deadline_and_event():
    item = build_pivot_item("conferences", _conference(), today=TODAY)
    assert item.type == "conference"
    assert item.subtitle == "Boston, USA"
    # actionable submission deadline (abstract) vs. event date (drives prune)
    assert item.metadata["deadline_date"] == "2026-09-10"
    assert item.metadata["next_kind"] == "abstract"
    assert item.metadata["event_date"] == "2026-11-13"
    assert item.metadata["prune_after"] == "2026-11-13"
    assert item.metadata["abstract_open"] is True


def test_build_item_skips_missing_id():
    assert build_pivot_item("grants", {"title": "no id"}, today=TODAY) is None


@pytest.mark.django_db
def test_ingest_creates_and_embeds():
    summary = ingest_pivot(
        [("grants", _grant()), ("conferences", _conference())],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    assert summary.created == 2
    assert summary.embedded == 2
    assert ContentItem.objects.filter(source="pivot").count() == 2
    grant = ContentItem.objects.get(external_id="g1")
    assert grant.type == ContentItem.Type.GRANT
    assert ContentItem.objects.get(external_id="c1").type == ContentItem.Type.CONFERENCE
    assert grant.embedding is not None
    assert grant.metadata["first_seen"]
    assert grant.metadata["search_text"]


@pytest.mark.django_db
def test_first_seen_immutable_across_reingest():
    ingest_pivot(
        [("grants", _grant())], embedder=_fake_embedder, prune=False, today=TODAY
    )
    first = ContentItem.objects.get(external_id="g1").metadata["first_seen"]

    # Re-ingest the same id (a later refresh) with a changed field.
    ingest_pivot(
        [("grants", _grant(amount="Upper: $99,000 USD"))],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    again = ContentItem.objects.get(external_id="g1")
    assert again.metadata["first_seen"] == first  # never reset
    assert again.metadata["amount"] == "Upper: $99,000 USD"  # other fields update
    assert ContentItem.objects.filter(external_id="g1").count() == 1  # upsert, no dup


@pytest.mark.django_db
def test_prune_removes_expired_keeps_future_and_unknown():
    ingest_pivot(
        [
            ("grants", _grant("future", deadline_date="2026-12-01")),
            ("grants", _grant("past", deadline_date="2025-01-01")),
            ("grants", _grant("nodate", deadline_date="")),
            ("conferences", _conference("conf_future", event_dates="2026-11-13")),
            ("conferences", _conference("conf_past", event_dates="2025-01-01")),
        ],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    removed = prune_expired(today=TODAY)
    assert removed == 2  # grant "past" + conference "conf_past"

    remaining = set(
        ContentItem.objects.filter(source="pivot").values_list("external_id", flat=True)
    )
    assert remaining == {"future", "nodate", "conf_future"}


@pytest.mark.django_db
def test_prune_preserves_saved_deadline_via_set_null():
    user = User.objects.create_user(username="r", password="p")
    ingest_pivot(
        [("grants", _grant("expiring", deadline_date="2025-01-01"))],
        embedder=_fake_embedder,
        prune=False,
        today=TODAY,
    )
    item = ContentItem.objects.get(external_id="expiring")
    saved = SavedOpportunity.objects.create(
        user=user,
        content=item,
        area=SavedOpportunity.Area.GRANT,
        title="Amazon Agentic AI Research Award",
        deadline_date="2025-01-01",
        snapshot={"amount": "Upper: $70,000 USD"},
    )

    assert prune_expired(today=TODAY) == 1

    saved.refresh_from_db()
    assert saved.content_id is None  # SET_NULL, not deleted
    assert saved.title == "Amazon Agentic AI Research Award"
    assert saved.snapshot["amount"] == "Upper: $70,000 USD"


@pytest.mark.django_db
def test_upsert_without_embedder_stores_items_unvectored():
    summary = upsert_pivot_items(
        [build_pivot_item("grants", _grant(), today=TODAY)],
        embed=True,
        embedder=lambda texts: None,  # embeddings extra unavailable
    )
    assert summary.created == 1
    assert summary.embedded == 0
    assert ContentItem.objects.get(external_id="g1").embedding is None
