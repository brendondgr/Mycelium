"""The five-stage seam, end to end, with the network forbidden.

Everything below runs from raw payloads written straight to disk, which is the
same path a re-parse takes in production. If any of these tests could only pass
with network access, the fetch/parse split would be a lie.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.scraper.collect.core.http import FetchError, PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, RawStore
from apps.scraper.collect.grants.pipeline import CollectConfig, Pipeline
from apps.scraper.collect.grants.smoke import FAIL, PASS, run_checklist
from apps.scraper.collect.grants.store import Store
from apps.scraper.tests.collect.grants.conftest import (
    GRANTS_GOV_DETAIL,
    GRANTS_GOV_SUMMARY,
    NIH_ANNOUNCEMENT,
    NIH_OVERLAY_NOTICE,
    SBIR_SOLICITATION,
    opportunity,
)

TODAY = date(2026, 8, 15)
RUN_ID = "20260815T000000Z"


def seed(config: CollectConfig) -> None:
    """Write raw payloads for three sources, as stage 1 would have."""
    raw_store = RawStore(config.raw_root)
    raw_store.write(
        RawBundle(
            source="grants_gov",
            run_id=RUN_ID,
            fetched_at="2026-08-15T00:00:00Z",
            records=[GRANTS_GOV_SUMMARY],
            meta={"details": {"357305": GRANTS_GOV_DETAIL}, "hit_count": 1},
        )
    )
    raw_store.write(
        RawBundle(
            source="sbir",
            run_id=RUN_ID,
            fetched_at="2026-08-15T00:00:00Z",
            records=[SBIR_SOLICITATION],
            meta={},
        )
    )
    raw_store.write(
        RawBundle(
            source="nih_guide",
            run_id=RUN_ID,
            fetched_at="2026-08-15T00:00:00Z",
            records=[NIH_ANNOUNCEMENT],
            meta={"notices": [NIH_OVERLAY_NOTICE]},
        )
    )


@pytest.fixture
def seeded(tmp_path) -> CollectConfig:
    config = CollectConfig(
        root=tmp_path / "collect", sources=["grants_gov", "sbir", "nih_guide"]
    )
    seed(config)
    return config


# --- stage independence --------------------------------------------------


def test_parse_runs_with_no_network_at_all(seeded):
    offline = Pipeline(CollectConfig(root=seeded.root, sources=seeded.sources, offline=True))
    records, counts, errors = offline.parse(RUN_ID)

    assert not errors
    assert counts["grants_gov"] == 1
    assert counts["sbir"] == 4  # 1 solicitation + 2 topics + 1 subtopic
    assert counts["nih_guide"] == 2  # 1 announcement + 1 overlay
    assert len(records) == 7


def test_offline_client_refuses_to_reach_the_network(tmp_path):
    client = PoliteClient(cache_dir=tmp_path / "cache", offline=True)
    with pytest.raises(FetchError, match="offline"):
        client.get("https://example.invalid/nothing")


def test_a_parse_bug_in_one_adapter_does_not_sink_the_others(seeded, monkeypatch):
    pipeline = Pipeline(seeded)

    def explode(_bundle):
        raise ValueError("bad field")

    monkeypatch.setattr(pipeline.registry["sbir"], "parse", explode)
    records, counts, errors = pipeline.parse(RUN_ID)

    assert ("sbir", "parse", "ValueError: bad field") in errors
    assert "grants_gov" in counts
    assert records


# --- stage 3 -------------------------------------------------------------


def test_normalize_drops_records_whose_every_deadline_has_passed(seeded):
    records = [
        opportunity(source_record_id="1", close_date="2025-01-01"),
        opportunity(source_record_id="2", opportunity_number="PA-25-002", close_date="2027-01-01"),
    ]
    kept = Pipeline(seeded).normalize(records, TODAY)
    assert [r.source_record_id for r in kept] == ["2"]


def test_normalize_keeps_rolling_and_recurring_records(seeded):
    rolling = opportunity(source_record_id="1", close_date=None)
    recurring = opportunity(
        source_record_id="2",
        opportunity_number="PA-25-002",
        close_date="2025-01-01",
        additional_due_dates=["2027-01-01"],
    )
    kept = Pipeline(seeded).normalize([rolling, recurring], TODAY)
    assert len(kept) == 2


def test_normalize_makes_close_date_the_final_round(seeded):
    """Adapters disagreed about which end of a deadline list meant what.

    Normalizing centrally is what stops the next adapter reinventing the bug, so
    the rule is asserted against an adapter that hands over its rounds in the
    worst possible order.
    """
    backwards = opportunity(close_date="2021-09-21", additional_due_dates=["2026-09-21", "2025-09-22"])
    (kept,) = Pipeline(seeded).normalize([backwards], TODAY)
    assert kept.close_date == "2026-09-21"
    assert kept.additional_due_dates == ["2021-09-21", "2025-09-22"]


def test_normalize_leaves_a_recurring_record_showing_its_next_round(seeded):
    backwards = opportunity(close_date="2021-09-21", additional_due_dates=["2026-09-21", "2025-09-22"])
    (kept,) = Pipeline(seeded).normalize([backwards], TODAY)
    # Pruning keys on the last round; a reader is shown the next one.
    assert kept.due_on(TODAY) == "2026-09-21"


def test_normalize_shows_the_nearest_round_of_a_long_cycle(seeded):
    """The NIH shape: last receipt date years out, next cycle weeks away."""
    cycle = opportunity(close_date="2028-01-07", additional_due_dates=["2026-10-05", "2027-02-05"])
    (kept,) = Pipeline(seeded).normalize([cycle], TODAY)
    assert kept.close_date == "2028-01-07"
    assert kept.due_on(TODAY) == "2026-10-05"


def test_normalize_swaps_an_inverted_award_range(seeded):
    record = opportunity(award_floor=500_000.0, award_ceiling=50_000.0)
    (kept,) = Pipeline(seeded).normalize([record], TODAY)
    assert (kept.award_floor, kept.award_ceiling) == (50_000.0, 500_000.0)


def test_normalize_discards_an_empty_husk(seeded):
    husk = opportunity(title="", description="")
    assert Pipeline(seeded).normalize([husk], TODAY) == []


# --- full run ------------------------------------------------------------


def test_full_run_from_stored_payloads_persists_every_kind(seeded):
    pipeline = Pipeline(seeded)
    report = pipeline.run(skip_fetch=True, run_id=RUN_ID, today=TODAY)

    assert report.stats.inserted > 0
    with Store(seeded.db_path) as store:
        kinds = {record.record_kind for record in store.all_records()}
    assert kinds == {"standalone", "topic", "overlay"}


def test_running_twice_changes_nothing(seeded):
    pipeline = Pipeline(seeded)
    pipeline.run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    second = pipeline.run(skip_fetch=True, run_id=RUN_ID, today=TODAY)

    assert second.stats.inserted == 0
    assert second.stats.updated == 0
    assert second.stats.unchanged > 0


def test_the_overlay_resolves_against_the_announcement_in_the_same_run(seeded):
    # The NIH fixture's overlay points at PA-25-172, which the XML fixture
    # supplies — so the parent reference must come out resolved, not flagged.
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    with Store(seeded.db_path) as store:
        overlay = next(r for r in store.all_records() if r.record_kind == "overlay")
    assert overlay.parent_opportunity_number == "PA-25-172"
    assert overlay.unresolved_parent is False


def test_topics_outnumber_their_parent_solicitation(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    with Store(seeded.db_path) as store:
        topics = [r for r in store.all_records() if r.record_kind == "topic"]
    assert len(topics) == 3


def test_raw_payloads_stay_on_disk_after_the_run(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    assert (seeded.raw_root / RUN_ID / "grants_gov.json").exists()


def test_raw_run_pruning_keeps_only_the_most_recent(tmp_path):
    raw_store = RawStore(tmp_path / "raw")
    for index in range(5):
        raw_store.write(
            RawBundle(f"s{index}", f"2026010{index}T000000Z", "t", [{"a": index}], {})
        )
    removed = raw_store.prune_runs(keep=2)
    assert len(removed) == 3
    assert raw_store.latest_run_id() == "20260104T000000Z"


# --- smoke checklist -----------------------------------------------------


def test_smoke_checklist_passes_on_a_healthy_corpus(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    checks = run_checklist(seeded, today=TODAY)

    failures = [check for check in checks if check.status == FAIL]
    assert not failures, [check.line() for check in failures]
    assert len(checks) == 10


def test_smoke_checklist_reports_the_idempotency_check_as_passing(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    checks = run_checklist(seeded, today=TODAY)
    idempotency = next(c for c in checks if c.name.startswith("Idempotency"))
    assert idempotency.status == PASS


def test_smoke_checklist_catches_a_stale_record(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    with Store(seeded.db_path) as store:
        store.upsert_all([opportunity(source_record_id="stale", opportunity_number="PA-20-001", close_date="2020-01-01")])

    checks = run_checklist(seeded, today=TODAY, check_idempotency=False)
    stale_check = next(c for c in checks if "past close date" in c.name)
    assert stale_check.status == FAIL


def test_smoke_count_margin_check_fails_when_far_off(seeded):
    Pipeline(seeded).run(skip_fetch=True, run_id=RUN_ID, today=TODAY)
    checks = run_checklist(
        seeded, today=TODAY, expected_counts={"grants_gov": 1000}, check_idempotency=False
    )
    margin = next(c for c in checks if "within margin" in c.name)
    assert margin.status == FAIL


# --- errors --------------------------------------------------------------


def test_a_dead_source_is_recorded_and_the_run_continues(seeded, monkeypatch):
    pipeline = Pipeline(seeded)

    def blocked(_client, *, limit=None):
        raise FetchError("https://api.www.sbir.gov/public/api/solicitations", "HTTP 403", 403)

    monkeypatch.setattr(pipeline.registry["sbir"], "fetch", blocked)
    monkeypatch.setattr(
        pipeline.registry["grants_gov"],
        "fetch",
        lambda _client, limit=None: RawBundle(
            "grants_gov",
            RUN_ID,
            "t",
            [GRANTS_GOV_SUMMARY],
            {"details": {"357305": GRANTS_GOV_DETAIL}},
        ),
    )
    monkeypatch.setattr(
        pipeline.registry["nih_guide"],
        "fetch",
        lambda _client, limit=None: RawBundle("nih_guide", RUN_ID, "t", [NIH_ANNOUNCEMENT], {}),
    )

    report = pipeline.run(today=TODAY)

    assert any(source == "sbir" and "403" in message for source, _, message in report.errors)
    assert report.parsed["grants_gov"] == 1
    with Store(seeded.db_path) as store:
        assert any(row["source"] == "sbir" for row in store.errors_for(report.run_id))


def test_unknown_source_is_rejected_up_front(tmp_path):
    pipeline = Pipeline(CollectConfig(root=tmp_path, sources=["nope"]))
    with pytest.raises(ValueError, match="nope"):
        pipeline.selected_sources()
