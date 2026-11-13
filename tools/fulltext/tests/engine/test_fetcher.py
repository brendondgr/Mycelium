"""The fetcher's protections: deadlines, quota stops, strike-outs, shared state."""

import http.server
import threading
import time

import pytest
import requests

from tools.fulltext.engine import fetcher as fetcher_mod
from tools.fulltext.engine import sources as S
from tools.fulltext.engine.cache import DiskCache
from tools.fulltext.engine.fetcher import Fetcher
from tools.fulltext.engine.state import MemoryState


class Trickle(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "100000")
        self.end_headers()
        try:
            for _ in range(200):
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.1)
        except OSError:
            pass

    def log_message(self, *a):
        pass


@pytest.fixture
def trickle_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_trickling_download_is_cut_off(tmp_path, monkeypatch, trickle_server):
    monkeypatch.setattr(S, "BODY_DEADLINE", 1)
    f = Fetcher({}, tmp_path, guard=False)  # the test server is on 127.0.0.1
    t = time.time()
    url = f"http://127.0.0.1:{trickle_server.server_port}/a.pdf"
    md, _, note = f.download("crossref", url, set())
    assert md == "" and note == "error BodyTimeout"
    assert time.time() - t < 5


# -- outbound guard (SSRF) ------------------------------------------------- #

PUBLIC = {"repo.example": "93.184.216.34", "inside.example": "10.0.0.5"}


def _fake_dns(host, port, *a, **kw):
    import socket

    ip = PUBLIC.get(host, host)
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.fixture
def redirecting(monkeypatch):
    """Every request the transport would send is recorded; the first answers
    with a redirect to ``target["to"]``. Nothing touches the network."""
    from requests.adapters import HTTPAdapter

    monkeypatch.setattr(fetcher_mod.socket, "getaddrinfo", _fake_dns)
    sent: list[str] = []
    target = {"to": ""}

    def send(self, request, *a, **kw):
        sent.append(request.url)
        r = requests.Response()
        r.status_code = 302
        r.headers["Location"] = target["to"]
        r._content = b""
        r._content_consumed = True
        r.url = request.url
        r.request = request
        return r

    monkeypatch.setattr(HTTPAdapter, "send", send)
    return sent, target


@pytest.mark.parametrize(
    "to",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://inside.example/x.pdf",
        "https://repo.example:8443/x.pdf",
        "file:///etc/passwd",
    ],
)
def test_a_redirect_to_a_private_address_is_refused(tmp_path, redirecting, to):
    sent, target = redirecting
    target["to"] = to
    f = Fetcher({}, tmp_path)
    with pytest.raises(requests.RequestException) as err:
        f.get("openalex", "https://repo.example/paper.pdf", attempts=1)
    refused = (fetcher_mod.BlockedURL, requests.exceptions.InvalidSchema)
    assert isinstance(err.value, refused)
    # the public first hop went out; the redirect target never did
    assert sent == ["https://repo.example/paper.pdf"]


def test_a_private_first_url_is_never_sent(tmp_path, redirecting):
    sent, _ = redirecting
    f = Fetcher({}, tmp_path)
    md, _, note = f.download("unpaywall", "http://169.254.169.254/x.pdf", set())
    assert (md, note) == ("", "blocked")
    assert sent == []
    # remembered: asked again, it is not even attempted
    again = f.download("unpaywall", "http://169.254.169.254/x.pdf", set())
    assert again[2] == "blocked"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://192.168.0.1/",
        "http://169.254.169.254/",
        "http://100.64.0.1/",
        "http://224.0.0.1/",
        "http://0.0.0.0/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://repo.example:22/",
        "gopher://repo.example/",
        "http:///nohost",
    ],
)
def test_check_url_refuses(url, monkeypatch):
    monkeypatch.setattr(fetcher_mod.socket, "getaddrinfo", _fake_dns)
    with pytest.raises(fetcher_mod.BlockedURL):
        fetcher_mod.check_url(url)


def test_check_url_allows_a_public_host(monkeypatch):
    monkeypatch.setattr(fetcher_mod.socket, "getaddrinfo", _fake_dns)
    fetcher_mod.check_url("https://repo.example/a.pdf")
    fetcher_mod.check_url("http://repo.example:80/a.pdf")


def _response(status, body=b"", content_type="application/json"):
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers["content-type"] = content_type
    r.url = "https://api.wiley.com/x"
    return r


def test_quota_hidden_in_a_500_switches_the_source_off(tmp_path):
    f = Fetcher({"WILEY_TDM_TOKEN": "t"}, tmp_path)
    body = (
        b'{"fault":{"faultstring":"Rate limit quota violation. Quota limit exceeded."}}'
    )
    assert f._quota_exhausted("wiley", _response(500, body)) is True
    assert "quota" in f.disabled["wiley"]
    # An ordinary 500, or a PDF body, is not a quota stop.
    g = Fetcher({"WILEY_TDM_TOKEN": "t"}, tmp_path)
    assert g._quota_exhausted("wiley", _response(500, b"internal error")) is False
    assert (
        g._quota_exhausted("wiley", _response(500, b"%PDF quota", "application/pdf"))
        is False
    )


