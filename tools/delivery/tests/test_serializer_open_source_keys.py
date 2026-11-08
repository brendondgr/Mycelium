"""The opportunity cards read the keys the open collector actually writes.

The sibling file ``test_source_line_migration.py`` covers the first two fields
caught in this class of failure (the conference venue line and the conference
description). This one covers the rest of them, because the failure repeats
once per field and is invisible every time:

a serializer method reads a Pivot-era metadata key, the open collector writes a
different one, nothing raises, and the field serializes as ``""`` / ``[]`` /
``False`` for **every row in the corpus**. A green suite says nothing about it —
each of these methods had either no test at all or a test that fed it the very
Pivot-shaped metadata the collector stopped producing.

Measured against the live corpus at the time of the fix (912 conferences, 2,171
grants, all collector-written): ``event_dates`` 0, ``event_date`` 0,
``abstract_open`` 0, ``manuscript_open`` 0, ``keywords`` 0, ``matched_subjects``
0, ``sponsor`` 0, ``matched_topics`` 0, ``deadline_kind`` 0.

Every test below names the branch it pins. Delete the Pivot halves — and the
fallbacks they cover — together, once no Pivot-era row survives, not before.
"""

from __future__ import annotations

from types import SimpleNamespace

from tools.delivery.serializers import (
    ConferenceSerializer,
    GrantSerializer,
    SearchResultSerializer,
)

#: Every "is it still upcoming?" answer below is relative to this, passed in the
#: serializer context exactly as the feed views pass it (one clock read per
#: request). Nothing here reads the real clock, so these tests do not rot.
TODAY = "2026-08-17"


def _score(meta: dict, **signals):
    """The three attributes these readers touch on a ``RelevanceScore``."""
    return SimpleNamespace(
        content_id="4f0d9d5e-0000-0000-0000-000000000001",
        content=SimpleNamespace(metadata=meta),
        signals=signals,
    )


def _conference(today: str = TODAY) -> ConferenceSerializer:
    return ConferenceSerializer(context={"today": today})


def _grant(today: str = TODAY) -> GrantSerializer:
    return GrantSerializer(context={"today": today})


class TestConferenceEventDates:
    """The card's human "when is it" line.

    ``event_dates`` is Pivot's key; the collector writes ``event_dates_text``.
    No rebuilt conference carries the old key, so every card lost its date line.
    """

    def test_reads_the_collector_key(self):
        meta = {"event_dates_text": "Nov 10 2026"}
        assert _conference().get_event_dates(_score(meta)) == "Nov 10 2026"

    def test_falls_back_to_the_pivot_key(self):
        """The case a swap would break: every conference ingested before the
        migration, which carries only ``event_dates``."""
        assert (
            _conference().get_event_dates(_score({"event_dates": "10 Nov 2026"}))
            == "10 Nov 2026"
        )

    def test_collector_key_wins_when_both_are_present(self):
        meta = {"event_dates_text": "Nov 10 2026", "event_dates": "stale"}
        assert _conference().get_event_dates(_score(meta)) == "Nov 10 2026"

    def test_a_bare_epoch_is_refused_not_displayed(self):
        """261 of 912 live conferences (all ``conf:openreview``) carry a raw
        millisecond epoch here, because the adapter passes its source's
        ``start_date`` through untouched. Printing "1797552000000" on a card is
        worse than printing nothing; the fix belongs in the adapter."""
        meta = {"event_dates_text": "1797552000000"}
        assert _conference().get_event_dates(_score(meta)) == ""

    def test_a_refused_epoch_still_falls_through_to_the_pivot_key(self):
        meta = {"event_dates_text": "1797552000000", "event_dates": "10 Nov 2026"}
        assert _conference().get_event_dates(_score(meta)) == "10 Nov 2026"

    def test_a_year_inside_a_real_date_string_is_not_mistaken_for_an_epoch(self):
        """Only a *bare* run of digits is refused — the guard must not eat a
        date string that merely contains numbers."""
        meta = {"event_dates_text": "December 17, 2026 - December 19, 2026"}
        assert _conference().get_event_dates(_score(meta)) == (
            "December 17, 2026 - December 19, 2026"
        )

    def test_whitespace_is_collapsed(self):
        meta = {"event_dates_text": "Nov 10\n  2026"}
        assert _conference().get_event_dates(_score(meta)) == "Nov 10 2026"

    def test_nothing_at_all_is_empty_not_none(self):
        assert _conference().get_event_dates(_score({})) == ""

    def test_the_search_card_reads_the_same_chain(self):
        """A venue found through search and the same venue in the feed must not
        print different dates; both go through one helper."""
        serializer = SearchResultSerializer()
        item = SimpleNamespace(metadata={"event_dates_text": "Nov 10 2026"})
        assert serializer.get_event_dates(item) == "Nov 10 2026"


