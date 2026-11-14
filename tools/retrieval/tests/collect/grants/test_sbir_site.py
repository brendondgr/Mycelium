"""SBIR from the public topic pages while its API answers 403 (2026-11).

The HTML below is cut down from www.sbir.gov's real listing and topic pages
(2026-11-14), keeping the markup the parser reads.
"""

from __future__ import annotations

from tools.retrieval.collect.core.http import FetchError, Response
from tools.retrieval.collect.grants.adapters import sbir
from tools.retrieval.collect.grants.adapters.sbir import SBIRAdapter

LISTING = """
<div id="search-results-hits">
  <h3 class="margin-top-2 line-height-sans-5"><a href="/topics/13073">A unified model for
  multi-cloud data analytics &amp; cost</a></h3>
  <p class="margin-bottom-205"><span class="margin-right-1 padding-x-105 bg-green radius-sm text-white">Open</span>
  <b>Release Date:</b> November 4, 2026&nbsp;&nbsp;<span class="border-left-05">&nbsp;&nbsp;<b>Open Date:</b> December 2, 2026</span>
  &nbsp;&nbsp;<span class="border-left-05">&nbsp;&nbsp;<b>Close Date:</b> January 6, 2027</span></p>
  <p class="measure-6">Modern software-centric data systems...</p>
  <h3 class="margin-top-2 line-height-sans-5"><a href="/topics/13081">Remote UAS-based X-Ray</a></h3>
  <p class="margin-bottom-205"><span class="margin-right-1 padding-x-105 bg-green radius-sm text-white">Open</span>
  <b>Release Date:</b> November 4, 2026&nbsp;&nbsp;<span>&nbsp;&nbsp;<b>Open Date:</b> December 2, 2026</span>
  &nbsp;&nbsp;<span>&nbsp;&nbsp;<b>Close Date:</b> January 6, 2027</span></p>
</div>
"""


def topic_page(number: str, branch: str, text: str) -> str:
    return f"""<html><body><h1>Title</h1>
<h4>Funding Agency</h4><p>DOW</p><p>{branch}</p>
<b>Year:</b> 2027 <b>Topic Number:</b> <p>{number}</p>
<b>Solicitation Number:</b> <p>27.BZ</p>
<p>Tagged as:</p><span>SBIR</span><span>BOTH</span>
<b>Solicitation Status:</b> Open
<p>NOTE:</p><p>The Solicitations and topics listed on this site are copies.</p>
<a class="usa-button" href="https://www.dodsbirsttr.mil/topics-app/">View Official Solicitation</a>
<h3>Release Schedule</h3><p>Release Date</p><p>November 4, 2026</p>
<p>Open Date</p><p>December 2, 2026</p><p>Due Date(s)</p><p>January 6, 2027</p>
<p>Close Date</p><p>January 6, 2027</p>
<h3>Description</h3><p>{text}</p><p>Second paragraph.</p>
<footer><a>Site Map</a><a>Privacy Policy</a></footer>
<script>var x = "Description";</script></body></html>""" + " " * 1000


class FakeClient:
    def __init__(self) -> None:
        self.urls: list[tuple[str, bool]] = []

    def get(self, url, *, cache=True, **_):
        self.urls.append((url, cache))
        if "api.www.sbir.gov" in url:
            raise FetchError(url, "HTTP 403", status=403)
        if "/topics?" in url:
            page = LISTING if url.endswith("page=0") else "<div>none</div>"
            return Response(url, 200, page.encode())
        number, branch, text = {
            "13073": ("DAF27BZ02-DV023", "USAF", "Cloud cost models for sustainment."),
            "13081": ("DTR27BZ02-NV002", "DTRA", "X-ray imaging from drones."),
        }[url.rsplit("/", 1)[1]]
        return Response(url, 200, topic_page(number, branch, text).encode())


def test_a_refused_api_falls_back_to_the_public_topic_pages():
    client = FakeClient()
    bundle = SBIRAdapter().fetch(client)
    assert bundle.meta == {"via": "site"}
    # the listing is read fresh, topic pages may come from the cache
    assert ("https://www.sbir.gov/topics?status=Open&page=0", False) in client.urls
    assert ("https://www.sbir.gov/topics/13073", True) in client.urls
    [row] = bundle.records
    assert row["solicitation_number"] == "27.BZ" and row["branch"] == ""
    records = SBIRAdapter().parse(bundle)
    parent, *topics = records
    assert parent.record_kind == "standalone" and parent.status == "open"
    assert (parent.open_date, parent.close_date) == ("2026-12-02", "2027-01-06")
    assert parent.activity_codes == ["Phase I", "Phase II"]
    assert [t.opportunity_number for t in topics] == ["DAF27BZ02-DV023", "DTR27BZ02-NV002"]
    first = topics[0]
    assert first.title == "A unified model for multi-cloud data analytics & cost"
    assert first.description.startswith("Cloud cost models for sustainment.")
    assert "Site Map" not in first.description
    assert first.funder_subunit == "USAF" and topics[1].funder_subunit == "DTRA"
    assert first.source_url == "https://www.sbir.gov/topics/13073"


def test_other_api_failures_still_raise():
    class Down(FakeClient):
        def get(self, url, **kw):
            raise FetchError(url, "HTTP 500", status=500)

    try:
        SBIRAdapter().fetch(Down())
    except FetchError as exc:
        assert exc.status == 500
    else:
        raise AssertionError("expected the 500 to surface")


def test_the_listing_parser_reads_status_and_dates():
    hits = sbir.parse_listing(LISTING)
    assert [h["id"] for h in hits] == ["13073", "13081"]
    assert hits[0]["status"] == "Open" and hits[0]["close_date"] == "January 6, 2027"