def test_switch_off_is_shared_through_the_state_and_expires(tmp_path):
    state = MemoryState()
    a = Fetcher({}, tmp_path, state=state, disable_ttl=0.2)
    b = Fetcher({}, tmp_path, state=state, disable_ttl=0.2)
    a._disable("core", "provider quota exhausted (HTTP 500)")
    assert "core" in b.disabled  # another worker sees it at once
    time.sleep(0.25)
    assert "core" not in b.disabled  # and it comes back after the TTL


def test_missing_credentials_never_expire(tmp_path):
    f = Fetcher({}, tmp_path, disable_ttl=0)
    assert f.disabled["elsevier"] == "missing ELSEVIER_API_KEY"
    assert "elsevier" not in f.order


def test_consecutive_refusals_switch_a_source_off(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "ENTITLEMENT_STRIKES", 3)
    f = Fetcher({"WILEY_TDM_TOKEN": "t"}, tmp_path)
    monkeypatch.setattr(f, "src_wiley", lambda *a: ("", None, "http 403"))
    for i in range(3):
        f.fetch(None, f"10.1002/x{i}", None, order=["wiley"])
    assert "consecutive refusals" in f.disabled["wiley"]
    _, _, _, tried, _ = f.fetch(None, "10.1002/y", None, order=["wiley"])
    assert tried == {"wiley": "disabled"}


def test_a_success_resets_the_strike_count(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "ENTITLEMENT_STRIKES", 2)
    f = Fetcher({"WILEY_TDM_TOKEN": "t"}, tmp_path)
    answers = iter([("", None, "http 403"), ("body", {}, "ok"), ("", None, "http 403")])
    monkeypatch.setattr(f, "src_wiley", lambda *a: next(answers))
    for i in range(3):
        f.fetch(None, f"10.1002/x{i}", None, order=["wiley"])
    assert "wiley" not in f.disabled


def test_definitive_answers_are_remembered_and_transient_ones_are_not(
    tmp_path, monkeypatch
):
    f = Fetcher({}, tmp_path)
    calls = []
    answers = {"core": ("", None, "not-found"), "openalex": ("", None, "error Timeout")}

    def make(src):
        return lambda *a: calls.append(src) or answers[src]

    monkeypatch.setattr(f, "src_core", make("core"))
    monkeypatch.setattr(f, "src_openalex", make("openalex"))
    f.fetch(None, "10.1/a", None, order=["core", "openalex"])
    _, _, _, tried, _ = f.fetch(None, "10.1/a", None, order=["core", "openalex"])
    assert calls == ["core", "openalex", "openalex"]
    assert tried["core"] == "not-found (cached)"
    # retry=True asks again.
    g = Fetcher({}, tmp_path, state=f.state, retry=True)
    monkeypatch.setattr(g, "src_core", make("core"))
    monkeypatch.setattr(g, "src_openalex", make("openalex"))
    g.fetch(None, "10.1/a", None, order=["core"])
    assert calls[-1] == "core"


def test_download_caches_the_payload_and_records_the_original(tmp_path, monkeypatch):
    f = Fetcher({}, tmp_path)
    jats = (
        b"<article><body><sec><title>Results</title><p>"
        + b"Plastics were found in every sample. " * 40
        + b"</p></sec></body></article>"
    )
    hits = []

    def fake_get(source, url, **kw):
        hits.append(url)
        r = _response(200, jats, "application/xml")
        r.url = url
        return r

    monkeypatch.setattr(f, "get", fake_get)
    md, kind, note = f.download("unpaywall", "https://repo.example.org/a.xml", set())
    assert note == "ok" and kind == "jats" and "Plastics were found" in md
    assert f._origin.kind == "xml" and f._origin.path.endswith(".bin")
    md2, _, _ = f.download("unpaywall", "https://repo.example.org/a.xml", set())
    assert md2 == md and len(hits) == 1  # the second time came from the cache


def test_a_url_already_tried_by_an_earlier_source_is_skipped(tmp_path):
    f = Fetcher({}, tmp_path)
    assert f.download("openalex", "https://x/a.pdf", {"https://x/a.pdf"}) == (
        "",
        "",
        "dup",
    )


def test_disk_cache_keeps_none_as_an_answer(tmp_path):
    c = DiskCache(tmp_path)
    assert not c.has_json("doi_pmid", "10.1/x")
    c.put_json("doi_pmid", "10.1/x", None)
    assert c.has_json("doi_pmid", "10.1/x") and c.get_json("doi_pmid", "10.1/x") is None
    long_key = "10.1/" + "y" * 400
    c.put_json("crossref", long_key, {"a": 1})
    assert c.get_json("crossref", long_key) == {"a": 1}


def test_is_licensed():
    assert fetcher_mod.is_licensed("wiley", {})
    assert fetcher_mod.is_licensed("springer", {"endpoint": "meta"})
    assert not fetcher_mod.is_licensed("springer", {"endpoint": "openaccess"})
    assert not fetcher_mod.is_licensed("arxiv", {})
