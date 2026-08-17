"""A collection that sees nothing must fail loudly, not succeed quietly.

This guard exists because of a failure this repository has already had once.
``extract_fellowship_constraints`` filtered on the wrong source string, matched
zero rows on every run, reported success every time, and went unnoticed long
enough to be documented in the repo map as a working feature. The nightly
collection has exactly the same shape available to it: a killed fetch, a renamed
adapter, an unreachable host, or a key that drifts between the collector and the
mapper all end in "0 created, 0 updated" and exit 0.

That matters more than it looks. The nightly does not stop when collection
returns nothing — it goes on to rank, slate and report over whatever corpus
already exists, so a silently dead collector produces a perfectly normal-looking
daily report for as long as it takes someone to notice the listings have stopped
moving.

``seen`` is the right thing to test, not ``created``. A healthy re-run over an
unchanged corpus legitimately creates and updates nothing — that is the
idempotency contract these very tests pin elsewhere — but it can never *see*
nothing.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

COMMAND = "apps.scraper.management.commands.collect_opportunities"


class _Summary:
    """Stands in for the ingest summary the command reports on."""

    def __init__(self, *, seen: int, created: int = 0, updated: int = 0) -> None:
        self.seen = seen
        self.created = created
        self.updated = updated
        self.embedded = 0
        self.pruned = 0
        self.skipped = 0
        self.refused = 0


def _run(summary: _Summary, *, collected: int = 1):
    """Drive the command with collection and extraction stubbed out.

    ``collected`` is how many records the stubbed collector yields —
    the distinction the guard turns on. Zero means the collector came
    back empty; non-zero means it worked and ``summary`` then decides
    whether anything changed.
    """
    # The four collector stages are stubbed so nothing touches the network:
    # this test is about what the command does with an ingest result, not about
    # collection itself.
    from apps.scraper.collect.runner import CONFERENCES, GRANTS

    data = {
        domain: mock.Mock(
            items=[mock.Mock(series_key='conf/x')] * collected,
            series=[],
            new_keys=set(),
            pipeline=mock.Mock(),
        )
        for domain in (GRANTS, CONFERENCES)
    }
    # A mapped record only has to be truthy and carry a key — nothing here
    # exercises the mapper itself, which has its own 636 lines of tests.
    fake_item = {"external_id": "k", "source": "grants:nsf", "metadata": {}}
    with (
        mock.patch(f"{COMMAND}.stage_extract", return_value=data),
        mock.patch(f"{COMMAND}.map_grant", return_value=fake_item),
        mock.patch(f"{COMMAND}.map_conference", return_value=fake_item),
        mock.patch(f"{COMMAND}.stage_deduplicate"),
        mock.patch(f"{COMMAND}.stage_flag_new"),
        mock.patch(f"{COMMAND}.stage_validate"),
        mock.patch(f"{COMMAND}.write_report"),
        mock.patch(f"{COMMAND}.ingest_collected", return_value=summary),
        mock.patch(f"{COMMAND}.embed_pending", return_value=0),
        mock.patch(f"{COMMAND}.prune_expired", return_value=0),
    ):
        # --skip-fetch keeps the raw-payload prune off the path too; this test
        # is about the exit contract, not about disk housekeeping.
        call_command(
            "collect_opportunities", "--no-extract", "--no-prune", "--skip-fetch"
        )


def test_a_run_that_saw_nothing_raises():
    """The headline: zero seen is a failed run, and the message says why."""
    with pytest.raises(CommandError) as excinfo:
        _run(_Summary(seen=0), collected=0)

    message = str(excinfo.value)
    assert "no records were collected at all" in message
    # The operator needs to be told what to check, not merely that it failed.
    assert "reachable" in message


def test_an_idempotent_rerun_is_not_mistaken_for_a_dead_one():
    """Seen but unchanged is the *success* case, and must stay one.

    This is the assertion that stops the guard from being tightened into
    something that breaks the idempotency contract: a second pass over an
    unchanged corpus reports 0 created and 0 updated on purpose.
    """
    _run(_Summary(seen=2_190, created=0, updated=0))  # no exception


def test_a_normal_first_run_succeeds():
    _run(_Summary(seen=2_190, created=2_190))  # no exception