class TestConferenceEventDate:
    """The ISO date the event-date window filter and sort are built on.

    ``event_date`` is Pivot's key; the collector writes ``event_start``. A
    filter over a field that is empty on every row silently matches nothing.
    """

    def test_reads_the_collector_key(self):
        assert (
            _conference().get_event_date(_score({"event_start": "2026-11-10"}))
            == "2026-11-10"
        )

    def test_falls_back_to_the_pivot_key(self):
        assert (
            _conference().get_event_date(_score({"event_date": "2026-11-10"}))
            == "2026-11-10"
        )

    def test_collector_key_wins_when_both_are_present(self):
        meta = {"event_start": "2026-11-10", "event_date": "2026-01-01"}
        assert _conference().get_event_date(_score(meta)) == "2026-11-10"

    def test_a_free_text_date_is_refused(self):
        """This field's contract is "parseable ISO or empty". Handing a client
        that sorts by it "February 22 - March 1, 2022" would reorder the feed
        by whatever its parser made of the string."""
        meta = {"event_start": "February 22 - March 1, 2022"}
        assert _conference().get_event_date(_score(meta)) == ""

    def test_a_partial_date_is_refused(self):
        assert _conference().get_event_date(_score({"event_start": "2026-11"})) == ""

    def test_the_human_date_string_is_never_parsed_into_this_field(self):
        """``event_dates_text`` is deliberately not in the chain — deriving a
        date from it needs a parser, and a mis-parsed date is a silently
        mis-sorted feed."""
        meta = {"event_dates_text": "Nov 10 2026"}
        assert _conference().get_event_date(_score(meta)) == ""

    def test_nothing_at_all_is_empty_not_none(self):
        assert _conference().get_event_date(_score({})) == ""


def _deadline(kind: str, instant: str, **extra) -> dict:
    """One ``deadlines_structured`` entry, in the collector's own shape."""
    return {
        "kind": kind,
        "instant": instant,
        "basis": "UTC",
        "raw": instant,
        "source": "test",
        **extra,
    }


