"""Every record with usable source material ends up with a description.

The first full backfill left 139 listings with no description of any kind. For
78 of them that is the honest answer -- the venue's site was blocked, gone, or
turned out to belong to a different conference, and there is nothing true to
say. For the other 61 there *was* source material and we simply failed to turn
it into prose, which is a different thing and not acceptable: a card with a
title and a blank body tells a reader nothing about whether to spend a week on
a submission.

Two changes close that gap, and these tests pin both:

* the loop asks five times instead of three, because the repair prompt was
  still converting failures into passes at attempt 3 when the old ceiling cut
  it off;
* a record whose five attempts were all rejected falls back to a description
  assembled from attributes already known correct, rather than to nothing.
"""

from __future__ import annotations

from apps.scraper.collect import extract
from apps.scraper.collect.extract import ExtractionInput, attribute_summary


class TestAttributeSummary:
    """The floor: composed from fields, so it cannot contain an invention."""

    def test_a_conference_says_what_the_listing_records(self):
        rec = ExtractionInput(
            key="conf/x",
            kind="conference",
            title="Statistical Learning and Data Science",
            acronym="SLADS",
            year_label="2026",
            series_name="Statistical Learning and Data Science",
            topics=["Machine Learning", "Statistics"],
        )
        summary = attribute_summary(rec)

        assert "Statistical Learning and Data Science (SLADS)" in summary
        assert "2026" in summary
        assert "Machine Learning, Statistics" in summary
        # The reader is told where this came from rather than left to assume
        # it was read off the venue's site.
        assert "assembled from the listing's own recorded details" in summary

    def test_a_grant_names_its_funder_and_number(self):
        rec = ExtractionInput(
            key="num:1",
            kind="grant",
            title="Biological Oceanography",
            funder="National Science Foundation",
            opportunity_number="PD-26-1650",
            categories=["Science and Technology"],
        )
        summary = attribute_summary(rec)

        assert "Biological Oceanography is a funding opportunity" in summary
        assert "National Science Foundation" in summary
        assert "PD-26-1650" in summary

    def test_it_invents_nothing_beyond_its_inputs(self):
        """The property the whole fallback rests on.

        Every token of substance must trace to a field. This is checked rather
        than asserted because it is the reason we are allowed to show this text
        at all: there is no generation step, so there is no invention.
        """
        rec = ExtractionInput(
            key="conf/y",
            kind="conference",
            title="Workshop on Graphs",
            acronym="WOG",
            year_label="2027",
            topics=["Graph Theory"],
        )
        summary = attribute_summary(rec)

        known = {
            "workshop", "on", "graphs", "wog", "2027", "graph", "theory",
            # the fixed frame the template supplies
            "is", "a", "conference", "held", "in", "it", "lists", "its",
            "subject", "areas", "as", "no", "usable", "description", "could",
            "be", "verified", "from", "the", "source", "so", "this", "summary",
            "assembled", "listing's", "own", "recorded", "details",
        }
        words = {w.strip(".,()").lower() for w in summary.split()}
        assert words <= known, f"unexplained words: {sorted(words - known)}"

    def test_an_acronym_alone_is_still_a_true_sentence(self):
        """Poor, but true, and better than a blank card."""
        rec = ExtractionInput(key="conf/z", kind="conference", acronym="TMLR")
        assert attribute_summary(rec).startswith("TMLR is a conference")

    def test_nothing_to_say_stays_empty(self):
        """A record with no name has nothing true to assert about itself."""
        assert attribute_summary(ExtractionInput(key="k", kind="conference")) == ""
        assert attribute_summary(ExtractionInput(key="k", kind="grant")) == ""


