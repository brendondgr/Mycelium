"""Tests for :mod:`apps.scraper.collect.ingest`.

Fixtures are built through :func:`~apps.scraper.collect.mapping.map_grant` /
``map_conference`` over minimal :class:`Opportunity` / :class:`ConferenceInstance`
dataclass literals, the same convention :mod:`test_collect_mapping` uses, so these
tests exercise the real Phase 3 -> Phase 4 seam rather than a hand-shaped stand-in
dict that could silently drift from what the mapper actually produces.

Every test needs Postgres (``ContentItem.metadata`` round-trips through a real
JSONField and the module reads ``django.utils.timezone``), so all of them carry
``pytest.mark.django_db``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User

from apps.content.models import ContentItem, SavedOpportunity
from apps.scraper.collect.conferences.record import ConferenceInstance, Deadline
from apps.scraper.collect.grants.record import Opportunity
from apps.scraper.collect.ingest import (
    IngestSummary,
    embed_pending,
    ingest_collected,
    prune_expired,
    upsert_items,
)
from apps.scraper.collect.mapping import map_conference, map_grant

TODAY = date(2026, 8, 16)
NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)
TODAY_ISO = "2026-08-16"


def _fake_embedder(texts):
    # Deterministic, dependency-free stand-in for fastembed -- same idiom the
    # Pivot ingest test suite uses.
    return [[float(len(t)), 1.0, 2.0] for t in texts]


def _grant_item(sid="g1", *, source="nsf", close_date="2026-11-12", **over):
    kwargs = dict(
        source=source,
        source_record_id=sid,
        title="Test Research Award",
        funder="Test Funder",
        description="A grant funding foundational research on distributed systems.",
        close_date=close_date,
        currency="USD",
    )
    kwargs.update(over)
    return map_grant(Opportunity(**kwargs), today=TODAY)


def _conference_item(
    sid="c1", *, source="ccf_deadlines", instant="2026-11-01T00:00:00Z"
):
    deadlines = (
        [Deadline(kind="submission", raw=instant, instant=instant, source=source)]
        if instant
        else []
    )
    instance = ConferenceInstance(
        source=source,
        source_record_id=sid,
        series_key=f"conf/{sid}",
        title="Test Systems Conference",
        acronym="TSC",
        year_label="2026",
        deadlines=deadlines,
    )
    return map_conference(instance, series=None, now=NOW)


def _dateless_conference(sid="journal", *, source="openreview"):
    """A conference row with no deadline and no event date — the 156-row case.

    ``prune_expired``'s original rule can never reach one of these: an empty
    ``prune_after`` cannot be proven past. Mostly journal listings the
    OpenReview adapter emits alongside real calls for papers.
    """
    return _conference_item(sid, source=source, instant="")


# --------------------------------------------------------------------------- #
# Upsert basics
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_upsert_creates_grant_and_conference():
    summary = upsert_items(
        [_grant_item(), _conference_item()], today=TODAY_ISO
    )
    assert summary.seen == 2
    assert summary.created == 2
    assert summary.updated == 0
    assert summary.by_type == {"grant": 1, "conference": 1}

    grant = ContentItem.objects.get(source="grants:nsf", external_id="src:nsf:g1")
    assert grant.type == ContentItem.Type.GRANT
    assert grant.metadata["first_seen"]

    conf = ContentItem.objects.get(source="conf:ccf_deadlines")
    assert conf.type == ContentItem.Type.CONFERENCE
    assert conf.metadata["first_seen"]


@pytest.mark.django_db
def test_upsert_tolerates_none_items_as_skipped():
    """``map_grant`` returns ``None`` for a filtered ``overlay`` record; a
    caller chaining mapper output straight into ``upsert_items`` should never
    have to filter that out itself."""
    overlay = map_grant(
        Opportunity(
            source="nih_guide",
            source_record_id="ov1",
            record_kind="overlay",
            title="Policy notice",
        ),
        today=TODAY,
    )
    assert overlay is None

    summary = upsert_items([overlay, _grant_item()], today=TODAY_ISO)
    assert summary.skipped == 1
    assert summary.created == 1
    assert summary.seen == 1  # the None never counts as "seen"


# --------------------------------------------------------------------------- #
# first_seen immutability + idempotent re-ingest
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_first_seen_survives_a_reingest_with_a_changed_field():
    upsert_items([_grant_item(title="Original Title")], today=TODAY_ISO)
    first = ContentItem.objects.get(external_id="src:nsf:g1").metadata["first_seen"]

    summary = upsert_items(
        [_grant_item(title="Revised Title")], today=TODAY_ISO
    )
    again = ContentItem.objects.get(external_id="src:nsf:g1")

    assert summary.updated == 1
    assert again.metadata["first_seen"] == first  # never reset
    assert again.metadata["title"] == "Revised Title"  # other fields do update
    assert ContentItem.objects.filter(external_id="src:nsf:g1").count() == 1


@pytest.mark.django_db
def test_reingest_with_only_source_url_changed_still_counts_as_updated():
    """``source_url`` is mapper-derived from the record too, and can move on
    its own with every *metadata* field staying identical (a funder
    re-platforming its site, for instance). The "did anything change" check
    must catch that, or a moved URL silently never gets persisted."""
    upsert_items([_grant_item()], today=TODAY_ISO)
    original = ContentItem.objects.get(external_id="src:nsf:g1")
    assert original.source_url == ""

    moved = _grant_item(source_url="https://new.nsf.gov/opportunity/g1")
    summary = upsert_items([moved], today=TODAY_ISO)

    assert summary.updated == 1
    again = ContentItem.objects.get(external_id="src:nsf:g1")
    assert again.source_url == "https://new.nsf.gov/opportunity/g1"


@pytest.mark.django_db
def test_reingest_of_unchanged_input_reports_zero_created_updated_embedded():
    """The headline guarantee (plan Phase 4): re-running ingest over input
    that has not changed at all must be a true no-op, not just "no duplicate
    rows". ``metadata["search_text"]`` is set by hand here to stand in for
    what Phase 8 extraction would already have written by the time
    ``embed_pending`` ever runs for real -- this module's own upsert never
    sets that key itself (see the module docstring)."""
    item = _grant_item()
    item["metadata"]["search_text"] = "test research award distributed systems"

    first = ingest_collected([item], embedder=_fake_embedder, today=TODAY_ISO)
    assert first.created == 1
    assert first.updated == 0
    assert first.embedded == 1

    second = ingest_collected([item], embedder=_fake_embedder, today=TODAY_ISO)
    assert second.created == 0
    assert second.updated == 0
    assert second.embedded == 0
    assert isinstance(second, IngestSummary)


@pytest.mark.django_db
def test_derived_extraction_and_embedding_keys_survive_a_content_change():
    """A re-scrape that changes a genuinely mapped field (forcing ``updated``
    to increment) must not silently discard Phase 8's verified extraction or
    this module's own recorded embedding state -- those keys never appear in
    a freshly mapped item at all, so a wholesale metadata replacement would
    erase them on every single re-scrape of a record extraction has already
    settled."""
    upsert_items([_grant_item(title="Original Title")], today=TODAY_ISO)
    obj = ContentItem.objects.get(external_id="src:nsf:g1")
    obj.metadata = {
        **obj.metadata,
        "search_text": "verified extracted summary",
        "search_text_source": "extracted",
        "search_text_hash": "abc123",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "extraction_status": "ok",
        "ai_summary": "A verified summary nobody should lose.",
    }
    obj.save(update_fields=["metadata"])

    summary = upsert_items([_grant_item(title="Revised Title")], today=TODAY_ISO)
    assert summary.updated == 1

    again = ContentItem.objects.get(external_id="src:nsf:g1")
    assert again.metadata["title"] == "Revised Title"
    assert again.metadata["search_text"] == "verified extracted summary"
    assert again.metadata["search_text_source"] == "extracted"
    assert again.metadata["extraction_status"] == "ok"
    assert again.metadata["ai_summary"] == "A verified summary nobody should lose."


@pytest.mark.django_db
def test_summary_counts_refused_records_among_those_touched():
    upsert_items([_grant_item(title="Original")], today=TODAY_ISO)
    obj = ContentItem.objects.get(external_id="src:nsf:g1")
    obj.metadata = {**obj.metadata, "extraction_status": "refused"}
    obj.save(update_fields=["metadata"])

    summary = upsert_items([_grant_item(title="Revised")], today=TODAY_ISO)
    assert summary.refused == 1


# --------------------------------------------------------------------------- #
# Prune
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_source_id_is_pruned_when_expired():
    """The bug the plan names: Pivot's ``prune_expired`` filtered on a
    hard-coded ``OPPORTUNITY_SOURCES`` allow-list of exactly two source ids,
    so a record from any *other* source -- every ``grants:<adapter>`` /
    ``conf:<adapter>`` row this migration introduces -- was silently
    invisible to expiry. This module's ``prune_expired`` filters on
    ``type__in`` instead, so a brand-new source id is pruned correctly with
    no allow-list to have forgotten to update."""
    upsert_items(
        [
            _grant_item("expired", source="nsf", close_date="2025-01-01"),
            _conference_item("still_open", source="openreview"),
        ],
        today=TODAY_ISO,
    )
    assert ContentItem.objects.filter(source="grants:nsf").exists()

    removed = prune_expired(today=TODAY_ISO)
    assert removed == 1
    assert not ContentItem.objects.filter(external_id="src:nsf:expired").exists()
    assert ContentItem.objects.filter(source="conf:openreview").exists()


@pytest.mark.django_db
def test_prune_after_empty_is_never_pruned():
    """A rolling grant (no ``close_date`` at all) maps to ``prune_after ==
    ""`` -- an unknown/absent expiry can never be proven past, so it must
    survive every prune regardless of how far "today" is pushed forward."""
    upsert_items([_grant_item("rolling", close_date=None)], today=TODAY_ISO)
    item = ContentItem.objects.get(external_id="src:nsf:rolling")
    assert item.metadata["prune_after"] == ""

    removed = prune_expired(today="2099-01-01")
    assert removed == 0
    assert ContentItem.objects.filter(external_id="src:nsf:rolling").exists()


@pytest.mark.django_db
def test_a_dateless_conference_is_pruned_once_the_source_stops_listing_it():
    """The gap the old rule could never close.

    A conference with no deadline and no event date carries ``prune_after ==
    ""``, so the past-date sweep can never touch it — 156 of 912 live
    conferences on 2026-08-17, shown to readers forever. It is now deleted, but
    only on the evidence that the collector has stopped seeing it: ``last_seen``
    older than ``OPPORTUNITY_STALE_DAYS``.
    """
    upsert_items([_dateless_conference()], today=TODAY_ISO)
    item = ContentItem.objects.get(source="conf:openreview")
    assert item.metadata["prune_after"] == ""

    # Seen today: the source still lists it, so it survives.
    assert prune_expired(today=TODAY_ISO) == 0
    assert ContentItem.objects.filter(id=item.id).exists()

    # Unseen for longer than the window: gone.
    assert prune_expired(today="2027-01-01") == 1
    assert not ContentItem.objects.filter(id=item.id).exists()


@pytest.mark.django_db
def test_a_dateless_grant_is_never_stale_however_long_it_sits():
    """A rolling grant means the opposite of a dateless conference.

    ``mapping._grant_deadlines`` writes ``prune_after == ""`` to say "no round
    at all, never expires". The staleness rule must not read that as death, or
    every continuously-open funding call disappears two months after ingest.
    """
    upsert_items([_grant_item("rolling", close_date=None)], today=TODAY_ISO)

    assert prune_expired(today="2099-01-01") == 0
    assert ContentItem.objects.filter(external_id="src:nsf:rolling").exists()


@pytest.mark.django_db
def test_stale_only_skips_the_ordinary_expiry_sweep():
    """``--stale-only`` is the one-off purge, not a second full prune."""
    upsert_items(
        [
            _grant_item("expired", close_date="2025-01-01"),
            _dateless_conference(),
        ],
        today=TODAY_ISO,
    )

    removed = prune_expired(today="2027-01-01", stale_only=True)
    assert removed == 1
    assert not ContentItem.objects.filter(source="conf:openreview").exists()
    # The past-dated grant is untouched: this sweep was not asked about it.
    assert ContentItem.objects.filter(external_id="src:nsf:expired").exists()


@pytest.mark.django_db
def test_dry_run_reports_without_deleting():
    upsert_items([_grant_item("expired", close_date="2025-01-01")], today=TODAY_ISO)

    assert prune_expired(today=TODAY_ISO, dry_run=True) == 1
    assert ContentItem.objects.filter(external_id="src:nsf:expired").exists()


@pytest.mark.django_db
def test_prune_after_compares_zero_padded():
    """A record due in October (month "10") must not be judged expired
    relative to an August "today" (month "08"). Under a naive, non-zero-padded
    lexicographic compare a leading "1" sorts *before* a leading "8"
    character-by-character, which would misread October as earlier than
    August; zero-padding both sides (which ``map_grant`` always emits via
    ``date.isoformat()``) is what keeps the plain string compare correct."""
    upsert_items(
        [
            _grant_item("due_october", close_date="2026-10-01"),
            _grant_item("due_august", source="sam_gov", close_date="2026-08-05"),
        ],
        today=TODAY_ISO,
    )

    removed = prune_expired(today=TODAY_ISO)  # today = 2026-08-16
    assert removed == 1
    assert ContentItem.objects.filter(external_id="src:nsf:due_october").exists()
    assert not ContentItem.objects.filter(
        source="grants:sam_gov", external_id="src:sam_gov:due_august"
    ).exists()


@pytest.mark.django_db
def test_prune_preserves_saved_deadline_via_set_null():
    user = User.objects.create_user(username="researcher", password="pw")
    upsert_items(
        [_grant_item("expiring", close_date="2025-01-01")], today=TODAY_ISO
    )
    item = ContentItem.objects.get(external_id="src:nsf:expiring")
    saved = SavedOpportunity.objects.create(
        user=user,
        content=item,
        area=SavedOpportunity.Area.GRANT,
        title="Test Research Award",
        deadline_date="2025-01-01",
        snapshot={"funder": "Test Funder"},
    )

    assert prune_expired(today=TODAY_ISO) == 1

    saved.refresh_from_db()
    assert saved.content_id is None  # SET_NULL, not deleted
    assert saved.snapshot["funder"] == "Test Funder"


# --------------------------------------------------------------------------- #
# Embed
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_embed_pending_skips_items_with_no_search_text():
    """A record ``upsert_items`` has written but Phase 8 extraction has not
    yet reached carries no ``search_text`` at all -- ``embed_pending`` must
    leave it alone rather than embedding raw collector text (plan D9)."""
    upsert_items([_grant_item()], today=TODAY_ISO)

    embedded = embed_pending(embedder=_fake_embedder)
    assert embedded == 0
    assert ContentItem.objects.get(external_id="src:nsf:g1").embedding is None


@pytest.mark.django_db
def test_embed_pending_reembeds_only_when_search_text_hash_changes():
    upsert_items([_grant_item()], today=TODAY_ISO)
    obj = ContentItem.objects.get(external_id="src:nsf:g1")
    obj.metadata = {**obj.metadata, "search_text": "first extracted summary"}
    obj.save(update_fields=["metadata"])

    first_count = embed_pending(embedder=_fake_embedder)
    assert first_count == 1
    obj.refresh_from_db()
    first_vector = obj.embedding
    assert first_vector is not None
    assert obj.metadata["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert obj.metadata["search_text_hash"]

    # Unchanged search_text: a second sweep must not re-embed.
    second_count = embed_pending(embedder=_fake_embedder)
    assert second_count == 0

    # Changed search_text: the hash no longer matches, so it re-embeds.
    obj.metadata = {**obj.metadata, "search_text": "a materially different summary"}
    obj.save(update_fields=["metadata"])
    third_count = embed_pending(embedder=_fake_embedder)
    assert third_count == 1
    obj.refresh_from_db()
    assert obj.metadata["search_text_hash"]


@pytest.mark.django_db
def test_embed_pending_is_scoped_to_collector_sources():
    """A ``pivot``-sourced grant carrying its own ``search_text`` must never
    be touched by this module's embed sweep -- Pivot's own ingest already
    owns embedding for that row, and this function's scope is exactly the
    ``grants:``/``conf:`` prefixes the collector mapper writes."""
    pivot_item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id="p1",
        metadata={"search_text": "a pivot-sourced grant"},
    )
    upsert_items([_grant_item()], today=TODAY_ISO)
    collector_obj = ContentItem.objects.get(external_id="src:nsf:g1")
    collector_obj.metadata = {**collector_obj.metadata, "search_text": "collector text"}
    collector_obj.save(update_fields=["metadata"])

    embedded = embed_pending(embedder=_fake_embedder)
    assert embedded == 1

    pivot_item.refresh_from_db()
    assert pivot_item.embedding is None


@pytest.mark.django_db
def test_embed_pending_without_embedder_leaves_items_unvectored():
    upsert_items([_grant_item()], today=TODAY_ISO)
    obj = ContentItem.objects.get(external_id="src:nsf:g1")
    obj.metadata = {**obj.metadata, "search_text": "some extracted text"}
    obj.save(update_fields=["metadata"])

    embedded = embed_pending(embedder=lambda texts: None)  # extra unavailable
    assert embedded == 0
    assert ContentItem.objects.get(external_id="src:nsf:g1").embedding is None


# --------------------------------------------------------------------------- #
# ingest_collected orchestration
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_ingest_collected_chains_upsert_embed_prune():
    live = _grant_item("live", close_date="2026-12-01")
    live["metadata"]["search_text"] = "a live grant, still open"
    expired = _grant_item("expired", source="sam_gov", close_date="2025-01-01")
    expired["metadata"]["search_text"] = "an expired grant"

    summary = ingest_collected(
        [live, expired], embedder=_fake_embedder, today=TODAY_ISO
    )

    assert summary.created == 2
    assert summary.embedded == 2
    assert summary.pruned == 1
    assert ContentItem.objects.filter(external_id="src:nsf:live").exists()
    assert not ContentItem.objects.filter(
        source="grants:sam_gov", external_id="src:sam_gov:expired"
    ).exists()