class TestConferenceSubmissionOpen:
    """"Can I still submit to this?", derived rather than read.

    ``abstract_open`` / ``manuscript_open`` are Pivot keys the collector never
    writes, so both read ``False`` for the whole rebuilt corpus while the dates
    that decide them sat in ``deadlines_structured`` (174 abstract and 750
    submission entries live). They are also not facts that can be frozen at
    ingest: a flag written yesterday is wrong the morning after the deadline.
    """

    def test_a_future_abstract_deadline_is_open(self):
        meta = {"deadlines_structured": [_deadline("abstract", "2026-09-15T11:59:00Z")]}
        assert _conference().get_abstract_open(_score(meta)) is True

    def test_a_passed_abstract_deadline_is_closed(self):
        meta = {"deadlines_structured": [_deadline("abstract", "2026-08-16T23:59:00Z")]}
        assert _conference().get_abstract_open(_score(meta)) is False

    def test_deadline_day_itself_still_counts_as_open(self):
        """Same cut as ``deadlines_projection._conference_specs`` (``due <
        today`` is what drops an entry), so a card and its reminder never
        disagree on the last day."""
        meta = {"deadlines_structured": [_deadline("abstract", f"{TODAY}T23:59:00Z")]}
        assert _conference().get_abstract_open(_score(meta)) is True

    def test_submission_is_the_manuscript_family_not_the_abstract_one(self):
        """The collector calls the full-paper deadline ``submission``; the
        projection renames it MANUSCRIPT. Both flags must answer independently
        — a venue past its abstract date but still taking papers is the normal
        case, not an edge one."""
        meta = {
            "deadlines_structured": [
                _deadline("abstract", "2026-08-01T23:59:00Z"),
                _deadline("submission", "2026-09-15T23:59:00Z"),
            ]
        }
        card = _conference()
        assert card.get_abstract_open(_score(meta)) is False
        assert card.get_manuscript_open(_score(meta)) is True

    def test_the_projections_own_word_for_it_is_accepted_too(self):
        """An array already written in ``ContentDeadline``'s vocabulary must
        not be silently dropped for using the other of the two names."""
        meta = {
            "deadlines_structured": [_deadline("manuscript", "2026-09-15T23:59:00Z")]
        }
        assert _conference().get_manuscript_open(_score(meta)) is True

    def test_a_notification_date_never_reads_as_open(self):
        """The domain rule the whole deadline stack is built on: only abstract
        and submission mean "I can still act on this". A notification is
        something the venue does *to* a submitter."""
        meta = {
            "deadlines_structured": [
                _deadline("notification", "2026-12-01T23:59:00Z"),
                _deadline("camera_ready", "2026-12-20T23:59:00Z"),
                _deadline("registration", "2026-11-30T23:59:00Z"),
            ]
        }
        card = _conference()
        assert card.get_abstract_open(_score(meta)) is False
        assert card.get_manuscript_open(_score(meta)) is False

    def test_the_event_date_never_gates_openness(self):
        """A venue whose submissions closed last week is closed, however far
        away the event still is. The event date lives outside this array
        precisely so it can never be mistaken for a deadline."""
        meta = {
            "event_start": "2026-12-01",
            "deadlines_structured": [_deadline("submission", "2026-08-01T23:59:00Z")],
        }
        assert _conference().get_manuscript_open(_score(meta)) is False

    def test_an_unparseable_instant_is_not_open(self):
        """A TBD or malformed date is not evidence of an open call."""
        meta = {"deadlines_structured": [_deadline("submission", "TBD")]}
        assert _conference().get_manuscript_open(_score(meta)) is False

    def test_a_missing_array_falls_back_to_the_pivot_flag(self):
        """Pivot-era rows carry the flag and no structured array; they must keep
        rendering what they always did."""
        card = _conference()
        assert card.get_abstract_open(_score({"abstract_open": True})) is True
        assert card.get_manuscript_open(_score({"manuscript_open": True})) is True

    def test_without_a_today_in_context_only_the_pivot_flag_answers(self):
        """"Still upcoming" has no answer without a reference date, and this
        serializer deliberately does not reach for the clock to invent one."""
        meta = {"deadlines_structured": [_deadline("abstract", "2026-09-15T11:59:00Z")]}
        assert _conference(today="").get_abstract_open(_score(meta)) is False
        assert _conference(today="").get_abstract_open(_score({"abstract_open": True}))

    def test_nothing_at_all_is_false_not_none(self):
        assert _conference().get_abstract_open(_score({})) is False
        assert _conference().get_manuscript_open(_score({})) is False


