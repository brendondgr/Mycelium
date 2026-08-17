"""The venue line survives a corpus that is half-migrated.

Pivot wrote a conference's place into ``metadata["location"]``; the open
collector writes ``metadata["place_text"]``. For the length of the migration
both shapes are in the table at once, so every reader of that field has to
chain rather than choose.

This file exists because the swap that broke it passed a full green suite:
``_source_line``'s conference branch had exactly one caller and no test at all,
so replacing the key silently reduced 2,958 of 2,962 conferences to
country-only in every report and PDF. A field with one caller and no test is
not covered by "the suite is green".

Delete these tests once no ``location`` row survives — and delete the fallbacks
in the same change, not before.
"""

from __future__ import annotations

import pytest

from apps.content.daily_report import _source_line

pytestmark = pytest.mark.django_db


class TestConferenceVenueLine:
    def test_reads_the_collector_key(self):
        assert (
            _source_line("conference", {"place_text": "Vienna", "country": "Austria"})
            == "Vienna, Austria"
        )

    def test_falls_back_to_the_pivot_key(self):
        """The case the swap broke: every conference already in the database."""
        assert (
            _source_line("conference", {"location": "Vienna", "country": "Austria"})
            == "Vienna, Austria"
        )

    def test_collector_key_wins_when_both_are_present(self):
        assert (
            _source_line(
                "conference",
                {"place_text": "Vienna", "location": "Wien", "country": "Austria"},
            )
            == "Vienna, Austria"
        )

    def test_country_alone_still_renders(self):
        assert _source_line("conference", {"country": "Austria"}) == "Austria"

    def test_no_place_at_all_is_empty_not_a_stray_comma(self):
        assert _source_line("conference", {}) == ""


class TestGrantSourceLine:
    """Unchanged by the migration, pinned so a later edit cannot drift it."""

    def test_prefers_sponsor(self):
        meta = {"sponsor": "NSF", "funder": "National Science Foundation"}
        assert _source_line("grant", meta) == "NSF"

    def test_falls_back_to_funder(self):
        assert _source_line("grant", {"funder": "NSF"}) == "NSF"


def test_serializer_location_chains_the_same_way():
    """The serializer twin of the same fallback.

    ``get_location`` feeds the app's conference cards, the saves rail and the
    project tabs. It was left on the dead key while the report was moved to the
    new one — the same field broken in opposite directions by two changes that
    each looked correct alone.
    """
    from apps.content.serializers import ConferenceSerializer

    get = ConferenceSerializer.get_location

    class _Score:
        pass

    def meta_of(payload):
        return lambda self, score: payload

    for payload, expected in (
        ({"place_text": "Vienna", "country": "Austria"}, "Vienna, Austria"),
        ({"location": "Vienna", "country": "Austria"}, "Vienna, Austria"),
        ({"place_text": "Vienna", "location": "Wien"}, "Vienna"),
        ({}, ""),
    ):
        serializer = ConferenceSerializer.__new__(ConferenceSerializer)
        serializer._meta = meta_of(payload).__get__(serializer)
        assert get(serializer, _Score()) == expected, payload


class TestConferenceDescription:
    """The conference card's blurb must be the verified extraction.

    ``ConferenceSerializer`` overrode the base ``get_description`` to read
    Pivot's ``scope`` key. The open collector writes no ``scope``, so the
    override returned "" for all 912 conferences in the rebuilt corpus while
    776 of them held a verified ``ai_summary``. Nothing failed: the field was
    simply, silently empty everywhere -- the same shape as the
    ``location``/``place_text`` regression above, and equally invisible to a
    green test suite because the override had no test of its own.
    """

    @staticmethod
    def _describe(payload):
        from apps.content.serializers import ConferenceSerializer

        serializer = ConferenceSerializer.__new__(ConferenceSerializer)
        serializer._meta = (lambda self, score: payload).__get__(serializer)
        return ConferenceSerializer.get_description(serializer, object())

    def test_prefers_the_verified_extraction(self):
        assert self._describe({"ai_summary": "A workshop on graphs."}) == (
            "A workshop on graphs."
        )

    def test_extraction_wins_over_the_pivot_key(self):
        """Both present: the verified text is the one the record was embedded
        on, so showing anything else would describe a row by text that is not
        what matched it."""
        payload = {"ai_summary": "Verified blurb.", "scope": "Pivot blurb."}
        assert self._describe(payload) == "Verified blurb."

    def test_falls_back_to_the_collector_key(self):
        assert self._describe({"description": "Collector blurb."}) == (
            "Collector blurb."
        )

    def test_still_reads_pivot_scope_for_rows_that_predate_the_migration(self):
        assert self._describe({"scope": "Cultural Connections"}) == (
            "Cultural Connections"
        )

    def test_whitespace_is_collapsed(self):
        assert self._describe({"ai_summary": "a\n\n  b   c"}) == "a b c"

    def test_nothing_at_all_is_empty_not_none(self):
        assert self._describe({}) == ""
