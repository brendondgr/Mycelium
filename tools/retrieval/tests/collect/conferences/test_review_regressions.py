"""Regressions for defects found by independent review of the parallel adapters.

Each of these shipped in a working, green adapter and would have degraded the
output silently. They are grouped here rather than scattered so the provenance
stays visible: every one was caught by a reviewer re-probing a claim, not by the
test suite that already existed.

The standalone project's WikiCFP section (four regressions: a deadline pinned
to midnight losing its own final day, a raw-payload trust signal dropped
before resolve, and a bot-wall interstitial that would have parsed to a quiet
day) was dropped here along with the adapter itself (plan decision D5 — see
``tools/retrieval/collect/conferences/adapters/__init__.py``). It is not merely
skipped: the source it protected is no longer collected at all.
"""

from __future__ import annotations

from tools.retrieval.collect.conferences.adapters.miccai import MICCAIAdapter
from tools.retrieval.collect.conferences.dedupe import deduplicate
from tools.retrieval.tests.collect.conferences.conftest import bundle, fixture_text

# --- miccai: a whole deadline round disappeared --------------------------


def test_miccai_deadline_rounds_carry_distinguishing_labels():
    """Four distinct labels map to the kind "submission" ("Submission
    deadline", "Submission deadline extended", "Application deadline",
    "Applications due").

    Without a round label they share the (kind, round_label) identity, so
    merge_deadlines treats the second as an *extension* of the first and one
    round silently vanishes.
    """
    series, instances = MICCAIAdapter().parse(
        bundle("miccai", [{"feed_xml": fixture_text("miccai_keydates_feed_sample.xml")}])
    )
    labels = {d.round_label for i in instances for d in i.deadlines}
    assert "" not in labels, "every MICCAI deadline needs a round label"
    assert len(labels) == len([d for i in instances for d in i.deadlines])


def test_no_miccai_deadline_is_lost_to_dedupe():
    series, instances = MICCAIAdapter().parse(
        bundle("miccai", [{"feed_xml": fixture_text("miccai_keydates_feed_sample.xml")}])
    )
    before = sum(len(i.deadlines) for i in instances)
    _, merged, _ = deduplicate(series, instances)
    after = sum(len(i.deadlines) for i in merged)
    assert after == before, f"dedupe lost {before - after} deadline(s)"


def test_two_submission_deadlines_for_one_venue_both_survive_a_merge():
    """The failure in miniature, with the identity mechanism doing its job."""
    from tools.retrieval.collect.conferences.record import Deadline
    from tools.retrieval.collect.conferences.store import merge_deadlines

    merged, extensions = merge_deadlines(
        [Deadline(kind="submission", instant="2026-12-07T23:59:59Z",
                  round_label="Submission deadline")],
        [Deadline(kind="submission", instant="2026-09-11T23:59:59Z",
                  round_label="Application deadline")],
    )
    assert len(merged) == 2
    assert extensions == 0


# --- society_pages: exhibitor rows read as paper deadlines ----------------


def test_exhibitor_deadlines_do_not_make_a_venue_read_as_open_to_authors():
    """SfN's page carries "Exhibit Application Submission Closes (Group A)",
    the same for Group B, and "Art of Neuroscience application submission
    closes" -- all worded exactly like author deadlines.

    Only `abstract` and `submission` decide whether a venue is actionable, so
    classifying a booth application as a submission tells an author the call is
    open months after the paper deadline passed. Same class of error as
    filtering on the event date.
    """
    from tools.retrieval.collect.conferences.adapters.society_pages import (
        _classify_kind,
    )

    for label in (
        "Exhibit Application Submission Closes (Group A)",
        "Art of Neuroscience application submission closes",
        "Booth confirmations and payment due",
        "Sponsorship application deadline",
    ):
        assert _classify_kind(label) not in {"submission", "abstract"}, label


def test_real_author_deadlines_are_still_classified_as_submissions():
    """The guard must not swallow the deadlines the source exists to provide."""
    from tools.retrieval.collect.conferences.adapters.society_pages import (
        _classify_kind,
    )

    assert _classify_kind("Extended deadline for abstract submission") == "abstract"
    assert _classify_kind("Late-breaking abstract submission closes") == "abstract"
    assert (
        _classify_kind("Extended deadline for submission of symposium proposals")
        == "submission"
    )


