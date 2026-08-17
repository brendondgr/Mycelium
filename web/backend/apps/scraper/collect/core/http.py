"""A deliberately slow, well-behaved HTTP client.

Every source these collectors touch is a public good — a government agency, a
volunteer-run wiki, a grant-funded library project — so the defaults here favour
politeness over throughput: an identifying user agent with contact information, a
minimum gap between requests to the same host, exponential backoff on throttling,
and an on-disk cache so a re-run costs the source nothing.

Four of the behaviours below look like over-engineering until you meet the host
that forced them. Each one is annotated with the source that did.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: The fallback used whenever ``COLLECT_CONTACT`` is absent, or present but
#: blank. Fine for tests and offline replay; a real, monitored address must be
#: set before the first live run against a public source, since it is the
#: only way a host operator can reach us about our traffic.
_FALLBACK_CONTACT = "research-collector@example.org"


def _resolve_contact() -> str:
    """Read ``COLLECT_CONTACT``, treating a blank value the same as unset.

    ``.env.example`` is loaded as an ``env_file`` for the backend and worker
    containers, so a bare ``COLLECT_CONTACT=`` line there arrives as an empty
    string, not an absent variable — and plain ``os.environ.get(name,
    default)`` takes that empty string *over* the default. The blank would
    then flow straight into ``USER_AGENT`` below as
    ``mycelium-collector/0.1 (+)``, silently dropping the one thing the
    header exists to carry. Treat blank the same as unset, the way
    ``config.settings.env_str`` does for the analytics data paths (see
    ``docs/architecture.md``) — ``.strip() or fallback`` falls through to the
    real default instead of past it.

    Pulled out as its own function (rather than inlined into the module-level
    assignment below) purely so a test can exercise the blank-vs-unset
    behaviour directly, without reloading the module.
    """
    return os.environ.get("COLLECT_CONTACT", "").strip() or _FALLBACK_CONTACT


#: Read at IMPORT TIME, so setting ``COLLECT_CONTACT`` after this module has
#: loaded has no effect — it must be in the process environment before Django
#: (or anything else) first imports ``apps.scraper.collect``.
DEFAULT_CONTACT = _resolve_contact()
USER_AGENT = f"mycelium-collector/0.1 (+{DEFAULT_CONTACT})"

#: Minimum seconds between requests to the same host.
DEFAULT_MIN_INTERVAL = 0.5
DEFAULT_TIMEOUT = 45.0
DEFAULT_RETRIES = 4
#: Responses that mean "slow down" or "try again", as opposed to "you are wrong".
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

#: Per-host minimum intervals, in seconds. Each is a stated policy or a measured
#: throttle, never a guess:
#:
#: * ``wikicfp.com`` — ``Crawl-delay: 5`` in robots.txt, restated in prose on the
#:   site's own data page: "please issue at most one query every five seconds".
#: * ``dblp.org`` — ``Crawl-delay: 4`` in robots.txt. The host 429s on the fourth
#:   request inside 1.4s and then refuses TCP connections for minutes.
#: * ``api2.openreview.net`` — headers advertise 180/min, but *distinct* queries
#:   (which is all a crawler makes) are limited to 20 per 60s.
#: * ``spie.org`` — ``Crawl-delay: 10`` in robots.txt.
HOST_MIN_INTERVAL: dict[str, float] = {
    "www.wikicfp.com": 5.0,
    "wikicfp.com": 5.0,
    "dblp.org": 4.0,
    "api2.openreview.net": 3.2,
    "api.openreview.net": 3.2,
    "spie.org": 10.0,
    "www.spie.org": 10.0,
}

#: Hosts where a 429 means "stop for minutes", not "retry shortly". dblp closes
#: the connection and then answers nothing at the TCP layer; continued probing
#: measurably extends the ban, so retrying is actively counterproductive.
NO_RETRY_AFTER_THROTTLE = frozenset({"dblp.org", "www.dblp.org"})

#: Upper bound on a server-supplied Retry-After we are willing to sleep through.
MAX_RETRY_AFTER = 120.0


class FetchError(RuntimeError):
    """A source could not be reached. Never fatal to a multi-source run."""

    def __init__(self, url: str, reason: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason
        self.status = status


@dataclass
class Response:
    url: str
    status: int
    body: bytes

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding, errors="replace")

    def json(self) -> object:
        return json.loads(self.body.decode("utf-8", errors="replace"))


class RobotsGate:
    """Per-host ``robots.txt``, fetched once and cached for the session.

    The eight per-host intervals above were read by hand, which works when the
    source list is eight curated APIs and stops working the moment the crawler
    starts visiting a thousand conference websites nobody vetted. This asks each
    host directly instead.

    Failure handling follows RFC 9309, and the distinction matters:

    * **404 or any 4xx** — the host publishes no restrictions, so everything is
      allowed. Most conference sites are in this group.
    * **5xx, or unreachable** — treated as *complete disallow*. A server that
      cannot tell us its rules has not granted permission, and in practice a host
      too broken to serve robots.txt is not going to serve the page either.

    ``Crawl-delay`` is honoured where published, by widening the client's own
    per-host interval — the site's stated rate always wins over ours when it is
    slower.
    """

    def __init__(self, client: PoliteClient, user_agent: str = USER_AGENT) -> None:
        self.client = client
        self.user_agent = user_agent
        self._verdicts: dict[str, object] = {}
        self._lock = threading.Lock()
        self.checked = 0
        self.denied = 0

    def allowed(self, url: str) -> tuple[bool, str]:
        """(may we fetch, why not). Never raises; an unknown host is a denial."""
        host = _host_of(url)
        if not host:
            return False, "no host in URL"

        with self._lock:
            parser = self._verdicts.get(host)
        if parser is None:
            parser = self._load(url, host)
            with self._lock:
                self._verdicts[host] = parser
        if isinstance(parser, str):  # a recorded refusal reason
            return False, parser

        if parser.can_fetch(self.user_agent, url):
            return True, ""
        with self._lock:
            self.denied += 1
        return False, f"{host}/robots.txt disallows {self.user_agent}"

    def _load(self, url: str, host: str):
        from urllib.robotparser import RobotFileParser

        scheme = url.split("://", 1)[0] or "https"
        parser = RobotFileParser()
        with self._lock:
            self.checked += 1
        try:
            response = self.client.get(f"{scheme}://{host}/robots.txt", min_bytes=0)
        except FetchError as exc:
            if exc.status is not None and 400 <= exc.status < 500:
                parser.parse([])  # no rules published: everything is allowed
                return parser
            with self._lock:
                self.denied += 1
            return f"robots.txt unavailable ({exc.reason}); treating as disallow"

        parser.parse(response.text().splitlines())
        # A published crawl delay outranks our default whenever it is slower.
        try:
            delay = parser.crawl_delay(self.user_agent)
        except (AttributeError, ValueError):
            delay = None
        if delay:
            current = self.client.host_intervals.get(host, 0.0)
            self.client.host_intervals[host] = max(current, float(delay))
        return parser


class PoliteClient:
    """Rate-limited, retrying, optionally caching HTTP client."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        host_intervals: dict[str, float] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        offline: bool = False,
        sleep=time.sleep,
    ) -> None:
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        #: Per-host overrides win over ``min_interval`` whenever they are *slower*.
        #: A caller asking for a 2s global gap must not silently speed WikiCFP up
        #: to 2s when the site asks for 5s.
        self.host_intervals = {**HOST_MIN_INTERVAL, **(host_intervals or {})}
        self.timeout = timeout
        self.retries = retries
        #: When offline, a cache miss raises instead of hitting the network. This
        #: is what makes "re-run the parse stage without network access" real.
        self.offline = offline
        self._sleep = sleep
        self._last_request_at: dict[str, float] = {}
        #: Hosts that have throttled us this session, so a subsequent connection
        #: reset is read as "still banned" rather than a transient blip.
        self._throttled_hosts: set[str] = set()
        self.request_count = 0
        self.cache_hits = 0

    # -- public -----------------------------------------------------------

    def interval_for(self, url: str) -> float:
        """The gap this host actually gets: the slower of global and per-host."""
        return max(self.min_interval, self.host_intervals.get(_host_of(url), 0.0))

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        cache: bool = True,
        min_bytes: int = 0,
        expect: Callable[[bytes], bool] | None = None,
    ) -> Response:
        return self._request("GET", url, None, headers, cache, min_bytes, expect)

    def post_json(
        self,
        url: str,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
        cache: bool = True,
        min_bytes: int = 0,
        expect: Callable[[bytes], bool] | None = None,
    ) -> Response:
        body = json.dumps(payload).encode("utf-8")
        merged = {"Content-Type": "application/json", **(headers or {})}
        return self._request("POST", url, body, merged, cache, min_bytes, expect)

    def post_raw(
        self,
        url: str,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        cache: bool = True,
        min_bytes: int = 0,
        expect: Callable[[bytes], bool] | None = None,
    ) -> Response:
        return self._request("POST", url, body, headers, cache, min_bytes, expect)

    # -- internals --------------------------------------------------------

    def _cache_path(self, method: str, url: str, body: bytes | None) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(f"{method} {url} ".encode() + (body or b"")).hexdigest()[:32]
        return self.cache_dir / f"{digest}.cache"

    def _throttle(self, url: str) -> None:
        host = _host_of(url)
        interval = self.interval_for(url)
        last = self._last_request_at.get(host)
        now = time.monotonic()
        if last is not None:
            wait = interval - (now - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at[host] = time.monotonic()

    @staticmethod
    def _validate(payload: bytes, url: str, min_bytes: int, expect) -> None:
        """Reject a 2xx that is not the page we asked for.

        Three probed hosts fail exactly this way and none of them raises on its
        own: SPIE serves an Incapsula bot-wall interstitial with HTTP 200,
        ``www.ieee.org`` answers 202 with a zero-byte body, and SfN serves a
        branded soft-404 at 200. Without this check all three are cached as
        success and the adapter reports a healthy fetch of nothing, forever.
        """
        if min_bytes and len(payload) < min_bytes:
            raise FetchError(
                url, f"body too short: {len(payload)} bytes, expected >= {min_bytes}", 200
            )
        if expect is not None and not expect(payload):
            raise FetchError(url, "response body failed the adapter's content check", 200)

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict[str, str] | None,
        cache: bool,
        min_bytes: int = 0,
        expect: Callable[[bytes], bool] | None = None,
    ) -> Response:
        cache_path = self._cache_path(method, url, body) if cache else None
        if cache_path and cache_path.exists():
            payload = cache_path.read_bytes()
            # A cached body still has to satisfy the content check, or one bad
            # fetch poisons every later run from disk.
            self._validate(payload, url, min_bytes, expect)
            self.cache_hits += 1
            return Response(url=url, status=200, body=payload)

        if self.offline:
            raise FetchError(url, "offline mode and no cached response available")

        host = _host_of(url)
        merged_headers = {"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})}
        delay = 1.0
        last_reason = "unknown"
        last_status: int | None = None

        for attempt in range(self.retries):
            self._throttle(url)
            request = urllib.request.Request(url, data=body, headers=merged_headers, method=method)
            try:
                self.request_count += 1
                with urllib.request.urlopen(request, timeout=self.timeout) as raw:
                    payload = raw.read()
                    response = Response(url=url, status=raw.status, body=payload)
                self._validate(payload, url, min_bytes, expect)
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(payload)
                return response
            except urllib.error.HTTPError as exc:
                last_status = exc.code
                last_reason = f"HTTP {exc.code}"
                if exc.code not in RETRY_STATUS:
                    # 400/403/404 are answers, not hiccups. Retrying is just rude.
                    raise FetchError(url, last_reason, exc.code) from exc
                if exc.code == 429:
                    self._throttled_hosts.add(host)
                    if host in NO_RETRY_AFTER_THROTTLE:
                        # dblp stops answering at the TCP layer after a 429 and
                        # continued probing extends the ban. Stop immediately.
                        raise FetchError(
                            url, "throttled; this host bans on retry, so stopping", 429
                        ) from exc
                    wait = _retry_after(exc)
                    if wait is not None:
                        # Honour the server's own number. OpenReview says 54s;
                        # the 1-2-4-8 ladder totals ~15s and would give up while
                        # still inside the window, reporting the source as dead.
                        delay = min(wait, MAX_RETRY_AFTER)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_reason = str(exc)
                if isinstance(exc, ConnectionResetError) and host in self._throttled_hosts:
                    raise FetchError(
                        url, f"connection reset after throttling; stopping ({exc})", last_status
                    ) from exc

            if attempt < self.retries - 1:
                self._sleep(delay)
                delay *= 2

        raise FetchError(url, f"gave up after {self.retries} attempts ({last_reason})", last_status)


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Seconds the server asked us to wait, if it said so in a form we trust."""
    raw = None
    try:
        raw = exc.headers.get("Retry-After")
    except AttributeError:
        return None
    if not raw:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        return None  # HTTP-date form; not worth parsing for our sources
    return seconds if seconds >= 0 else None


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc or url
