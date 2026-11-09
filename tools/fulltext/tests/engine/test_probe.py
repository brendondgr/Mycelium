"""Telling a rejected key from a valid key this network is not entitled to use."""

import requests

from tools.fulltext.engine import probe as P
from tools.fulltext.engine.fetcher import Fetcher


def resp(status, body=b"", ct="text/xml"):
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers["content-type"] = ct
    return r


def fetcher(tmp_path, answers, **env):
    """A Fetcher whose get() answers from ``answers``: (source, url-part) -> resp."""
    f = Fetcher({"CONTACT_EMAIL": "lab@fsu.edu", **env}, tmp_path)

    def get(source, url, **kw):
        for (src, part), r in answers.items():
            if src == source and part in url:
                return r
        raise AssertionError(f"unexpected request {source} {url}")

    f.get = get
    return f


def by_source(probes):
    return {p.source: p for p in probes}


def test_elsevier_search_ok_but_article_refused_is_not_entitled(tmp_path):
    f = fetcher(
        tmp_path,
        {
            ("elsevier", "search"): resp(200, b"{}"),
            ("elsevier", "article"): resp(403, b"<error/>"),
        },
        ELSEVIER_API_KEY="k",
    )
    p = P.probe_elsevier(f)
    assert p.state == P.NOT_ENTITLED and "library" in p.detail


def test_elsevier_401_everywhere_is_a_rejected_key(tmp_path):
    f = fetcher(
        tmp_path,
        {("elsevier", "search"): resp(401), ("elsevier", "article"): resp(401)},
        ELSEVIER_API_KEY="k",
    )
    assert P.probe_elsevier(f).state == P.REJECTED


def test_elsevier_body_means_on(tmp_path):
    f = fetcher(
        tmp_path,
        {
            ("elsevier", "search"): resp(200, b"{}"),
            ("elsevier", "article"): resp(200, b"<x><originalText/></x>"),
        },
        ELSEVIER_API_KEY="k",
    )
    assert P.probe_elsevier(f).ok


def test_wiley_states(tmp_path):
    for status, body, state in [
        (200, b"%PDF-1.7 ...", P.ON),
        (401, b"", P.REJECTED),
        (403, b"", P.TOKEN_OR_NETWORK),
    ]:
        f = fetcher(
            tmp_path,
            {("wiley", "tdm"): resp(status, body, "application/pdf")},
            WILEY_TDM_TOKEN="t",
        )
        assert P.probe_wiley(f).state == state, status


def test_springer_open_access_only_key_is_on_and_says_so(tmp_path):
    f = fetcher(
        tmp_path,
        {
            ("springer", "openaccess"): resp(200, b"<records/>"),
            ("springer", "meta"): resp(401),
        },
        SPRINGER_API_KEY="k",
    )
    p = P.probe_springer(f)
    assert p.ok and "subscription" in p.detail


def test_probe_all_reports_off_sources_without_asking_and_free_ones_on(tmp_path):
    f = fetcher(
        tmp_path, {("unpaywall", "unpaywall"): resp(200, b"{}", "application/json")}
    )
    probes = by_source(P.probe_all(f))
    assert (
        probes["elsevier"].state == P.OFF
        and "ELSEVIER_API_KEY" in probes["elsevier"].detail
    )
    assert probes["pmc"].ok and probes["arxiv"].ok and probes["unpaywall"].ok
    assert probes["core"].ok and "anonymous" in probes["core"].detail


def test_unpaywall_rejecting_the_address_is_reported(tmp_path):
    f = fetcher(tmp_path, {("unpaywall", "unpaywall"): resp(422)})
    assert P.probe_unpaywall(f).state == P.REJECTED


def test_a_network_error_is_unreachable_not_a_crash(tmp_path):
    f = Fetcher({"CONTACT_EMAIL": "lab@fsu.edu", "WILEY_TDM_TOKEN": "t"}, tmp_path)

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    f.get = boom
    assert by_source(P.probe_all(f, ["wiley"]))["wiley"].state == P.UNREACHABLE
