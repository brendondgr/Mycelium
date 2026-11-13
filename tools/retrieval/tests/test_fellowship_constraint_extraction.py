"""Regression tests for ``extract_fellowship_constraints``
(tools.retrieval.fellowships.ingest).

This is the ingest-level *selection* pass: which stored fellowships get sent to
the model for eligibility-prose extraction, and how many. The pure pattern/model
logic those records feed into is covered separately in
``test_fellowship_constraints.py``.

Phase 2 of ``docs/plans/open-opportunity-collector.md`` fixed a real bug here: the
function used to filter on another source's id, but fellowships are ingested
under ``FELLOWSHIP_SOURCE`` ("illinois-fellowship-finder"). The queryset was
therefore always empty and this extraction pass had never actually run on a
single real fellowship, silently: it just returned 0 and the ingest moved on.
No test anywhere exercised the function
(``grep -rn extract_fellowship_constraints`` matched none), which is exactly why
the bug survived a full test suite. These tests exercise the selection logic
directly against the ORM so a source-filter regression like this one fails loudly
instead of quietly doing nothing.

Phase 6 moved ``extract_fellowship_constraints`` into
``tools.retrieval.fellowships.ingest``; the function was already fellowship-only.

All model calls are stubbed — ``extract_fellowship_constraints`` takes ``complete``
for injection precisely so tests never need the network or a model server, and
none of these do.
"""

import json

import pytest
from django.test import override_settings

from tools.retrieval.eligibility.constraints import empty_constraints
from tools.retrieval.fellowships.ingest import (
    CONSTRAINT_EXTRACTION_BATCH,
    FELLOWSHIP_SOURCE,
    extract_fellowship_constraints,
)
from tools.retrieval.models import ContentItem

# Prose the pattern layer alone cannot gate on (the NSF-style "within two years"
# window from test_fellowship_constraints.py) — plausible eligibility text so a
# resolved model reply isn't obviously fabricated.
_ELIGIBILITY = ["Applicants must have received the PhD within the previous two years."]


def _fellowship(
    external_id: str,
    *,
    source: str = FELLOWSHIP_SOURCE,
    eligibility=None,
    constraints=None,
) -> ContentItem:
    """A stored fellowship ``ContentItem``, built directly (not via ``ingest_pivot``)
    so these tests isolate the selection pass from the rest of the ingest pipeline.
    """
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source=source,
        external_id=external_id,
        source_url=f"https://fellowship-finder.grad.illinois.edu/x/{external_id}",
        metadata={
            "title": f"Fellowship {external_id}",
            "eligibility": _ELIGIBILITY if eligibility is None else eligibility,
            "constraints": empty_constraints() if constraints is None else constraints,
        },
    )


def _resolving_complete(calls: list[str]):
    """A stub ``complete`` that resolves every item it is asked about and records
    every prompt it was called with, so a test can assert on both the outcome
    (what got written back) and the input (how many/which records were sent).
    """

    def _complete(prompt: str) -> str:
        calls.append(prompt)
        n = prompt.count("ITEM ")
        items = [
            {
                "item": i,
                "min_stage": "postdoc",
                "max_years_post_phd": 2,
                "degree_required": "phd",
                "evidence": "received the PhD within the previous two years",
            }
            for i in range(1, n + 1)
        ]
        return json.dumps({"items": items})

    return _complete


# ---------------------------------------------------------------------------
# The regression: only FELLOWSHIP_SOURCE rows are ever selected
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_illinois_source_with_unresolved_constraints_is_selected():
    """The exact case that was broken: a real fellowship, unresolved constraints,
    stored under the real source id — must be sent to the model.
    """
    _fellowship("f1")
    calls: list[str] = []

    changed = extract_fellowship_constraints(complete=_resolving_complete(calls))

    assert changed == 1
    assert len(calls) == 1
    obj = ContentItem.objects.get(external_id="f1")
    assert obj.metadata["constraints"]["source"] == "llm"
    assert obj.metadata["constraints"]["min_stage"] == "postdoc"