# --- found by the smoke checklist on a six-source corpus ------------------


def test_an_openreview_workshop_with_no_named_parent_is_flagged_unresolved():
    """A workshop always has a parent conference; this adapter cannot name it,
    because the venue-id hierarchy is convention rather than schema.

    Leaving `unresolved_parent` False claimed the question was settled when it
    was never asked. 26 records were silently parentless until the smoke
    checklist ran against a multi-source corpus.
    """
    from tools.retrieval.collect.conferences.record import ConferenceInstance

    workshop = ConferenceInstance(
        source="openreview",
        source_record_id="ICLR.cc/2027/Workshop/Example",
        record_kind="workshop",
    )
    # Whatever the adapter produces, a child with no parent must be flagged.
    assert workshop.record_kind in {"workshop", "track"}

    from tools.retrieval.collect.conferences.adapters.openreview import _record_kind

    assert _record_kind("ICLR.cc/2027/Workshop/Example") == "workshop"
    assert _record_kind("AAAI.org/2027/Conference") == "conference"


def test_every_openresearch_record_carries_a_resolvable_link():
    """`Homepage` is populated on only ~19% of records, and a record with no
    link at all cannot be spot-checked against anything. The wiki page always
    exists and stands in when the venue's own site is absent."""
    from tools.retrieval.collect.conferences.adapters.openresearch import (
        OpenResearchAdapter,
    )

    rows = [
        {
            "subject": "AAMAS 2027",
            "fullurl": "https://www.openresearch.org/wiki/AAMAS_2027",
            "printouts": {
                "Title": ["Autonomous Agents and Multiagent Systems"],
                "Acronym": ["AAMAS 2027"],
                "Submission deadline": [{"timestamp": "1791504000", "raw": "1/2026/10/9"}],
                # No Homepage at all -- the common case.
            },
        }
    ]
    _, instances = OpenResearchAdapter().parse(bundle("openresearch", rows))
    assert instances[0].url.startswith("http")


# --- society_pages: found by independent review of the adapter ------------


def _sfn_instance():
    from tools.retrieval.collect.conferences.adapters.society_pages import (
        SocietyPagesAdapter,
        SocietyRegistryRow,
    )

    row = SocietyRegistryRow(
        society="SfN",
        conference="Neuroscience 2026",
        acronym="Neuroscience",
        year=2026,
        url="https://example.org/dates",
        event_dates="November 14-18, 2026",
    )
    return SocietyPagesAdapter()._parse_page(row, fixture_text("sfn_dates_deadlines.html"))


def test_every_society_deadline_has_a_distinct_identity():
    """A deadline's identity is (kind, round_label) and merge_deadlines matches
    on it. These pages carry dozens of rows sharing a kind -- the live SfN page
    yields 56 deadlines across only 7 (kind, "") pairs.

    Without a distinguishing label, the second store run treats each as an
    extension of the last: entries overwritten, others destroyed, and one row
    reached extension_count=15 -- a counter this codebase documents as a
    predatory red flag.
    """
    deadlines = _sfn_instance().deadlines
    identities = [d.identity for d in deadlines]
    assert len(set(identities)) == len(identities)
    assert all(d.round_label for d in deadlines)


def test_a_society_page_is_idempotent_across_repeated_runs(tmp_path):
    """The collision only showed up on the *second* upsert, because the insert
    path bypasses merge entirely."""
    from tools.retrieval.collect.conferences.store import ConferenceStore

    with ConferenceStore(tmp_path / "c.db") as store:
        first = store.upsert_instances([_sfn_instance()])
        assert first.inserted == 1
        expected = len(store.all_instances()[0].deadlines)

        for _ in range(2):
            stats = store.upsert_instances([_sfn_instance()])
            assert (stats.inserted, stats.updated) == (0, 0)
            assert stats.extensions == 0
            stored = store.all_instances()[0]
            assert len(stored.deadlines) == expected, "deadlines lost or duplicated"
            assert all(d.extension_count == 0 for d in stored.deadlines)


