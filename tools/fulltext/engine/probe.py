"""Ask each keyed provider the cheapest question that tells its state apart.

A key can be present and still be useless, in two different ways that need two
different fixes, so "is it set" is not enough:

* **rejected** — the provider does not accept the key (HTTP 401). Fix the key.
* **not entitled here** — the key is fine, but this server is not entitled to
  full text: Elsevier and Wiley authorise by the requesting IP, and Elsevier
  also gates its full-text Article Retrieval API per key behind a library TDM
  agreement. Fix the network, or ask the library. (Wiley answers a made-up
  token and a real one from the wrong network with the same 403, so Wiley is
  reported as "token or network".)

One probe per source, a handful of requests in all. The results are reported,
never cached: a fresh run reflects a key or network change at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

from . import sources as S
from .fetcher import Fetcher
from .sources import cfg

ON = "on"
OFF = "off"  # no key, or a required credential missing
REJECTED = "key rejected"
NOT_ENTITLED = "key fine, not entitled from this network"
#: Wiley's 403 cannot tell a made-up token from a real one on the wrong network.
TOKEN_OR_NETWORK = "refused: token or network"
QUOTA = "quota exhausted"
UNREACHABLE = "unreachable"
UNKNOWN = "unexpected answer"

#: Subscription papers each publisher certainly owns: what an entitlement
#: gates. (Wiley serves its open-access papers to any token at all, even a
#: made-up one, so only a subscription paper says anything about the token.)
ELSEVIER_DOI = "10.1016/j.watres.2020.116073"
WILEY_DOI = "10.1002/anie.200604274"
SPRINGER_DOI = "10.1007/s11356-020-08394-5"
#: An open-access paper every locator knows, for the optional-key lookups.
OPEN_DOI = "10.1111/jcmm.15185"


@dataclass
class Probe:
    source: str
    state: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state == ON


def probe_all(fetcher: Fetcher, sources: list[str] | None = None) -> list[Probe]:
    """A :class:`Probe` for every source (or ``sources``), keyed ones live-checked."""
    out = []
    for source in sources or list(S.SOURCES):
        if source in fetcher.unconfigured:
            out.append(Probe(source, OFF, fetcher.unconfigured[source]))
            continue
        fn = PROBES.get(source)
        if fn is None:
            out.append(Probe(source, ON, "needs no key"))
            continue
        try:
            out.append(fn(fetcher))
        except requests.RequestException as exc:
            out.append(Probe(source, UNREACHABLE, type(exc).__name__))
    return out


def _quota(r: requests.Response) -> bool:
    return r.status_code == 429 or bool(S.QUOTA_RE.search(r.text[:2000] or ""))


def probe_elsevier(f: Fetcher) -> Probe:
    headers = {
        "X-ELS-APIKey": cfg(f.env, "ELSEVIER_API_KEY"),
        "Accept": "application/json",
    }
    if tok := cfg(f.env, "ELSEVIER_INST_TOKEN"):
        headers["X-ELS-Insttoken"] = tok
    search = f.get(
        "elsevier",
        S.ELSEVIER_SEARCH,
        params={"query": "plastic", "count": 1},
        headers=headers,
        attempts=1,
    )
    article = f.get(
        "elsevier",
        S.ELSEVIER + quote(ELSEVIER_DOI, safe=""),
        params={"httpAccept": "text/xml", "view": "FULL"},
        headers={**headers, "Accept": "text/xml"},
        attempts=1,
    )
    if _quota(search) or _quota(article):
        return Probe("elsevier", QUOTA, "Elsevier reports its weekly quota is spent")
    if article.status_code == 200 and "originalText" in article.text:
        return Probe("elsevier", ON, "full-text Article Retrieval answers with a body")
    if search.status_code == 401 or article.status_code == 401:
        if search.status_code == 200:
            return Probe(
                "elsevier",
                NOT_ENTITLED,
                "the Search API accepts the key, the Article Retrieval API "
                "does not: the library must enable full-text access for it",
            )
        return Probe("elsevier", REJECTED, "Elsevier answered 401 to the key")
    if article.status_code == 403 or (
        article.status_code == 400 and "View parameter" in article.text
    ):
        return Probe(
            "elsevier",
            NOT_ENTITLED,
            "the key is valid but not entitled to full text from this "
            "network or agreement: run on a subscribing network, or ask the "
            "library to enable the Article Retrieval API (or for an "
            "institutional token)",
        )
    if article.status_code == 200:
        return Probe(
            "elsevier",
            NOT_ENTITLED,
            "Article Retrieval answers, but with metadata only: not entitled",
        )
    return Probe(
        "elsevier",
        UNKNOWN,
        f"search HTTP {search.status_code}, article HTTP {article.status_code}",
    )


def probe_springer(f: Fetcher) -> Probe:
    key = cfg(f.env, "SPRINGER_API_KEY")
    oa = f.get(
        "springer",
        S.SPRINGER_OA,
        params={"q": f"doi:{SPRINGER_DOI}", "api_key": key},
        attempts=1,
    )
    if oa.status_code in (401, 403):
        return Probe(
            "springer", REJECTED, f"Springer answered {oa.status_code} to the key"
        )
    if _quota(oa):
        return Probe("springer", QUOTA, "Springer's daily request quota is spent")
    if oa.status_code != 200:
        return Probe("springer", UNKNOWN, f"open-access endpoint HTTP {oa.status_code}")
    meta = f.get(
        "springer",
        S.SPRINGER_TDM,
        params={"q": f"doi:{SPRINGER_DOI}", "api_key": key},
        attempts=1,
    )
    if meta.status_code == 200:
        return Probe("springer", ON, "open-access and subscription endpoints both open")
    return Probe(
        "springer",
        ON,
        "open-access content only: this key does not open "
        "Springer's subscription endpoint",
    )


def probe_wiley(f: Fetcher) -> Probe:
    r = f.get(
        "wiley",
        S.WILEY_TDM + quote(WILEY_DOI, safe=""),
        headers={
            "Wiley-TDM-Client-Token": cfg(f.env, "WILEY_TDM_TOKEN"),
            "Accept": "application/pdf",
        },
        attempts=1,
    )
    if r.status_code == 200 and r.content[:5] == b"%PDF-":
        return Probe("wiley", ON, "the token fetched a subscription PDF")
    if r.status_code in (400, 401):
        return Probe("wiley", REJECTED, f"Wiley answered {r.status_code} to the token")
    if r.status_code == 403:
        # Wiley answers the same 403 to a made-up token and to a real token from
        # a network it does not recognise; it does not say which.
        return Probe(
            "wiley",
            TOKEN_OR_NETWORK,
            "Wiley refused a subscription paper: either the token is not a real "
            "one, or this server is not on a subscribing network (Wiley "
            "authorises by IP). Open-access papers still come through",
        )
    if _quota(r):
        return Probe("wiley", QUOTA, "Wiley's daily download quota is spent")
    return Probe("wiley", UNKNOWN, f"HTTP {r.status_code}")


def probe_unpaywall(f: Fetcher) -> Probe:
    r = f.get(
        "unpaywall",
        S.UNPAYWALL + quote(OPEN_DOI, safe=""),
        params={"email": f.email},
        attempts=1,
    )
    if r.status_code == 422:
        return Probe(
            "unpaywall",
            REJECTED,
            "Unpaywall rejected the contact email; it "
            "must be a real, deliverable address",
        )
    if r.status_code == 200:
        return Probe("unpaywall", ON, f"contact email {f.email} accepted")
    return Probe("unpaywall", UNKNOWN, f"HTTP {r.status_code}")


def _optional_key(source: str, env_key: str, call) -> Probe:
    """A free source whose optional key only raises a rate limit."""

    def probe(f: Fetcher) -> Probe:
        if not cfg(f.env, env_key):
            return Probe(source, ON, "no key: works at the anonymous rate limit")
        r = call(f)
        if r.status_code in (401, 403):
            return Probe(
                source,
                REJECTED,
                f"{env_key} answered {r.status_code}; the "
                f"source still works without it if removed",
            )
        return Probe(
            source,
            ON,
            "key accepted"
            if r.status_code == 200
            else f"key sent; lookup answered HTTP {r.status_code}",
        )

    return probe


PROBES = {
    "elsevier": probe_elsevier,
    "springer": probe_springer,
    "wiley": probe_wiley,
    "unpaywall": probe_unpaywall,
    "core": _optional_key(
        "core",
        "CORE_API_KEY",
        lambda f: f.get(
            "core",
            S.CORE,
            params={"q": "plastic", "limit": 1},
            headers={"Authorization": f"Bearer {cfg(f.env, 'CORE_API_KEY')}"},
            attempts=1,
        ),
    ),
    "semanticscholar": _optional_key(
        "semanticscholar",
        "SEMANTIC_SCHOLAR_API_KEY",
        lambda f: f.get(
            "semanticscholar",
            S.S2 + "DOI:" + quote(OPEN_DOI, safe=""),
            params={"fields": "title"},
            headers={"x-api-key": cfg(f.env, "SEMANTIC_SCHOLAR_API_KEY")},
            attempts=1,
        ),
    ),
    "openalex": _optional_key(
        "openalex",
        "OPEN_ALEX_API_KEY",
        lambda f: f.get(
            "openalex",
            S.OPENALEX + "doi:" + quote(OPEN_DOI, safe=""),
            params={"api_key": cfg(f.env, "OPEN_ALEX_API_KEY")},
            attempts=1,
        ),
    ),
}
