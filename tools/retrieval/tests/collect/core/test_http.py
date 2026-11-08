"""The four client behaviours that reconnaissance forced.

Each test here corresponds to a specific host that broke a naive client during
the source probes, and is named for it. None of these is hypothetical.
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from tools.retrieval.collect.core.http import (
    HOST_MIN_INTERVAL,
    FetchError,
    PoliteClient,
    _resolve_contact,
)


class _Recorder:
    """Collects the sleeps a client asks for, without taking any of them."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def _http_error(url: str, code: int, headers: dict[str, str] | None = None):
    return urllib.error.HTTPError(url, code, f"HTTP {code}", headers or {}, io.BytesIO(b""))


# --- COLLECT_CONTACT: blank must fall back, not through -------------------
#
# `.env.example` is an `env_file` for the backend and worker containers, so a
# bare `COLLECT_CONTACT=` line there arrives as an empty string rather than
# an absent variable. Plain `os.environ.get(name, default)` takes that empty
# string *over* the default, which would ship every outbound request with
# `mycelium-collector/0.1 (+)` — no contact at all, defeating the header's
# entire purpose. `_resolve_contact` is pulled out of the module-level
# assignment specifically so this can be pinned directly, without needing to
# reload the module (which would rebind classes other test files already
# imported by name).


def test_a_blank_collect_contact_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("COLLECT_CONTACT", "")
    assert _resolve_contact() == "research-collector@example.org"


def test_a_whitespace_only_collect_contact_also_falls_back(monkeypatch):
    monkeypatch.setenv("COLLECT_CONTACT", "   ")
    assert _resolve_contact() == "research-collector@example.org"


def test_an_unset_collect_contact_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("COLLECT_CONTACT", raising=False)
    assert _resolve_contact() == "research-collector@example.org"


def test_a_real_collect_contact_value_passes_through_unchanged(monkeypatch):
    monkeypatch.setenv("COLLECT_CONTACT", "ops@mycelium.example")
    assert _resolve_contact() == "ops@mycelium.example"


# --- per-host pacing -----------------------------------------------------


def test_wikicfp_gets_its_mandated_five_seconds_even_when_the_caller_asks_for_less():
    """The site asks for one query per five seconds in robots.txt and in prose.

    A caller passing --min-interval 0.5 must not be able to speed that up.
    """
    client = PoliteClient(min_interval=0.5)
    assert client.interval_for("http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=1") == 5.0


def test_a_slower_global_interval_still_wins_over_a_faster_per_host_one():
    """Per-host overrides raise the floor; they never lower it."""
    client = PoliteClient(min_interval=8.0)
    assert client.interval_for("https://api2.openreview.net/groups?id=venues") == 8.0


def test_hosts_without_an_override_get_the_global_default():
    client = PoliteClient(min_interval=0.5)
    assert client.interval_for("https://example.org/whatever") == 0.5


def test_the_measured_host_floors_are_the_ones_recon_recorded():
    assert HOST_MIN_INTERVAL["www.wikicfp.com"] == 5.0  # robots.txt Crawl-delay: 5
    assert HOST_MIN_INTERVAL["dblp.org"] == 4.0  # robots.txt Crawl-delay: 4
    assert HOST_MIN_INTERVAL["api2.openreview.net"] == 3.2  # 20 distinct req/60s
    assert HOST_MIN_INTERVAL["spie.org"] == 10.0  # robots.txt Crawl-delay: 10


# --- Retry-After ---------------------------------------------------------


def test_openreview_retry_after_is_honoured_instead_of_the_exponential_ladder(monkeypatch):
    """OpenReview answers 429 with retry-after: 54.

    The default 1-2-4-8 ladder totals ~15s and would exhaust its retries while
    still inside the throttle window, then report the source as dead.
    """
    sleeper = _Recorder()
    client = PoliteClient(min_interval=0, retries=2, sleep=sleeper)

    def always_429(*_args, **_kwargs):
        raise _http_error("https://api2.openreview.net/invitations", 429, {"Retry-After": "54"})

    monkeypatch.setattr("urllib.request.urlopen", always_429)

    with pytest.raises(FetchError):
        client.get("https://api2.openreview.net/invitations", cache=False)

    assert 54.0 in sleeper.slept, f"expected to wait the server's 54s, slept {sleeper.slept}"


def test_a_missing_retry_after_falls_back_to_exponential_backoff(monkeypatch):
    sleeper = _Recorder()
    client = PoliteClient(min_interval=0, retries=3, sleep=sleeper)

    def always_503(*_args, **_kwargs):
        raise _http_error("https://example.org/x", 503)

    monkeypatch.setattr("urllib.request.urlopen", always_503)

    with pytest.raises(FetchError):
        client.get("https://example.org/x", cache=False)

    assert sleeper.slept == [1.0, 2.0]


# --- dblp's escalating ban ----------------------------------------------