@pytest.mark.django_db
def test_wrong_source_is_never_selected():
    """Pins the bug directly: a FELLOWSHIP-typed row stored under any source
    other than ``FELLOWSHIP_SOURCE`` (e.g. the old, wrong filter's
    ``PIVOT_SOURCE``) must never be sent to the model — no fellowship is ever
    ingested under any source but the Illinois Fellowship Finder's own id.
    """
    _fellowship("wrong", source="grants:nsf")
    calls: list[str] = []

    changed = extract_fellowship_constraints(complete=_resolving_complete(calls))

    assert changed == 0
    assert calls == []  # zero LLM calls
    obj = ContentItem.objects.get(external_id="wrong")
    assert obj.metadata["constraints"]["source"] == "none"  # left untouched


# ---------------------------------------------------------------------------
# Already-resolved records are never re-sent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_already_llm_resolved_record_is_not_resent():
    resolved = {
        "min_stage": "postdoc",
        "max_years_post_phd": 3,
        "degree_required": "phd",
        "source": "llm",
        "evidence": "already answered",
    }
    _fellowship("settled", constraints=resolved)
    _fellowship("pending")
    calls: list[str] = []

    changed = extract_fellowship_constraints(complete=_resolving_complete(calls))

    assert changed == 1  # only "pending"
    assert len(calls) == 1
    assert calls[0].count("ITEM ") == 1  # the settled record never entered the prompt
    settled = ContentItem.objects.get(external_id="settled")
    assert settled.metadata["constraints"] == resolved  # byte-for-byte unchanged


@pytest.mark.django_db
def test_pattern_resolved_record_is_also_not_resent():
    """``is_resolved`` covers the free pattern layer too — a record the patterns
    already gated on at build time must not pay for a model call either.
    """
    pattern_resolved = {
        "min_stage": "postdoc",
        "max_years_post_phd": None,
        "degree_required": "phd",
        "source": "patterns",
        "evidence": "must hold a PhD at the time of award",
    }
    _fellowship("patterned", constraints=pattern_resolved)
    calls: list[str] = []

    changed = extract_fellowship_constraints(complete=_resolving_complete(calls))

    assert changed == 0
    assert calls == []


# ---------------------------------------------------------------------------
# FELLOWSHIP_CONSTRAINT_EXTRACTION=False short-circuits before any call
# ---------------------------------------------------------------------------


@override_settings(FELLOWSHIP_CONSTRAINT_EXTRACTION=False)
@pytest.mark.django_db
def test_disabled_flag_makes_zero_calls():
    _fellowship("f1")

    def _boom(_prompt):
        raise AssertionError("must not be called when the flag is off")

    changed = extract_fellowship_constraints(complete=_boom)

    assert changed == 0
    obj = ContentItem.objects.get(external_id="f1")
    assert obj.metadata["constraints"]["source"] == "none"  # never touched


# ---------------------------------------------------------------------------
# The batch cap is honoured
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_cap_limits_records_sent_per_pass():
    for i in range(CONSTRAINT_EXTRACTION_BATCH + 5):
        _fellowship(f"f{i}")
    calls: list[str] = []

    changed = extract_fellowship_constraints(complete=_resolving_complete(calls))

    assert changed == CONSTRAINT_EXTRACTION_BATCH  # capped, not all N
    assert len(calls) == 1  # one batched call, not one per record
    assert calls[0].count("ITEM ") == CONSTRAINT_EXTRACTION_BATCH


@pytest.mark.django_db
def test_custom_limit_is_honoured():
    for i in range(10):
        _fellowship(f"f{i}")
    calls: list[str] = []

    changed = extract_fellowship_constraints(
        complete=_resolving_complete(calls), limit=3
    )

    assert changed == 3
    assert calls[0].count("ITEM ") == 3
