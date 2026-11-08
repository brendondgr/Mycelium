"""The multi-source fetcher: walk a chain of sources until one yields a body.

Each ``src_<name>`` method asks one provider for one article and returns
``(markdown, provenance, note)``: the converted body (``""`` when it has none),
where it came from, and a short outcome code ("ok", "closed", "http 404",
"not-found", ...) that :mod:`.routing` turns into words.

Behaviour kept from PubMedExtraction, because each one was learned the hard way:

* every response body is read under a wall-clock deadline and a size cap, so a
  host that trickles bytes cannot hold a worker;
* a 429/5xx whose small body says "quota" is a quota stop, not a flaky server,
  and switches the source off instead of being retried;
* 25 consecutive 401/403s with no success switch a source off (not entitled
  from this network), so a run cannot silently waste thousands of requests;
* definitive answers ("closed", "http 404", "not-found") are remembered and
  never asked again; transient ones (errors, quota) are not.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from . import sources as S
from .cache import DiskCache
from .convert import (
    bytes_to_markdown,
    elsevier_to_markdown,
    jats_to_markdown,
    local_name,
    strip_ns,
    text_to_markdown,
)
from .sources import SOURCES, arxiv_id, cfg
from .state import MemoryState, State

log = logging.getLogger(__name__)

DEFAULT_DISABLE_TTL = 6 * 3600.0
#: Outcome codes that are a definitive "no" for (article, source) and are kept.
DEFINITIVE = (
    "http 404",
    "not-found",
    "closed",
    "no-body",
    "not-wiley",
    "no-links",
    "no-id",
)


class BodyTimeout(requests.Timeout):
    """The response started but did not finish within the deadline or size cap."""


def read_body(r: requests.Response, deadline: float | None = None) -> requests.Response:
    """Read a streamed response under a wall-clock limit and a size cap.

    ``timeout=`` only bounds each socket read, so a host that trickles a byte
    every few seconds could otherwise hold a worker indefinitely. ``read1()``
    returns after at most one socket read, so the deadline is checked as bytes
    arrive.
    """
    deadline = deadline or S.BODY_DEADLINE
    end = time.time() + deadline
    chunks, size = [], 0
    try:
        while chunk := r.raw.read1(64 * 1024, decode_content=True):
            chunks.append(chunk)
            size += len(chunk)
            if time.time() > end:
                raise BodyTimeout(
                    f"body incomplete after {deadline}s ({size:,} bytes): {r.url}"
                )
            if size > S.MAX_BODY:
                raise BodyTimeout(f"body larger than {S.MAX_BODY:,} bytes: {r.url}")
    finally:
        r.close()
    r._content, r._content_consumed = b"".join(chunks), True
    return r


def join_notes(notes) -> str:
    """Distinct outcome notes, minus 'dup' (a URL an earlier source tried)."""
    return "; ".join(n for n in dict.fromkeys(notes) if n != "dup")


class Fetcher:
    """Tries each configured source for one article; caches everything on disk."""

    def __init__(
        self,
        env: Mapping[str, str] | None,
        cache_dir: Path | str,
        *,
        state: State | None = None,
        order: list[str] | None = None,
        min_chars: int = 500,
        retry: bool = False,
        locate_only: bool = False,
        disable_ttl: float = DEFAULT_DISABLE_TTL,
    ):
        self.env = dict(env or {})
        self.cache = DiskCache(cache_dir)
        self.state: State = state or MemoryState()
        self.min_chars = min_chars
        self.retry = retry  # ignore remembered answers and caches: ask again
        self.locate_only = locate_only
        self.disable_ttl = disable_ttl
        self.email = cfg(self.env, "CONTACT_EMAIL") or ""
        self.session = requests.Session()
        self.session.headers["User-Agent"] = S.USER_AGENT + (
            f" mailto:{self.email}" if self.email else ""
        )
        self.stats: Counter = Counter()  # (source, outcome) -> n, this process only
        self._springer_dead: dict[str, bool] = {}
        # The cached file a successful source converted (PDF / XML / HTML), per
        # thread, so callers can keep a copy of the original next to the markdown.
        self._origin = threading.local()
        self.interval = {}
        for s, spec in SOURCES.items():
            keyed = any(
                cfg(self.env, k)
                for k in spec["optional"]
                if k.endswith(("_KEY", "_TOKEN"))
            )
            self.interval[s] = (
                spec["interval"]
                if keyed or "interval_nokey" not in spec
                else spec["interval_nokey"]
            )
        #: Sources off because a credential they need is missing: never expires.
        self.unconfigured = {
            s: "missing " + ", ".join(missing)
            for s in SOURCES
            if (missing := S.missing_credentials(self.env, s))
        }
        self.order = [
            s
            for s in (order or S.DEFAULT_ORDER)
            if s in SOURCES and s not in self.unconfigured
        ]

    # -- switch-offs -------------------------------------------------------- #
    @property
    def disabled(self) -> dict[str, str]:
        """{source: reason} for every source that will not be asked right now."""
        return {**self.unconfigured, **self.state.switched_off()}

    def _disable(self, source: str, reason: str) -> None:
        if self.state.switch_off(source, reason, self.disable_ttl):
            log.warning("full text: %s switched off: %s", source, reason)

    # -- plumbing ----------------------------------------------------------- #
    def _quota_exhausted(self, source: str, r: requests.Response) -> bool:
        """True when a 429/5xx is really 'you are out of quota for today'.

        The body is only inspected when it is small and textual, so a PDF is
        never decoded here.
        """
        if r.status_code not in (429, 500, 503) or len(r.content) > 8000:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        if not any(k in ct for k in ("json", "text", "xml")):
            return False
        try:
            body = r.text[:2000]
        except (UnicodeDecodeError, ValueError):
            return False
        if not S.QUOTA_RE.search(body):
            return False
        detail = re.sub(r"\s+", " ", body).strip()[:120]
        self._disable(
            source, f"provider quota exhausted (HTTP {r.status_code}): {detail}"
        )
        return True

    def get(
        self,
        source: str,
        url: str,
        *,
        params=None,
        headers=None,
        timeout=60,
        attempts=3,
    ) -> requests.Response:
        """GET with per-source throttling, 429/5xx backoff, and Retry-After respect."""
        r = None
        for attempt in range(attempts):
            self.state.wait_turn(source, self.interval.get(source, 0.0))
            try:
                r = read_body(
                    self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=timeout,
                        allow_redirects=True,
                        stream=True,
                    )
                )
            except BodyTimeout:
                raise  # a stalling host will stall again
            except requests.RequestException:
                if attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if self._quota_exhausted(source, r):
                    return r  # not transient: no point retrying
                if attempt == attempts - 1:
                    return r
                ra = r.headers.get("Retry-After")
                try:
                    delay = min(float(ra), 120) if ra else 2.0 * (attempt + 1)
                except ValueError:
                    delay = 5.0
                time.sleep(delay)
                continue
            return r
        return r

    def _remembered(self, key: str, source: str) -> str | None:
        return None if self.retry else self.state.remembered(key, source)

    def _remember(self, key: str, source: str, outcome: str) -> None:
        self.state.remember(key, source, outcome)

    def cache_path(self, source: str, key: str, ext: str) -> Path:
        return self.cache.path(source, key, ext)

    def cached_json(self, source: str, key: str, fetch):
        """A cached lookup, or ``fetch()``'s answer (cached unless it is None,
        which means the lookup failed and should be tried again)."""
        if not self.retry and self.cache.has_json(source, key):
            return self.cache.get_json(source, key)
        data = fetch()
        if data is not None:
            self.cache.put_json(source, key, data)
        return data

    def _cached_text(self, source: str, key: str, ext: str) -> str | None:
        return None if self.retry else self.cache.read_text(source, key, ext)

    def _set_origin(self, path, kind: str) -> None:
        self._origin.path, self._origin.kind = str(path), kind

    # -- download + convert an arbitrary URL -------------------------------- #
    def download(self, source: str, url: str, tried_urls: set, headers=None):
        """Fetch a PDF/HTML/XML URL and convert it. Returns (md, kind, note)."""
        if not url or url in tried_urls:
            return "", "", "dup"
        tried_urls.add(url)
        key = hashlib.sha1(url.encode()).hexdigest()
        raw = self.cache_path("downloads", key, "bin")
        meta = self.cache.get_json("downloads", key + ".meta")
        if raw.exists() and meta and not self.retry:
            data, ct = raw.read_bytes(), meta.get("content_type", "")
        else:
            past = self._remembered("url:" + key, "download")
            if past:
                return "", "", past
            try:
                r = self.get(source, url, headers=headers, timeout=90)
            except requests.RequestException as exc:
                return "", "", f"error {type(exc).__name__}"
            if r.status_code != 200:
                if r.status_code in (401, 403, 404, 410):
                    self._remember("url:" + key, "download", f"http {r.status_code}")
                return "", "", f"http {r.status_code}"
            data, ct = r.content, r.headers.get("content-type", "")
            self.cache.write_bytes("downloads", key, "bin", data)
            self.cache.put_json(
                "downloads",
                key + ".meta",
                {"url": url, "final_url": r.url, "content_type": ct},
            )
        md, kind = bytes_to_markdown(data, ct, self.min_chars)
        if isinstance(kind, tuple) and kind[0] == "pdf-link":
            return self.download(source, kind[1], tried_urls, headers)
        if not md:
            self._remember("url:" + key, "download", f"no-body ({kind})")
            return "", kind, f"no-body ({kind})"
        self._set_origin(raw, "xml" if kind == "jats" else kind)
        return md, kind, "ok"

    # -- individual sources ------------------------------------------------- #
    def src_europepmc(self, pmid, doi, pmcid, tried_urls):
        ids = [pmcid] if pmcid else []
        if not ids and pmid:
            rec = self.cached_json(
                "europepmc", f"search_{pmid}", lambda: self._epmc_search(pmid)
            )
            if rec:
                ids = list((rec.get("fullTextIdList") or {}).get("fullTextId", [])) or (
                    [rec["pmcid"]] if rec.get("pmcid") else []
                )
        if not ids:
            return "", None, "no-id"
        for fid in ids:
            xml = self._cached_text("europepmc", fid, "xml")
            if xml is None:
                r = self.get("europepmc", f"{S.EUROPEPMC}/{fid}/fullTextXML")
                if r.status_code != 200:
                    continue
                xml = r.text
                self.cache.write_text("europepmc", fid, "xml", xml)
            try:
                art = strip_ns(ET.fromstring(xml))
            except ET.ParseError:
                continue
            md = jats_to_markdown(art, self.min_chars)
            if md:
                self._set_origin(self.cache_path("europepmc", fid, "xml"), "xml")
                return (
                    md,
                    {"id": fid, "url": f"https://europepmc.org/article/PMC/{fid}"},
                    "ok",
                )
        return "", None, "no-body"

    def _epmc_search(self, pmid):
        r = self.get(
            "europepmc",
            f"{S.EUROPEPMC}/search",
            params={
                "query": f"EXT_ID:{pmid} AND SRC:MED",
                "format": "json",
                "resultType": "lite",
            },
        )
        if r.status_code != 200:
            return None
        res = r.json().get("resultList", {}).get("result", [])
        return res[0] if res else {}

    def src_elsevier(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        xml = self._cached_text("elsevier", doi, "xml")
        if xml is None:
            headers = {
                "X-ELS-APIKey": cfg(self.env, "ELSEVIER_API_KEY"),
                "Accept": "text/xml",
            }
            tok = cfg(self.env, "ELSEVIER_INST_TOKEN")
            if tok:
                headers["X-ELS-Insttoken"] = tok
            r = self.get(
                "elsevier",
                S.ELSEVIER + quote(doi, safe=""),
                params={"httpAccept": "text/xml", "view": "FULL"},
                headers=headers,
            )
            if r.status_code == 401:
                self._disable(
                    "elsevier",
                    "401 — ELSEVIER_API_KEY rejected (or the key "
                    "is not enabled for this API)",
                )
                return "", None, "disabled"
            if r.status_code == 429 or r.headers.get("X-ELS-Status", "").startswith(
                "QUOTA"
            ):
                reset = r.headers.get("X-RateLimit-Reset")
                when = (
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(int(reset)))
                    if reset and reset.isdigit()
                    else "unknown"
                )
                self._disable("elsevier", f"quota exhausted (resets {when})")
                return "", None, "disabled"
            if r.status_code == 403:
                # Verified on FSU's own network: Search and Abstract Retrieval answer
                # 200 with a key while /content/article/ answers 403 for every view.
                # That is a per-API entitlement, not an IP problem.
                return (
                    "",
                    None,
                    (
                        "http 403 (key valid but the Article Retrieval API is "
                        "not enabled for it — ask the library to add "
                        "full-text/TDM access, or set ELSEVIER_INST_TOKEN)"
                    ),
                )
            if r.status_code == 400 and "View parameter" in r.text:
                # Seen off campus: the FULL view is refused as an invalid parameter
                # rather than a 403. Same meaning, and it must count as a strike.
                return (
                    "",
                    None,
                    (
                        "http 400 (FULL view refused: key not entitled to "
                        "full text from this network/agreement)"
                    ),
                )
            if r.status_code == 404:
                return "", None, "http 404"
            if r.status_code != 200:
                return "", None, f"http {r.status_code}"
            xml = r.text
            self.cache.write_text("elsevier", doi, "xml", xml)
        md = elsevier_to_markdown(xml, self.min_chars)
        if md:
            self._set_origin(self.cache_path("elsevier", doi, "xml"), "xml")
            return md, {"url": f"https://doi.org/{doi}"}, "ok"
        return "", None, "no-body (not entitled or abstract-only record)"

    def src_springer(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        key = cfg(self.env, "SPRINGER_API_KEY")
        xml = self._cached_text("springer", doi, "xml")
        endpoint_used = (
            self.cache.get_json("springer", doi + ".endpoint")
            if xml is not None
            else None
        )
        if xml is None:
            notes = []
            for endpoint in (S.SPRINGER_OA, S.SPRINGER_TDM):
                if self._springer_dead.get(endpoint):
                    continue
                r = self.get(
                    "springer", endpoint, params={"q": f"doi:{doi}", "api_key": key}
                )
                if r.status_code in (401, 403):
                    # A standard key opens openaccess/* only; meta/* needs an
                    # entitled key.
                    self._springer_dead[endpoint] = True
                    if endpoint == S.SPRINGER_OA:
                        self._disable(
                            "springer", f"{r.status_code} — SPRINGER_API_KEY rejected"
                        )
                        return "", None, "disabled"
                    notes.append("meta endpoint not enabled for this key")
                    continue
                if r.status_code == 429:
                    self._disable("springer", "daily quota exhausted")
                    return "", None, "disabled"
                if r.status_code == 200 and "<article" in r.text:
                    xml = r.text
                    endpoint_used = (
                        "openaccess" if endpoint == S.SPRINGER_OA else "meta"
                    )
                    break
                notes.append(f"http {r.status_code}")
            if xml is None:
                if "http 404" in notes:
                    return "", None, "not-found"
                return "", None, join_notes(notes) or "not-found"
            self.cache.write_text("springer", doi, "xml", xml)
            self.cache.put_json("springer", doi + ".endpoint", endpoint_used)
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return "", None, "bad-xml"
        art = next((el for el in root.iter() if local_name(el.tag) == "article"), None)
        md = jats_to_markdown(strip_ns(art), self.min_chars) if art is not None else ""
        if md:
            self._set_origin(self.cache_path("springer", doi, "xml"), "xml")
            return (
                md,
                {"url": f"https://doi.org/{doi}", "endpoint": endpoint_used},
                "ok",
            )
        return "", None, "no-body (not entitled or abstract-only record)"

    def src_wiley(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        if not doi.lower().startswith(S.WILEY_PREFIXES):
            return "", None, "not-wiley"
        headers = {
            "Wiley-TDM-Client-Token": cfg(self.env, "WILEY_TDM_TOKEN"),
            "Accept": "application/pdf",
        }
        md, kind, note = self.download(
            "wiley", S.WILEY_TDM + quote(doi, safe=""), tried_urls, headers
        )
        if note == "http 401":
            self._disable("wiley", "401 — WILEY_TDM_TOKEN rejected")
            return "", None, "disabled"
        if "wiley" in self.state.switched_off():
            return "", None, "quota exhausted — retry tomorrow"
        if md:
            return md, {"url": f"https://doi.org/{doi}", "kind": kind}, "ok"
        return "", None, note

    def src_arxiv(self, pmid, doi, pmcid, tried_urls):
        aid = arxiv_id(doi)
        if not aid:
            return "", None, "not-arxiv"
        url = S.ARXIV_PDF + aid
        if self.locate_only:
            return "", {"url": url}, "located"
        md, kind, note = self.download("arxiv", url, tried_urls)
        if md:
            return md, {"url": f"https://arxiv.org/abs/{aid}", "kind": kind}, "ok"
        return "", None, note

    def src_crossref(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        rec = self.cached_json("crossref", doi, lambda: self.crossref_record(doi))
        if not rec:
            return "", None, "not-found"
        links = [
            ln
            for ln in rec.get("link", [])
            if ln.get("intended-application") == "text-mining"
        ]
        rank = {
            "text/xml": 0,
            "application/xml": 0,
            "application/pdf": 1,
            "text/html": 2,
            "text/plain": 3,
            "unspecified": 4,
        }
        links.sort(key=lambda ln: rank.get(ln.get("content-type", "unspecified"), 5))
        notes = []
        for ln in links:
            url = ln.get("URL", "")
            host = url.split("/")[2] if url.count("/") >= 2 else ""
            if host in ("api.elsevier.com", "api.wiley.com"):
                notes.append(
                    f"needs-key ({host})"
                )  # served by the dedicated keyed source
                continue
            md, kind, note = self.download("crossref", url, tried_urls)
            if md:
                return md, {"url": url, "kind": kind}, "ok"
            notes.append(note)
        return "", None, join_notes(notes) or "no-links"

    def crossref_record(self, doi):
        """Crossref work: dict, {} when Crossref does not know it, None on error."""
        params = {"mailto": self.email} if self.email else None
        r = self.get("crossref", S.CROSSREF + quote(doi, safe=""), params=params)
        if r.status_code != 200:
            return {} if r.status_code == 404 else None
        return r.json().get("message", {})

    def src_core(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        rec = self.cached_json("core", doi, lambda: self._core(doi))
        if rec is None:
            return "", None, "error"
        if not rec:
            return "", None, "not-found"
        full = rec.get("fullText") or ""
        if len(full) >= max(self.min_chars, 3000):
            # CORE hands over plain text inside JSON; keep it as a file so the
            # caller has an original for this source too.
            txt = self.cache.write_text("core", doi, "txt", full)
            self._set_origin(txt, "text")
            url = rec.get("downloadUrl") or f"https://core.ac.uk/works/{rec.get('id')}"
            return text_to_markdown(full), {"url": url, "kind": "text"}, "ok"
        urls = [rec.get("downloadUrl")] + list(rec.get("sourceFulltextUrls") or [])
        notes = []
        for url in [u for u in urls if u]:
            md, kind, note = self.download("core", url, tried_urls)
            if md:
                return md, {"url": url, "kind": kind}, "ok"
            notes.append(note)
        return "", None, join_notes(notes) or "no-links"

    def _core(self, doi):
        headers = {}
        key = cfg(self.env, "CORE_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        r = self.get(
            "core", S.CORE, params={"q": f'doi:"{doi}"', "limit": 3}, headers=headers
        )
        if r.status_code == 401:
            self._disable("core", "401 — CORE_API_KEY rejected")
            return None
        if r.status_code != 200:
            return None  # includes a 429 still standing after backoff: next time
        for w in r.json().get("results", []):
            if (w.get("doi") or "").lower() == doi.lower():
                return {
                    k: w.get(k)
                    for k in (
                        "id",
                        "doi",
                        "fullText",
                        "downloadUrl",
                        "sourceFulltextUrls",
                    )
                }
        return {}

    def src_unpaywall(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        rec = self.cached_json("unpaywall", doi, lambda: self.unpaywall_record(doi))
        if rec is None:
            return "", None, "error"
        oa = self.oa_summary(rec)
        if not rec.get("is_oa"):
            return "", oa, "closed"
        if self.locate_only:
            return "", oa, "located"
        locs = [rec.get("best_oa_location") or {}] + list(rec.get("oa_locations") or [])
        urls = []
        for loc in locs:
            for u in (loc.get("url_for_pdf"), loc.get("url")):
                if u and u not in urls:
                    urls.append(u)
        notes = []
        for url in urls:
            md, kind, note = self.download("unpaywall", url, tried_urls)
            if md:
                return md, {**oa, "url": url, "kind": kind}, "ok"
            notes.append(note)
        return "", oa, join_notes(notes) or "no-links"

    def unpaywall_record(self, doi):
        """Unpaywall's answer for a DOI, trimmed; None on error."""
        r = self.get(
            "unpaywall", S.UNPAYWALL + quote(doi, safe=""), params={"email": self.email}
        )
        if r.status_code == 422:
            self._disable(
                "unpaywall",
                "Unpaywall rejected the contact email (it must be a real address)",
            )
            return None
        if r.status_code == 404:
            return {"is_oa": False, "oa_status": "unknown-doi"}
        if r.status_code != 200:
            return None
        j = r.json()
        return {
            k: j.get(k)
            for k in ("is_oa", "oa_status", "best_oa_location", "oa_locations")
        }

    @staticmethod
    def oa_summary(rec) -> dict:
        best = rec.get("best_oa_location") or {}
        return {
            "oa": bool(rec.get("is_oa")),
            "status": rec.get("oa_status"),
            "host": best.get("host_type"),
            "version": best.get("version"),
            "pdf": best.get("url_for_pdf"),
            "url": best.get("url"),
        }

    def src_openalex(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        rec = self.cached_json("openalex", doi, lambda: self._openalex(doi))
        if rec is None:
            return "", None, "error"
        if not rec:
            return "", None, "not-found"
        if not rec.get("is_oa"):
            return "", None, "closed"
        if self.locate_only:
            return (
                "",
                {"status": rec.get("oa_status"), "url": rec.get("oa_url")},
                "located",
            )
        notes = []
        for url in rec.get("urls", []):
            md, kind, note = self.download("openalex", url, tried_urls)
            if md:
                return (
                    md,
                    {"status": rec.get("oa_status"), "url": url, "kind": kind},
                    "ok",
                )
            notes.append(note)
        return "", None, join_notes(notes) or "no-links"

    def _openalex(self, doi):
        params = {}
        key = cfg(self.env, "OPEN_ALEX_API_KEY")
        if key:
            params["api_key"] = key
        elif self.email:
            params["mailto"] = self.email
        r = self.get(
            "openalex", S.OPENALEX + "doi:" + quote(doi, safe=""), params=params
        )
        if r.status_code == 404:
            return {}
        if r.status_code == 403 and key:
            self._disable("openalex", "403 — OPEN_ALEX_API_KEY rejected")
            return None
        if r.status_code != 200:
            return None
        j = r.json()
        oa = j.get("open_access") or {}
        urls = []
        for loc in [j.get("best_oa_location") or {}] + list(j.get("locations") or []):
            for u in (loc.get("pdf_url"), loc.get("landing_page_url")):
                if u and u not in urls:
                    urls.append(u)
        if oa.get("oa_url") and oa["oa_url"] not in urls:
            urls.insert(0, oa["oa_url"])
        return {
            "is_oa": bool(oa.get("is_oa")),
            "oa_status": oa.get("oa_status"),
            "oa_url": oa.get("oa_url"),
            "urls": urls,
        }

    def src_semanticscholar(self, pmid, doi, pmcid, tried_urls):
        if not doi:
            return "", None, "no-doi"
        rec = self.cached_json("semanticscholar", doi, lambda: self._s2(doi))
        if rec is None:
            return "", None, "error"
        url = (rec.get("openAccessPdf") or {}).get("url")
        if not url:
            return "", None, "not-found" if not rec else "closed"
        if self.locate_only:
            return "", {"url": url}, "located"
        md, kind, note = self.download("semanticscholar", url, tried_urls)
        if md:
            return md, {"url": url, "kind": kind}, "ok"
        return "", None, note

    def _s2(self, doi):
        headers = {}
        key = cfg(self.env, "SEMANTIC_SCHOLAR_API_KEY")
        if key:
            headers["x-api-key"] = key
        r = self.get(
            "semanticscholar",
            S.S2 + "DOI:" + quote(doi, safe=""),
            params={"fields": "openAccessPdf,isOpenAccess"},
            headers=headers,
        )
        if r.status_code == 404:
            return {}
        if r.status_code == 403 and key:
            self._disable("semanticscholar", "403 — SEMANTIC_SCHOLAR_API_KEY rejected")
            return None
        if r.status_code != 200:
            return None
        return r.json()

    # -- driver ------------------------------------------------------------- #
    def fetch(self, pmid, doi, pmcid, order=None):
        """Walk the source chain for one article.

        Returns ``(md, source, provenance, tried, oa)``. ``order`` overrides the
        configured chain for this one article (routing sends each article only
        to the sources that can plausibly serve it). PMC is handled by the
        batched pre-pass in :mod:`.pipeline`, so it is skipped here.
        """
        tried: OrderedDict[str, str] = OrderedDict()
        tried_urls: set = set()
        oa = None
        key = doi or f"pmid:{pmid}"
        disabled = self.disabled
        for source in self.order if order is None else order:
            if source == "pmc":
                continue
            if source in disabled:
                tried[source] = "disabled"
                continue
            past = self._remembered(key, source)
            if past:
                tried[source] = f"{past} (cached)"
                continue
            fn = getattr(self, f"src_{source}")
            self._origin.__dict__.clear()
            try:
                md, prov, note = fn(pmid, doi, pmcid, tried_urls)
            except requests.RequestException as exc:
                md, prov, note = "", None, f"error {type(exc).__name__}"
            except Exception as exc:  # never let one source kill the article
                log.exception("full text: %s failed for %s", source, key)
                md, prov, note = "", None, f"error {type(exc).__name__}: {exc}"
            tried[source] = note
            if md:
                self.state.clear_strikes(source)
            elif "403" in note or "not entitled" in note or "401" in note:
                n = self.state.strike(source)
                if n >= S.ENTITLEMENT_STRIKES and not self.stats[(source, "ok")]:
                    self._disable(
                        source,
                        (
                            f"{n} consecutive refusals with no successes — not "
                            f"entitled from this network; run from a subscribing "
                            f"network or set an institutional token"
                        ),
                    )
            if source == "unpaywall" and prov:
                oa = {
                    k: prov.get(k)
                    for k in ("oa", "status", "host", "version", "pdf", "url")
                }
            outcome = (
                "ok" if md else (re.split(r"[ ;(]", note, maxsplit=1)[0] or "none")
            )
            self.stats[(source, outcome)] += 1
            if md:
                if getattr(self._origin, "path", None):
                    prov = {
                        **(prov or {}),
                        "original": {
                            "path": self._origin.path,
                            "kind": self._origin.kind,
                        },
                    }
                return md, source, prov, tried, oa
            if note == "no-doi" or note.startswith(DEFINITIVE):
                self._remember(key, source, note)
        return "", None, None, tried, oa


def is_licensed(source: str | None, provenance: dict | None) -> bool:
    """Whether a paper from ``source`` is subscription content (licensed to the
    instance's institution) rather than an open copy."""
    if source in S.LICENSED_SOURCES:
        return True
    return source == "springer" and (provenance or {}).get("endpoint") == "meta"


def describe(fetcher: Fetcher) -> list[dict]:
    """Each source, whether it is live on this instance, and why not."""
    disabled = fetcher.disabled
    return [
        {
            "source": s,
            "label": spec["label"],
            "available": s not in disabled,
            "reason": disabled.get(s),
            "needs": list(spec["needs"]),
            "keyed": s in S.KEYED_SOURCES,
        }
        for s, spec in SOURCES.items()
    ]


__all__ = [
    "Fetcher",
    "BodyTimeout",
    "read_body",
    "join_notes",
    "is_licensed",
    "describe",
]
