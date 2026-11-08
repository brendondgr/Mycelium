"""The smoke checklist (``tools.retrieval.collect.conferences.smoke``).

The point of these tests is that the checklist can actually *fail*. A checklist
that always passes verifies nothing, so several of these deliberately feed it a
broken corpus and assert it says so.

The standalone project's CLI section of this file (the old
``tools.retrieval.collect.conferences.cli``'s ``list-sources`` / ``status`` /
``spot-check`` / ``resolve`` / ``smoke`` / ``delta`` subcommands, all driven
through ``main(...)``) was dropped along with the CLI itself — Mycelium drives
this collector from a management command instead (see the module the tests
still cover: ``smoke.run_checklist`` and ``smoke.format_report``, which the
dropped CLI called but did not implement).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tools.retrieval.collect.conferences.record import Deadline
from tools.retrieval.collect.conferences.smoke import (
    FAIL,
    PASS,
    SKIP,
    format_report,
    run_checklist,
)
from tools.retrieval.collect.conferences.store import ConferenceStore

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def checks_by_prefix(checks, prefix: str):
    return next(c for c in checks if c.name.startswith(prefix))


@pytest.fixture
def populated(seeded_pipeline):
    seeded_pipeline.run(skip_fetch=True, now=NOW)
    return seeded_pipeline


# --- the headline checks -------------------------------------------------


def test_the_aoe_check_is_real_arithmetic_not_a_constant(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    aoe = checks_by_prefix(checks, "An AoE deadline")
    assert aoe.status == PASS
    assert "2026-01-16T11:59:59Z" in aoe.detail


def test_idempotency_passes_on_a_second_identical_run(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=True)
    assert checks_by_prefix(checks, "Idempotency").status == PASS


def test_offline_rerun_exercises_parse_and_resolve_with_no_network(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    offline = checks_by_prefix(checks, "Parse and resolve re-runnable")
    assert offline.status == PASS
    assert "offline" in offline.detail


def test_every_deadline_basis_check_passes_on_a_good_corpus(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    assert checks_by_prefix(checks, "Every deadline carries").status == PASS


def test_the_basis_check_fails_when_a_basis_is_missing(populated):
    """Prove the check can fail. A basis-less deadline is a silent day-shift."""
    with ConferenceStore(populated.config.db_path) as store:
        record = store.all_instances()[0]
        record.deadlines = [Deadline(kind="submission", instant="2027-01-01T00:00:00Z", basis="")]
        store.upsert_instances([record])

    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    assert checks_by_prefix(checks, "Every deadline carries").status == FAIL


def test_multi_round_ordering_is_verified_against_the_real_corpus(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    multi = checks_by_prefix(checks, "A multi-round venue")
    assert multi.status == PASS
    assert "VLDB" in multi.detail


def test_past_instances_are_retained_and_the_check_says_so(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    retained = checks_by_prefix(checks, "A past instance")
    assert retained.status == PASS
    assert "retained" in retained.detail


# --- skip is not pass ----------------------------------------------------


def test_a_property_the_corpus_cannot_exercise_is_skipped_not_passed(populated):
    """Reporting PASS for something never tested would claim a verification that
    did not happen."""
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    # This fixture has one source, so there is nothing to cross-source merge.
    assert checks_by_prefix(checks, "A venue in two sources").status == SKIP


def test_an_empty_store_skips_rather_than_passing(config):
    checks = run_checklist(config, now=NOW, check_idempotency=False)
    assert checks_by_prefix(checks, "Every deadline carries").status == SKIP


def test_the_report_counts_skips_separately(populated):
    checks = run_checklist(populated.config, now=NOW, check_idempotency=False)
    report = format_report(checks)
    assert "passed" in report and "failed" in report and "skipped" in report
    assert report.count("[-]") == sum(1 for c in checks if c.status == SKIP)


# --- what the dropped CLI's non-CLI-specific subcommands wrapped ---------


def test_phase_selects_adapters_up_to_that_phase():
    from tools.retrieval.collect.conferences.adapters import adapters_for_phase

    assert "ccf_deadlines" in adapters_for_phase(0)


def test_an_unknown_source_is_rejected_rather_than_silently_collecting_nothing(tmp_path):
    from tools.retrieval.collect.conferences.pipeline import (
        ConferenceConfig,
        ConferencePipeline,
    )

    pipeline = ConferencePipeline(
        ConferenceConfig(root=tmp_path, sources=["not_a_real_source"])
    )
    with pytest.raises(ValueError, match="unknown source"):
        pipeline.selected_sources()