class _StubLLM:
    """Returns replies in order; counts calls."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, prompt, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else "not json"
        return type("_R", (), {"content": reply})()


GRANT = ExtractionInput(
    key="num:1",
    kind="grant",
    title="Biological Oceanography",
    funder="National Science Foundation",
    description="A" * 600,
    categories=["Oceanography"],
)


def test_the_loop_now_asks_five_times():
    """Attempts 4 and 5 exist. Two records passed at attempt 3 for every
    twelve that passed at attempt 2, so the curve had not flattened where the
    old ceiling of three sat."""
    llm = _StubLLM([])  # every reply unparseable
    extract.extract_one(llm, GRANT, "source " * 200)
    assert llm.calls == 5


def test_five_rejections_still_produce_a_description():
    """The headline: a refused record is described from its attributes."""
    llm = _StubLLM([])
    outcome = extract.extract_one(llm, GRANT, "source " * 200)

    assert outcome.status == "attributes"
    assert "Biological Oceanography" in outcome.ai_summary
    assert "National Science Foundation" in outcome.ai_summary
    # Provenance never blurs: this was not extracted from anything.
    assert outcome.summary_source == "attributes"
    assert outcome.search_text_source == "attributes"
    # Why the model's own attempts failed stays on the record.
    assert outcome.refusal_reason


def test_a_wrong_venue_is_not_dressed_up_as_a_described_one():
    """`not_the_venue` means we never found this record's page.

    Its attributes were not disproved, but nor were they confirmed, and the
    listing we did read belongs to somebody else. Showing a composed summary
    here would be the same overreach in a quieter voice.
    """
    # A schema-complete reply on purpose: a malformed one is rejected before
    # identity is ever checked, and this test is about the identity verdict.
    payload = (
        '{"summary": "' + "x" * 60 + '", "purpose": "p", "audience": "a", '
        '"topics": ["one", "two"], "field": "CS", "confidence": "high"}'
    )
    conf = ExtractionInput(
        key="conf/x", kind="conference", title="Real Venue", acronym="RV"
    )
    llm = _StubLLM([payload] * 5)
    outcome = extract.extract_one(
        llm, conf, "source " * 200, identity_text="a completely different meeting"
    )

    assert outcome.status == "not_the_venue"
    assert outcome.ai_summary == ""
    assert outcome.summary_source == ""


def test_a_model_outage_stays_retryable():
    """Never settle a record we failed to ask. Settling it here would stop the
    retry from ever happening — the same shape as the 321 model_failed rows
    one over-concurrent run once wrote."""

    class _Down:
        calls = 0

        def complete(self, prompt, **kwargs):
            _Down.calls += 1
            raise ConnectionError("relay down")

    outcome = extract.extract_one(_Down(), GRANT, "source " * 200)
    assert outcome.status == "model_failed"
    assert outcome.status in extract.RETRYABLE_STATUSES
    assert outcome.ai_summary == ""


def test_attributes_is_settled_so_it_is_not_re_billed():
    """Five attempts already bought this floor; a re-run must not buy it again."""
    assert "attributes" in extract.SETTLED_STATUSES
    assert "attributes" not in extract.RETRYABLE_STATUSES


class TestTopicCountBound:
    """One topic is an answer, not a defect.

    The bound was 2-6, carried over from the prompt's own wording and never
    examined. On the live corpus it was the single largest cause of a good
    description being discarded: 27 records had grounded prose thrown away
    purely because a narrow listing honestly has one subject -- "Riemann 200
    Göttingen topic days", NSF's "Foundations of Life".

    It also pushed the wrong way. A model told to produce two topics for a
    one-topic listing invents the second, and ``ungrounded_topic`` then rejects
    the record for the invention the bound just demanded.
    """

    @staticmethod
    def _payload(topics):
        return {
            "summary": "s" * 60, "purpose": "p", "audience": "a",
            "topics": topics, "field": "CS", "confidence": "high",
        }

    def test_one_topic_is_accepted(self):
        fails = extract.validate(
            self._payload(["graph theory"]), "graph theory " * 40, "conference",
            acronym="", title="", page_text="graph theory " * 40,
        )
        assert not [f for f in fails if f.startswith("out_of_bounds")]

    def test_zero_topics_is_still_rejected(self):
        fails = extract.validate(
            self._payload([]), "graph theory " * 40, "conference",
            acronym="", title="", page_text="graph theory " * 40,
        )
        assert any("has 0 entries" in f for f in fails)

    def test_seven_topics_is_still_rejected(self):
        """The upper bound stays: seven is topic spam, not detail."""
        fails = extract.validate(
            self._payload([f"topic {i}" for i in range(7)]),
            "topic " * 40, "conference",
            acronym="", title="", page_text="topic " * 40,
        )
        assert any("has 7 entries" in f for f in fails)

    def test_the_prompt_asks_for_what_the_validator_accepts(self):
        """A prompt demanding more than the checker requires is how the model
        was talked into inventing a topic in the first place."""
        assert "1-6 short topic strings" in extract.GRANT_PROMPT
        assert "1-6 short topic strings" in extract.CONFERENCE_PROMPT
        assert "2-6" not in extract.GRANT_PROMPT
        assert "2-6" not in extract.CONFERENCE_PROMPT