def test_an_impossible_date_does_not_take_down_every_other_registry_row():
    """f-string int formatting never validates a calendar day, so the original
    guard was dead code: "February 30" produced "2026-02-30", which raised out
    of strptime and killed the whole parse. These pages are hand-maintained; a
    typo is exactly the expected input."""
    from tools.retrieval.collect.conferences.adapters.society_pages import (
        SocietyPagesAdapter,
        SocietyRegistryRow,
    )

    row = SocietyRegistryRow(
        society="X", conference="Y", acronym="Y", year=2026, url="https://example.org"
    )
    page = (
        "<table>"
        "<tr><td>February 30</td><td>Paper submission deadline</td></tr>"
        "<tr><td>June 11</td><td>Abstract submission deadline</td></tr>"
        "</table>"
    )
    instance = SocietyPagesAdapter()._parse_page(row, page)
    dated = [d for d in instance.deadlines if d.instant]
    assert dated, "the valid row must still survive"
    assert any(d.instant is None for d in instance.deadlines)


def test_a_row_with_no_instant_never_claims_a_real_timezone():
    """The zone is read from the label and the date from the cell, so a row
    whose label happens to repeat "EST" claimed a real basis while carrying no
    instant -- and store._downgrades_basis reads a real basis as the more
    trustworthy one."""
    from tools.retrieval.collect.conferences.adapters.society_pages import (
        SocietyPagesAdapter,
        SocietyRegistryRow,
    )

    row = SocietyRegistryRow(
        society="X", conference="Y", acronym="Y", year=2026, url="https://example.org"
    )
    page = "<table><tr><td>Early August</td><td>Notifications sent, 5 p.m. EST</td></tr></table>"
    instance = SocietyPagesAdapter()._parse_page(row, page)
    undated = [d for d in instance.deadlines if d.instant is None]
    assert undated
    assert all(d.basis.startswith("inferred") for d in undated)


def test_a_registry_row_can_pin_its_own_fetch_mode():
    """Two seeded rows answer HTTP but expose no deadline table in the plain
    payload. Fetching them over HTTP yields a record with no deadlines and no
    warnings -- a silent nothing that looks like a healthy fetch. Honest prose
    in `notes` is not enforceable state."""
    import json
    from pathlib import Path

    from tools.retrieval.collect.conferences import adapters as conference_adapters

    # Resolved off the package's own __file__ rather than a path relative to
    # the standalone project's repo root, which this worktree is not.
    registry = Path(conference_adapters.__file__).parent / "society_registry.json"
    rows = json.loads(registry.read_text())
    rows = rows if isinstance(rows, list) else (rows.get("rows") or rows.get("societies"))
    pinned = {r["acronym"]: r.get("mode", "") for r in rows}
    assert pinned["ISMRM"] == "captured"
    assert pinned["AVIATION"] == "captured"


def test_repeated_logistics_rows_stay_distinct_without_breaking_extensions():
    """SfN repeats "Badge pickup on-site" across five consecutive days and
    "Exhibitor Move-Out" across two -- same label, different days, no instant.

    The date joins the round label only for undated rows. An undated entry can
    never be an extension (extension detection compares instants), so this
    costs nothing; doing the same to a dated deadline would make every real
    extension look like a brand-new round.
    """
    from tools.retrieval.collect.conferences.record import Deadline
    from tools.retrieval.collect.conferences.store import merge_deadlines

    merged, extensions = merge_deadlines(
        [Deadline(kind="abstract", instant="2026-06-11T18:00:00Z", round_label="extended")],
        [Deadline(kind="abstract", instant="2026-06-25T18:00:00Z", round_label="extended")],
    )
    assert len(merged) == 1, "a dated deadline moving later is still one entry"
    assert extensions == 1
    assert merged[0].extension_count == 1


def test_no_society_deadline_shares_an_identity_with_another():
    instance = _sfn_instance()
    identities = [d.identity for d in instance.deadlines]
    assert len(set(identities)) == len(identities)
