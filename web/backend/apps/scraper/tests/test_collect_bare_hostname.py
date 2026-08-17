"""A bare hostname is an address, not a missing one.

OpenReview's website field is free text, and organizers routinely type a host
with no scheme: ``jmlr.org/tmlr``, ``slads.scichina.com``. The fetchability
check required ``http://`` or ``https://``, so 17 conferences were recorded as
having "no fetchable URL" while holding a perfectly working address for each --
never fetched, therefore never described, and reported as though the listing
were at fault.

The link a reader clicks was never affected: ``mapping._normalize_url`` has
always supplied the scheme for display. That is what made this invisible -- the
card showed a working website while the crawler considered the same record
unreachable.

The refusals still have to hold: ``TBD``, ``internal (private)`` and an email
address are not addresses, and prepending a scheme to any of them would turn a
note-to-self into a request.
"""

from __future__ import annotations

import pytest

from apps.scraper.collect.conferences.enrich import EnrichmentTask


def _task(url: str) -> EnrichmentTask:
    return EnrichmentTask(
        instance_key="k", url=url, acronym="X", title="T", year_label="2026",
        gaps=("description",),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The cases that were being dropped.
        ("jmlr.org/tmlr", "https://jmlr.org/tmlr"),
        ("slads.scichina.com", "https://slads.scichina.com"),
        ("www.novasworkshop.org", "https://www.novasworkshop.org"),
        # Already addressed: left exactly as-is, including the scheme.
        ("https://neurips.cc", "https://neurips.cc"),
        ("http://example.org/cfp", "http://example.org/cfp"),
    ],
)
def test_an_address_survives_with_its_scheme(raw, expected):
    task = _task(raw)
    assert task.is_fetchable is True
    assert task.fetch_url == expected


@pytest.mark.parametrize(
    "raw",
    [
        "TBD",                          # a promise of a URL
        "internal (private)",           # spaces, and not an address
        "horvathfest2026@gmail.com",    # an email address
        "",                             # nothing at all
        "   ",
        "glee-competition.com; https://x.org",  # two URLs in one field
        "localhost",                    # no dotted label
    ],
)
def test_a_non_address_is_still_refused(raw):
    """Each of these is real data from the live corpus."""
    task = _task(raw)
    assert task.is_fetchable is False
    assert task.fetch_url == ""


def test_the_crawler_and_the_card_now_agree():
    """The two normalizers had drifted; a card's link worked, the crawl did not.

    Pinned against ``mapping._normalize_url`` directly so that changing one
    without the other fails here rather than silently costing another set of
    descriptions.
    """
    from apps.scraper.collect.mapping import _normalize_url

    for raw in ("jmlr.org/tmlr", "slads.scichina.com", "https://neurips.cc"):
        assert _task(raw).fetch_url == _normalize_url(raw)


class TestFollowedLinkSafety:
    """A hand-written href must not be able to kill a batch.

    `fetch_page` optionally follows one "call for papers" link off the page it
    just read. Venue sites write those hrefs by hand, so a real one is
    `/tiki-index.php?page=Call for Sponsors` — spaces included. Handing that to
    `http.client` raises `InvalidURL`, which is not a `FetchError` and so
    escaped the handler, ending an extraction run that had already settled 57
    records and had 92 to go.

    Two things were wrong and both are pinned here: the link was never encoded,
    and the failure was not isolated to the one optional page it belongs to.
    """

    def test_a_space_in_an_href_is_encoded_not_fatal(self):
        from apps.scraper.collect.conferences.enrich import cfp_links

        html = (
            '<a href="/tiki-index.php?page=Call for Sponsors">Call for Papers</a>'
        )
        links = cfp_links(html, "https://example.org/")

        assert links == ["https://example.org/tiki-index.php?page=Call%20for%20Sponsors"]

    def test_an_already_encoded_link_is_left_alone(self):
        """Double-encoding would break a link that was written correctly."""
        from apps.scraper.collect.conferences.enrich import cfp_links

        html = '<a href="/cfp?p=a%20b">Important Dates</a>'
        assert cfp_links(html, "https://example.org/") == [
            "https://example.org/cfp?p=a%20b"
        ]

    def test_a_control_character_is_stripped_rather_than_raised(self):
        from apps.scraper.collect.conferences.enrich import _encode_url

        assert _encode_url("https://example.org/a\x00b") == "https://example.org/ab"

    def test_a_relative_link_joins_onto_the_normalized_base(self):
        """The base must be the address we actually fetched.

        Joining onto a scheme-less `task.url` yields a nonsense target, so the
        subpage silently never loaded for exactly the bare-hostname records
        this file exists to rescue.
        """
        from apps.scraper.collect.conferences.enrich import cfp_links

        html = '<a href="dates.html">Important Dates</a>'
        assert cfp_links(html, "https://slads.scichina.com/") == [
            "https://slads.scichina.com/dates.html"
        ]