def test_dblp_stops_immediately_on_429_rather_than_retrying(monkeypatch):
    """dblp.org refuses TCP for minutes after a 429, and probing extends it.

    Retrying is not merely useless here, it prolongs the ban. One request, then
    stop.
    """
    sleeper = _Recorder()
    client = PoliteClient(min_interval=0, retries=4, sleep=sleeper)
    calls = {"n": 0}

    def throttled(*_args, **_kwargs):
        calls["n"] += 1
        raise _http_error("https://dblp.org/search/venue/api?q=SAC", 429)

    monkeypatch.setattr("urllib.request.urlopen", throttled)

    with pytest.raises(FetchError, match="bans on retry"):
        client.get("https://dblp.org/search/venue/api?q=SAC", cache=False)

    assert calls["n"] == 1, "dblp must be asked exactly once before giving up"


def test_a_connection_reset_after_a_throttle_is_a_hard_stop(monkeypatch):
    """The reset is the ban, not a blip. Retrying through it is what kept the
    ban alive during reconnaissance."""
    client = PoliteClient(min_interval=0, retries=4, sleep=_Recorder())
    client._throttled_hosts.add("example.org")

    def reset(*_args, **_kwargs):
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr("urllib.request.urlopen", reset)

    with pytest.raises(FetchError, match="connection reset after throttling"):
        client.get("https://example.org/x", cache=False)


def test_a_connection_reset_without_a_prior_throttle_still_retries(monkeypatch):
    """An ordinary transient reset must not be mistaken for a ban."""
    sleeper = _Recorder()
    client = PoliteClient(min_interval=0, retries=3, sleep=sleeper)

    def reset(*_args, **_kwargs):
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr("urllib.request.urlopen", reset)

    with pytest.raises(FetchError, match="gave up after 3 attempts"):
        client.get("https://example.org/x", cache=False)
    assert sleeper.slept == [1.0, 2.0]


# --- content assertions --------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_ieee_zero_byte_202_raises_instead_of_being_cached(monkeypatch, tmp_path):
    """www.ieee.org answers 202 with an empty body.

    202 is not in RETRY_STATUS, so without a content check this is cached as a
    success and the adapter reports a healthy fetch of nothing, forever.
    """
    client = PoliteClient(cache_dir=tmp_path, min_interval=0, sleep=_Recorder())
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(b"", status=202)
    )

    with pytest.raises(FetchError, match="body too short"):
        client.get("https://www.ieee.org/conferences", min_bytes=500)

    assert list(tmp_path.glob("*.cache")) == [], "a rejected body must not be cached"


def test_spie_incapsula_interstitial_at_200_fails_the_content_predicate(monkeypatch):
    """SPIE serves a bot-wall iframe with HTTP 200."""
    wall = b'<html><body><iframe src="/_Incapsula_Resource?SWUDNSAI=31"></iframe></body></html>'
    client = PoliteClient(min_interval=0, sleep=_Recorder())
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(wall))

    with pytest.raises(FetchError, match="content check"):
        client.get(
            "https://spie.org/conferences-and-exhibitions",
            cache=False,
            expect=lambda body: b"_Incapsula_Resource" not in body,
        )


def test_a_good_body_passes_both_checks(monkeypatch):
    page = b"<html><body>" + b"x" * 2000 + b"</body></html>"
    client = PoliteClient(min_interval=0, sleep=_Recorder())
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(page))

    response = client.get(
        "https://example.org/real",
        cache=False,
        min_bytes=500,
        expect=lambda body: b"<body>" in body,
    )
    assert response.status == 200


def test_a_poisoned_cache_entry_is_rejected_on_read(monkeypatch, tmp_path):
    """One bad fetch must not silently satisfy every later run from disk."""
    client = PoliteClient(cache_dir=tmp_path, min_interval=0, sleep=_Recorder())
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_a, **_k: _FakeResponse(b"x" * 1000)
    )
    client.get("https://example.org/p", min_bytes=100)
    assert len(list(tmp_path.glob("*.cache"))) == 1

    # Same URL, but now the caller demands more than the cached body carries.
    with pytest.raises(FetchError, match="body too short"):
        client.get("https://example.org/p", min_bytes=5000)


# --- unchanged behaviour -------------------------------------------------


def test_403_and_404_are_still_answers_not_hiccups(monkeypatch):
    client = PoliteClient(min_interval=0, retries=4, sleep=_Recorder())
    calls = {"n": 0}

    def forbidden(*_args, **_kwargs):
        calls["n"] += 1
        raise _http_error("https://example.org/x", 403)

    monkeypatch.setattr("urllib.request.urlopen", forbidden)

    with pytest.raises(FetchError) as caught:
        client.get("https://example.org/x", cache=False)
    assert caught.value.status == 403
    assert calls["n"] == 1


def test_400_is_an_answer_too(monkeypatch):
    """OpenReview returns 400 for an expired invitation fetched without
    expired=true. It must surface as an error the adapter can see, not a retry
    storm."""
    client = PoliteClient(min_interval=0, retries=4, sleep=_Recorder())
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(_http_error("https://api2.openreview.net/i", 400)),
    )
    with pytest.raises(FetchError) as caught:
        client.get("https://api2.openreview.net/i", cache=False)
    assert caught.value.status == 400


def test_offline_mode_raises_on_a_cache_miss(tmp_path):
    client = PoliteClient(cache_dir=tmp_path, offline=True, min_interval=0)
    with pytest.raises(FetchError, match="offline mode"):
        client.get("https://example.org/never-fetched")
