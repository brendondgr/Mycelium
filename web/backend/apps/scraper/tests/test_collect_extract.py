"""Phase 8's structured-extraction stage, fully offline.

Nothing here touches the network or a real model. Every scenario drives
:func:`extract.extract_one` / :func:`extract.run_extraction` through a
``StubLLM`` that answers a scripted queue of replies and counts its own
calls, which is what lets these tests prove the attempt bound is honoured
rather than merely believing the docstring that says so.

The word-overlap and grounding fixtures below are not eyeballed — they were
built and checked against the real ``_words`` / ``enrich.overlap_ratio``
definitions before being written here (see the module's own docstring for
why two different word-counters are involved), so a comment stating "ratio
0.22" or "90 content words" is a verified property of the fixture text, not
an approximation.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from apps.scraper.collect import extract

# --------------------------------------------------------------------------- #
# Stub model
# --------------------------------------------------------------------------- #


class StubLLM:
    """Answers a scripted queue of replies, in order. Records every prompt.

    Raising once the queue is empty is deliberate: a test that expects at
    most N calls and gets an (N+1)th finds out immediately, rather than the
    stub silently returning something and the assertion failing somewhere
    less informative.
    """

    def __init__(self, replies: list[str | Exception]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []
        self.calls = 0

    def complete(self, prompt: str, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        self.prompts.append(prompt)
        if not self._replies:
            raise AssertionError(
                f"stub exhausted after {self.calls} calls -- extract_one "
                "made more calls than EXTRACTION_MAX_ATTEMPTS allows"
            )
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply, usage=None)


# --------------------------------------------------------------------------- #
# Fixtures — grants (rich regime: >= 80 content words, 0.45 overlap floor)
# --------------------------------------------------------------------------- #

GRANT_DESC = (
    "This program funds field research into coastal marine biodiversity, "
    "coral reef resilience, and ecosystem recovery following storm damage "
    "across small island nations. Awards support graduate researchers, "
    "university laboratories, and community conservation groups conducting "
    "long-term monitoring of fish populations, seagrass meadows, mangrove "
    "forests, and nearshore water quality. Funded teams collaborate with "
    "local fishing cooperatives, environmental agencies, and coastal "
    "municipalities to design adaptive management plans, restore degraded "
    "habitats, and train the next generation of marine scientists. "
    "Preference is given to proposals that combine field sampling, remote "
    "sensing, and community outreach, and that report results in "
    "accessible formats for policymakers and residents of vulnerable "
    "coastal regions."
)

#: 90 distinct content words per extract._words -- comfortably over the
#: 80-word threshold, so this always takes the overlap-floor regime.
GRANT_ELIGIBILITY = "Open to accredited research institutions."

GRANT_SUMMARY = (
    "This grant funds coastal marine biodiversity research, including "
    "coral reef resilience and mangrove forest recovery after storms."
)
GRANT_PURPOSE = "The foundation exists to support marine conservation science."
GRANT_AUDIENCE = "Graduate researchers and university marine laboratories."
#: enrich.overlap_ratio(GRANT_SUMMARY + " " + GRANT_PURPOSE + " " +
#: GRANT_AUDIENCE, grant_source_text) == 0.74 -- well clear of the 0.45 floor.

GOOD_GRANT_PAYLOAD = {
    "summary": GRANT_SUMMARY,
    "purpose": GRANT_PURPOSE,
    "audience": GRANT_AUDIENCE,
    "research_areas": ["coastal conservation", "marine biodiversity"],
    "eligibility": GRANT_ELIGIBILITY,
    "award_summary": "",
    "confidence": "high",
}


def grant_input(**overrides: object) -> extract.ExtractionInput:
    base = dict(
        key="grants:test-1",
        kind="grant",
        title="Coastal Marine Biodiversity Grant",
        funder="Example Ocean Foundation",
        opportunity_number="OCEAN-2026",
        description=GRANT_DESC,
        eligibility=GRANT_ELIGIBILITY,
        categories=["marine biology", "conservation"],
    )
    base.update(overrides)
    return extract.ExtractionInput(**base)


def grant_source_text(rec: extract.ExtractionInput | None = None) -> str:
    return extract._grant_source_text(rec or grant_input())


# --------------------------------------------------------------------------- #
# Fixtures — conferences, rich regime (a real fetched-page-sized body)
# --------------------------------------------------------------------------- #

#: 127 distinct content words per extract._words -- a stand-in for a fetched
#: conference page, deliberately free of every word the "half-grounded"
#: prose below uses, and free of "marine"/"biology"/"retreat" for the
#: wrong-venue test.
RICH_BODY = (
    "The International Workshop on Spacecraft Systems Engineering brings "
    "together researchers, mission architects, and industry engineers to "
    "examine advances in satellite communications, structural analysis, "
    "power control, power distribution, computational modeling, sensor "
    "calibration, mission planning, orbital mechanics, guidance software, "
    "fault diagnosis, autonomous navigation, robotic assembly, materials "
    "science, radiation hardening, software verification, systems "
    "integration, ground station operations, launch vehicle interfaces, "
    "payload design, attitude determination, formation flying, deep space "
    "communication, planetary science instrumentation, cybersecurity for "
    "space systems, machine learning applications, data compression "
    "techniques, redundancy planning, reliability engineering, cost "
    "modeling, procurement strategy, collaboration frameworks, regulatory "
    "compliance, environmental testing, vibration analysis, electromagnetic "
    "compatibility, battery chemistry, propellant control, docking "
    "mechanisms, robotic manipulators, human factors, crew training "
    "simulations, emergency procedures, wreckage budgeting, constellation "
    "deployment, spectrum allocation, encryption protocols, signal "
    "processing, command sequencing, anomaly resolution, lifecycle "
    "management, supply chain coordination, satellite components, and "
    "workforce development programs across the aerospace sector."
)

#: enrich.overlap_ratio against RICH_BODY == 0.92 -- well clear of the floor.
GROUNDED_CONFERENCE_PROSE = (
    "This workshop covers spacecraft systems engineering, orbital "
    "mechanics and guidance software for mission architects and industry "
    "engineers."
)

#: enrich.overlap_ratio against RICH_BODY == 0.2222... -> "0.22" at 2 d.p.
#: (2 of its 9 content words -- "orbital", "guidance" -- are on the page).
#: This is the EXP-2026-08-007 RESULTS.md "half-grounded (overlap 0.22)"
#: case, reproduced with hand-built text rather than the experiment's own
#: corpus sample.
HALF_GROUNDED_CONFERENCE_PROSE = (
    "Coral reef genetics and migratory whale songs draw orbital guidance."
)

GROUNDED_TOPICS = ["orbital mechanics", "guidance systems"]


def conference_input(**overrides: object) -> extract.ExtractionInput:
    base = dict(
        key="conf:test-1",
        kind="conference",
        title="Spacecraft Systems Engineering Workshop",
        acronym="SSEW",
        year_label="2027",
        cfp_text=RICH_BODY,
        url="https://ssew.example.org/2027/",
        series_name="International Workshop on Spacecraft Systems Engineering",
        field_codes=["AE"],
        topics=["satellite communications", "orbital mechanics"],
    )
    base.update(overrides)
    return extract.ExtractionInput(**base)


# --------------------------------------------------------------------------- #
# Fixtures — conferences, stub regime (< 80 content words: no fetched page)
# --------------------------------------------------------------------------- #

#: 15 distinct content words per extract._words -- well under the 80-word
#: floor, so grounding_failures takes the no-invention branch, exactly the
#: median case measured on the live corpus (cfp_text empty on every row).
STUB_SOURCE = (
    "Conference: Foo Symposium on Applied Robotics\n"
    "Acronym: FOOSYM 2026\nSeries: Foo Society Symposium\n"
    "CCF areas: AI\nTopics: robotics, control systems"
)


def stub_conference_input(**overrides: object) -> extract.ExtractionInput:
    base = dict(
        key="conf:test-stub",
        kind="conference",
        title="Foo Symposium on Applied Robotics",
        acronym="FOOSYM",
        year_label="2026",
        cfp_text="",
        url="",
        series_name="Foo Society Symposium",
        field_codes=["AI"],
        topics=["robotics", "control systems"],
    )
    base.update(overrides)
    return extract.ExtractionInput(**base)


def stub_payload(summary: str, **overrides: object) -> dict:
    base = {
        "summary": summary,
        "purpose": "",
        "audience": "",
        "topics": ["robotics", "control systems"],
        "field": "robotics",
        "confidence": "medium",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Schema validation and the bounded repair loop
# --------------------------------------------------------------------------- #


def test_missing_key_is_malformed_and_a_fixing_repair_is_accepted():
    incomplete = {k: v for k, v in GOOD_GRANT_PAYLOAD.items() if k != "eligibility"}
    stub = StubLLM([json.dumps(incomplete), json.dumps(GOOD_GRANT_PAYLOAD)])

    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    assert outcome.status == "ok"
    assert outcome.attempts == 2
    assert stub.calls == 2
    # The repair prompt named the SPECIFIC failure, not a generic retry.
    assert "missing key 'eligibility'" in stub.prompts[1]
    assert "rejected" in stub.prompts[1]
    assert outcome.ai_summary == GRANT_SUMMARY
    assert outcome.search_text_source == "extracted"


def test_three_malformed_attempts_fall_back_to_raw_with_no_ai_summary():
    always_missing_a_key = json.dumps(
        {k: v for k, v in GOOD_GRANT_PAYLOAD.items() if k != "award_summary"}
    )
    stub = StubLLM([always_missing_a_key] * 3)

    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    assert stub.calls == 3
    assert outcome.attempts == 3
    assert outcome.status == "refused"
    assert outcome.search_text_source == "raw"
    assert outcome.ai_summary == ""
    assert outcome.ai_fields is None
    assert "malformed" in outcome.refusal_reason


def test_attempt_counter_never_exceeds_the_bound():
    # A stub that would keep failing forever if allowed to; the queue itself
    # enforces that extract_one never asks for a 4th call.
    stub = StubLLM(["not json at all"] * extract.EXTRACTION_MAX_ATTEMPTS)

    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    assert stub.calls == extract.EXTRACTION_MAX_ATTEMPTS
    assert outcome.attempts == extract.EXTRACTION_MAX_ATTEMPTS
    assert outcome.status in extract.RETRYABLE_STATUSES | extract.SETTLED_STATUSES


# --------------------------------------------------------------------------- #
# Four distinct refusals (plan §8.3 step 3)
# --------------------------------------------------------------------------- #


def test_hallucinated_date_is_refused_as_unsupported_claim():
    invented_year = stub_payload(
        "The symposium was first convened in 1998 and focuses on applied "
        "robotics."
    )
    stub = StubLLM([json.dumps(invented_year)] * 3)

    outcome = extract.extract_one(
        stub, stub_conference_input(), STUB_SOURCE, identity_text=STUB_SOURCE
    )

    assert stub.calls == 3
    assert outcome.status == "refused"
    assert "unsupported_claim" in outcome.refusal_reason
    assert "1998" in outcome.refusal_reason
    assert outcome.search_text_source == "raw"
    assert outcome.ai_summary == ""


def test_year_present_in_the_source_is_not_a_hallucination():
    # The mirror image of the case above: '2026' genuinely appears in
    # STUB_SOURCE ("Acronym: FOOSYM 2026"), so citing it is not an invention.
    present_year = stub_payload(
        "The 2026 symposium focuses on applied robotics and control systems."
    )
    fails = extract.grounding_failures(present_year["summary"], STUB_SOURCE)
    assert fails == []


def test_ungrounded_topic_is_its_own_refusal():
    payload = dict(GOOD_GRANT_PAYLOAD)
    payload["research_areas"] = ["coastal conservation", "orbital telemetry systems"]
    stub = StubLLM([json.dumps(payload)] * 3)

    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    assert outcome.status == "refused"
    assert "ungrounded_topic" in outcome.refusal_reason
    assert "orbital telemetry systems" in outcome.refusal_reason
    # The grounded item must NOT have been the one flagged.
    assert "'coastal conservation'" not in outcome.refusal_reason


def test_wrong_venue_is_its_own_refusal():
    # The header this module composes always names the record's own
    # acronym -- checking identity against that would be circular. The page
    # actually fetched (RICH_BODY) never mentions marine biology at all, so
    # identity must fail using ``identity_text``, not the header in
    # ``source_text``.
    header_claims_mbio = (
        "Conference: International Marine Biology Retreat\n"
        "Acronym: MBIO 2026\n\n" + RICH_BODY
    )
    payload = stub_payload(
        GROUNDED_CONFERENCE_PROSE, topics=GROUNDED_TOPICS, confidence="high"
    )
    rec = conference_input(
        title="International Marine Biology Retreat",
        acronym="MBIO",
        cfp_text="",  # irrelevant here: source_text is passed explicitly below
    )
    stub = StubLLM([json.dumps(payload)] * 3)

    outcome = extract.extract_one(
        stub, rec, header_claims_mbio, identity_text=RICH_BODY
    )

    assert outcome.status == "not_the_venue"
    assert "not_the_venue" in outcome.refusal_reason


def test_prose_written_from_priors_is_refused_as_ungrounded():
    payload = stub_payload(
        HALF_GROUNDED_CONFERENCE_PROSE, topics=GROUNDED_TOPICS, confidence="high"
    )
    stub = StubLLM([json.dumps(payload)] * 3)

    outcome = extract.extract_one(
        stub, conference_input(), RICH_BODY, identity_text=RICH_BODY
    )

    assert stub.calls == 3
    assert outcome.status == "refused"
    assert "ungrounded_prose" in outcome.refusal_reason
    assert "0.22" in outcome.refusal_reason
    assert outcome.search_text_source == "raw"
    assert outcome.ai_summary == ""


# --------------------------------------------------------------------------- #
# A repair that fixes the cited failure is accepted (conference, rich regime)
# --------------------------------------------------------------------------- #


def test_a_repair_that_grounds_the_prose_is_accepted():
    bad = stub_payload(
        HALF_GROUNDED_CONFERENCE_PROSE, topics=GROUNDED_TOPICS, confidence="high"
    )
    fixed = stub_payload(
        GROUNDED_CONFERENCE_PROSE, topics=GROUNDED_TOPICS, confidence="high"
    )
    stub = StubLLM([json.dumps(bad), json.dumps(fixed)])

    outcome = extract.extract_one(
        stub, conference_input(), RICH_BODY, identity_text=RICH_BODY
    )

    assert outcome.status == "ok"
    assert outcome.attempts == 2
    assert stub.calls == 2
    assert "ungrounded_prose" in stub.prompts[1]
    assert outcome.search_text_source == "extracted"
    assert "orbital mechanics" in outcome.search_text  # topics fold into it


# --------------------------------------------------------------------------- #
# Both grounding regimes fire (plan §8.5b)
# --------------------------------------------------------------------------- #


def test_rich_regime_passes_grounded_prose():
    assert extract.grounding_failures(GROUNDED_CONFERENCE_PROSE, RICH_BODY) == []


def test_rich_regime_refuses_half_grounded_prose_at_point_two_two():
    assert len(extract._words(RICH_BODY)) >= extract.MIN_SOURCE_WORDS_FOR_OVERLAP

    fails = extract.grounding_failures(HALF_GROUNDED_CONFERENCE_PROSE, RICH_BODY)

    assert len(fails) == 1
    assert fails[0].startswith("ungrounded_prose")
    assert "0.22" in fails[0]


def test_stub_regime_refuses_an_invented_year():
    prose = "The symposium was first convened in 1998 and focuses on robots."
    fails = extract.grounding_failures(prose, STUB_SOURCE)
    assert len(fails) == 1
    assert fails[0].startswith("unsupported_claim")
    assert "1998" in fails[0]
    assert len(extract._words(STUB_SOURCE)) < extract.MIN_SOURCE_WORDS_FOR_OVERLAP


def test_stub_regime_passes_a_year_that_is_on_the_page():
    prose = "The 2026 symposium focuses on applied robotics."
    assert extract.grounding_failures(prose, STUB_SOURCE) == []


# --------------------------------------------------------------------------- #
# Apply or refuse (plan §8, item 5)
# --------------------------------------------------------------------------- #


def test_apply_to_metadata_verified():
    stub = StubLLM([json.dumps(GOOD_GRANT_PAYLOAD)])
    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    metadata: dict = {"stale": "left over from a prior refusal"}
    extract.apply_to_metadata(metadata, outcome)

    assert metadata["ai_summary"] == GRANT_SUMMARY
    assert metadata["ai_fields"]["confidence"] == "high"
    assert metadata["summary_source"] == "extracted"
    assert metadata["search_text_source"] == "extracted"
    assert "extraction_refusal" not in metadata


def test_apply_to_metadata_refused_shows_no_ai_summary():
    bad = json.dumps({k: v for k, v in GOOD_GRANT_PAYLOAD.items() if k != "summary"})
    stub = StubLLM([bad] * 3)
    outcome = extract.extract_one(stub, grant_input(), grant_source_text())

    metadata: dict = {"ai_summary": "a previous, now-stale summary"}
    extract.apply_to_metadata(metadata, outcome)

    assert "ai_summary" not in metadata
    assert "ai_fields" not in metadata
    assert "summary_source" not in metadata
    assert metadata["search_text_source"] == "raw"
    assert "malformed" in metadata["extraction_refusal"]


# --------------------------------------------------------------------------- #
# The newness gate (plan §8, item 8)
# --------------------------------------------------------------------------- #


def test_newness_gate_only_processes_selected_keys():
    rec_a = grant_input(key="grants:a")
    rec_b = grant_input(key="grants:b", title="A Different Grant")
    stub = StubLLM([json.dumps(GOOD_GRANT_PAYLOAD)])  # only enough for one

    outcomes = extract.run_extraction(
        [rec_a, rec_b], llm_client=stub, only_keys={"grants:a"}
    )

    assert set(outcomes) == {"grants:a"}
    assert stub.calls == 1


def test_full_backfill_processes_every_record_when_only_keys_is_none():
    rec_a = grant_input(key="grants:a")
    rec_b = grant_input(key="grants:b", title="A Different Grant")
    stub = StubLLM([json.dumps(GOOD_GRANT_PAYLOAD)] * 2)

    outcomes = extract.run_extraction([rec_a, rec_b], llm_client=stub, only_keys=None)

    assert set(outcomes) == {"grants:a", "grants:b"}
    assert stub.calls == 2


# --------------------------------------------------------------------------- #
# Checkpointing and the page_hash fix (plan §8, "two defects")
# --------------------------------------------------------------------------- #


def test_checkpoint_skips_a_settled_record_until_its_source_changes():
    checkpoint = extract.DictCheckpoint()
    rec = grant_input()

    first = StubLLM([json.dumps(GOOD_GRANT_PAYLOAD)])
    extract.run_extraction([rec], llm_client=first, checkpoint=checkpoint)
    assert first.calls == 1

    # Second run over the SAME, unchanged source: the settled verdict is a
    # cache hit, so the model must not be called at all. A stub with an
    # empty reply queue proves it -- any call raises.
    second = StubLLM([])
    outcomes = extract.run_extraction([rec], llm_client=second, checkpoint=checkpoint)
    assert second.calls == 0
    assert outcomes[rec.key].status == "ok"

    # Third run: the source has moved (the defect the recon proved on live
    # data -- a page that changes after a settled `ok` was never re-read).
    # A hash mismatch must force a fresh extraction even though the prior
    # verdict was settled.
    changed = grant_input(description=GRANT_DESC + " A newly added paragraph.")
    third_payload = dict(GOOD_GRANT_PAYLOAD)
    third_payload["award_summary"] = "Up to $50,000 per award."
    third = StubLLM([json.dumps(third_payload)])
    outcomes = extract.run_extraction(
        [changed], llm_client=third, checkpoint=checkpoint
    )
    assert third.calls == 1
    award = outcomes[changed.key].ai_fields["award_summary"]
    assert award == "Up to $50,000 per award."