class TestConferenceTopics:
    """The two topic fields: same values, two documented shapes.

    ``keywords`` (space-joined blob) and ``matched_subjects`` (semicolon-
    delimited chips) are both Pivot keys. The collector writes ``topics``, and
    the verified extraction writes ``ai_fields["topics"]`` — 776 of 912
    conferences carry those against ``topics``' 70. Both shapes are load-bearing
    on the client (``conference-filters.tsx`` splits the second on ";"), so only
    the source of the values changed.
    """

    AI = {"ai_fields": {"topics": ["Cyber Security", "Systems and Networks"]}}

    def test_prefers_the_verified_extraction(self):
        assert _conference().get_matched_subjects(_score(self.AI)) == (
            "Cyber Security; Systems and Networks"
        )

    def test_the_extraction_wins_over_the_collector_key(self):
        meta = {**self.AI, "topics": ["Graphics"]}
        assert _conference().get_matched_subjects(_score(meta)) == (
            "Cyber Security; Systems and Networks"
        )

    def test_falls_back_to_the_collector_key(self):
        meta = {"topics": ["Graphics", "Computing Theory"]}
        assert _conference().get_matched_subjects(_score(meta)) == (
            "Graphics; Computing Theory"
        )

    def test_an_empty_collector_list_falls_through_to_the_pivot_key(self):
        """``topics`` is ``[]`` on most openreview records — an empty list is an
        absence, not an answer."""
        meta = {"topics": [], "matched_subjects": "Physics; Optics"}
        assert _conference().get_matched_subjects(_score(meta)) == "Physics; Optics"

    def test_falls_back_to_the_pivot_key(self):
        meta = {"matched_subjects": "Physics; Optics"}
        assert _conference().get_matched_subjects(_score(meta)) == "Physics; Optics"

    def test_keywords_keeps_pivots_space_joined_shape(self):
        """The two fields differ by delimiter, and that difference is the
        contract: the card chips ``matched_subjects`` precisely because
        ``keywords`` is an unsplittable blob."""
        assert _conference().get_keywords(_score(self.AI)) == (
            "Cyber Security Systems and Networks"
        )

    def test_keywords_falls_back_to_the_pivot_key(self):
        meta = {"keywords": "photonics optics"}
        assert _conference().get_keywords(_score(meta)) == "photonics optics"

    def test_nothing_at_all_is_an_empty_string_not_a_list(self):
        card = _conference()
        assert card.get_keywords(_score({})) == ""
        assert card.get_matched_subjects(_score({})) == ""


class TestGrantSponsor:
    """The funder line — the single most identifying thing on a grant card.

    ``sponsor`` is Pivot's key; the collector writes ``funder``. All 2,171
    rebuilt grants rendered a blank sponsor, and the sponsor facet with it.
    """

    def test_reads_the_collector_key(self):
        assert (
            _grant().get_sponsor(_score({"funder": "National Science Foundation"}))
            == "National Science Foundation"
        )

    def test_prefers_the_pivot_key_when_present(self):
        """Same order as ``daily_report._source_line``, deliberately: a card and
        the report line about the same grant must name the same funder."""
        meta = {"sponsor": "NSF", "funder": "National Science Foundation"}
        assert _grant().get_sponsor(_score(meta)) == "NSF"

    def test_the_raw_funder_wins_over_the_canonical_one(self):
        """They differ on 208 of 2,171 rows; the raw name is what the report
        prints, so the card prints it too."""
        meta = {"funder": "NSF Directorate", "funder_canonical": "NSF"}
        assert _grant().get_sponsor(_score(meta)) == "NSF Directorate"

    def test_the_canonical_name_is_the_last_resort(self):
        meta = {"funder": "", "funder_canonical": "European Commission"}
        assert _grant().get_sponsor(_score(meta)) == "European Commission"

    def test_nothing_at_all_is_empty_not_none(self):
        assert _grant().get_sponsor(_score({})) == ""

    def test_the_search_card_reads_the_same_chain(self):
        serializer = SearchResultSerializer()
        item = SimpleNamespace(metadata={"funder": "NIH"})
        assert serializer.get_sponsor(item) == "NIH"


class TestGrantMatchedTopics:
    """The grant topic chips and the Opportunities topic facet.

    ``matched_topics`` is Pivot's key; the facet was derived from an empty
    string on every row. Semicolon-delimited, because
    ``grant-filters.tsx::splitTopics`` splits on ";".
    """

    AI = {"ai_fields": {"research_areas": ["Artificial Intelligence", "AI Readiness"]}}

    def test_prefers_the_verified_extraction(self):
        assert _grant().get_matched_topics(_score(self.AI)) == (
            "Artificial Intelligence; AI Readiness"
        )

    def test_the_extraction_wins_over_the_sources_own_categories(self):
        """2,150 of 2,171 rows carry the extraction; it reads like a research
        area rather than a funding bucket."""
        meta = {**self.AI, "categories": ["Science and Technology"]}
        assert _grant().get_matched_topics(_score(meta)) == (
            "Artificial Intelligence; AI Readiness"
        )

    def test_falls_back_to_the_sources_categories(self):
        meta = {"categories": ["Health", "Income Security and Social Services"]}
        assert _grant().get_matched_topics(_score(meta)) == (
            "Health; Income Security and Social Services"
        )

    def test_eu_call_identifiers_never_become_topics(self):
        """``topic_keywords`` is the collector's most topic-sounding key and is
        deliberately not in the chain: all 579 live rows that carry it are
        ``grants:eu_portal``, and every value is a call identifier. A facet
        sidebar full of machine codes is worse than an empty one."""
        meta = {"topic_keywords": ["HORIZON-JU-EUROHPC-2026-QTI-13-01"]}
        assert _grant().get_matched_topics(_score(meta)) == ""

    def test_falls_back_to_the_pivot_key(self):
        meta = {"matched_topics": "Photonics; Optics"}
        assert _grant().get_matched_topics(_score(meta)) == "Photonics; Optics"

    def test_nothing_at_all_is_an_empty_string_not_a_list(self):
        assert _grant().get_matched_topics(_score({})) == ""


class TestDeadlineKind:
    """Which deadline ``deadline_date`` is — or nothing at all.

    ``signals["next_kind"]`` is only ever written by the fellowship ingest, so
    every grant and conference served "" here while its ``deadline_date`` sat
    next to it. The rule that decides the fallback is correspondence: the kind
    must name the *same* deadline the date points at. Telling a reader the
    abstract closes on the manuscript's date is worse than telling them nothing.
    """

    def test_a_dated_grant_is_an_application_deadline(self):
        score = _score({}, deadline_date="2026-09-15")
        assert _grant().get_deadline_kind(score) == "application"

    def test_a_rolling_grant_names_nothing(self):
        """An empty ``deadline_date`` is the collector's "rolling, never
        expires"; there is no deadline to name."""
        assert _grant().get_deadline_kind(_score({}, deadline_date="")) == ""

    def test_a_persisted_kind_still_wins(self):
        """The fellowship path, pinned: its ingest writes ``next_kind`` and this
        change must not step on it."""
        score = _score({}, deadline_date="2026-09-15", next_kind="application")
        assert _grant().get_deadline_kind(score) == "application"

    def test_a_conference_names_the_abstract_round(self):
        meta = {
            "deadlines_structured": [_deadline("abstract", "2026-09-15T11:59:00Z")]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == "abstract"

    def test_a_conference_names_the_submission_round_as_manuscript(self):
        meta = {
            "deadlines_structured": [_deadline("submission", "2026-09-15T23:59:00Z")]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == "manuscript"

    def test_it_names_the_round_the_shown_date_belongs_to(self):
        """The whole point. With an abstract date already passed and the
        manuscript date being the one displayed, "abstract" would be a lie
        about a date the reader can see."""
        meta = {
            "deadlines_structured": [
                _deadline("abstract", "2026-07-01T23:59:00Z"),
                _deadline("submission", "2026-09-15T23:59:00Z"),
            ]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == "manuscript"

    def test_two_rounds_on_one_day_resolve_to_the_earlier_instant(self):
        """Same ``min``-over-moments rule ``mapping.py`` used to choose the date
        in the first place, so the two cannot disagree."""
        meta = {
            "deadlines_structured": [
                _deadline("submission", "2026-09-15T23:59:00Z"),
                _deadline("abstract", "2026-09-15T11:59:00Z"),
            ]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == "abstract"

    def test_a_non_submission_round_is_never_named(self):
        """``deadline_date`` gates on submission types only, so a date that
        matches a notification round matched by coincidence, not by
        construction — naming it would misreport what the card is counting down
        to."""
        meta = {
            "deadlines_structured": [_deadline("notification", "2026-09-15T23:59:00Z")]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == ""

    def test_a_stale_snapshot_names_nothing(self):
        """``deadline_date`` is snapshotted into ``signals`` at match time and
        the array is re-mapped nightly; when they no longer line up, "" is the
        honest answer."""
        meta = {
            "deadlines_structured": [_deadline("submission", "2026-10-01T23:59:00Z")]
        }
        score = _score(meta, deadline_date="2026-09-15")
        assert _conference().get_deadline_kind(score) == ""

    def test_a_conference_without_a_date_names_nothing(self):
        meta = {
            "deadlines_structured": [_deadline("submission", "2026-09-15T23:59:00Z")]
        }
        assert _conference().get_deadline_kind(_score(meta, deadline_date="")) == ""
