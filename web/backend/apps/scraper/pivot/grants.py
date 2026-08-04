"""Pivot-RP funding (grants) scraper — vendored from the ProQuest tool.

Condenses ``utils/ProQuest/grants/{scrape,detail,enrich}.py`` into a single
module. The public entry point is :func:`scrape_grants`; it returns a list of
record dicts ready for the Mycelium ingest layer.

``playwright`` and ``bs4`` are optional extras — this module imports cleanly
when they are absent; the imports happen inside functions.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

from .common import BASE, STATE_PATH
from .normalize import normalize_date

SEARCH_PATH = "/funding/results"
BASE_PAIRS = [("dismiss_filter", "on"), ("results_type", "adhoc_search")]
DEFAULT_FILTERS = [
    ("fq_fundingType[]", "research"),
    ("fq_requirements[]", "academic"),
    ("fq_currency[]", "USD"),
]
DATE_RE = re.compile(r"\d{1,2}\s+\w{3,}\s+\d{4}")
DETAIL_DATE_RE = re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}")
DETAIL_FIELDS = ["amount", "website", "ai_summary", "abstract"]


class SessionExpired(Exception):
    pass


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _build_url(query: str, page: int, rows: int, filters: list) -> str:
    pairs = (
        [("full_ai", query)]
        + BASE_PAIRS
        + list(filters)
        + [("rows", rows), ("page", page)]
    )
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in pairs)
    return f"{BASE}{SEARCH_PATH}?{qs}"


# ---------------------------------------------------------------------------
# Search-results HTML parsing (BeautifulSoup)
# ---------------------------------------------------------------------------


def _parse_results(html: str):
    """Return (total_count_or_None, [row dicts]) from a search results page."""
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    total = None
    m = re.search(r"([\d,]+)\s+Results", soup.get_text())
    if m:
        total = int(m.group(1).replace(",", ""))
    rows = []
    for a in soup.select("a.results-title-link"):
        tr = a.find_parent("tr")
        href = a.get("href", "")
        sponsor = tr.select_one(".sponsor-info") if tr else None
        dl = tr.select_one("td.deadline a.deadline_link") if tr else None
        dl_text = " ".join(dl.get_text(" ", strip=True).split()) if dl else ""
        dm = DATE_RE.search(dl_text)
        deadline_date = normalize_date(dm.group(0)) if dm else ""
        rows.append(
            {
                "id": href.rstrip("/").split("/")[-1],
                "title": a.get_text(strip=True),
                "sponsor": sponsor.get_text(strip=True) if sponsor else "",
                "deadline": dl_text,
                "deadline_date": deadline_date,
                "url": BASE + href,
            }
        )
    return total, rows


# ---------------------------------------------------------------------------
# Detail-page parsing
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    text = " ".join((text or "").split())
    text = re.sub(r"\s*\b(Show\s+)?(more|less)\s*$", "", text, flags=re.I)
    return text.strip()


def _label_map(soup):
    """Map normalized field label -> its value-column element."""
    out = {}
    for lab in soup.select("span.small-label"):
        label = " ".join(lab.get_text(" ", strip=True).split())
        label = re.sub(r"^.*?(AI Generated (?:Title|Summary))$", r"\1", label)
        col = lab.find_parent("div")
        value = col.find_next_sibling("div") if col else None
        if label and value is not None and label not in out:
            out[label] = value
    return out


def _parse_amount(value_col) -> str:
    if value_col is None:
        return ""
    strong = value_col.find("strong")
    if strong:
        txt = _clean(strong.get_text(" ", strip=True))
        if txt:
            return txt
    amt = value_col.select_one(".amount-currency")
    if amt:
        return _clean(amt.get_text(" ", strip=True))
    return _clean(value_col.get_text(" ", strip=True))[:400]


def _parse_website(value_col) -> str:
    if value_col is None:
        return ""
    a = value_col.select_one("a[href]")
    if not a:
        return ""
    href = a.get("href", "").strip()
    if href.startswith("http") and "pivot.proquest.com" not in href:
        return href
    txt = a.get_text(" ", strip=True)
    return txt if txt.startswith("http") else href


def _parse_deadlines(soup):
    """Return (dates_str, notes_str) from the detail page deadline sections."""
    dates, notes = [], []
    for sec in soup.select(".deadline_section, .alert-deadline, .deadline_item"):
        txt = " ".join(sec.get_text(" ", strip=True).split())
        if "Enter date in format" in txt or "save or cancel" in txt.lower():
            continue
        for d in DETAIL_DATE_RE.findall(txt):
            if d not in dates:
                dates.append(d)
        if txt and txt.lower() not in ("upcoming deadlines",):
            notes.append(txt)
    return "; ".join(dates), " | ".join(n for n in notes if n)


def _parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    fields = _label_map(soup)

    abstract_col = fields.get("Abstract")
    ai_col = fields.get("AI Generated Summary")
    amount_col = fields.get("Amount")
    website_col = fields.get("Website")

    return {
        "abstract": (
            _clean(abstract_col.get_text(" ", strip=True)) if abstract_col else ""
        ),
        "ai_summary": _clean(ai_col.get_text(" ", strip=True)) if ai_col else "",
        "amount": _parse_amount(amount_col),
        "website": _parse_website(website_col),
    }


# ---------------------------------------------------------------------------
# Sync search pass (playwright.sync_api)
# ---------------------------------------------------------------------------


def _scrape_topic(
    req, topic: str, rows_per: int, max_pages: int, delay: float, filters: list
):
    """Paginate one query. Returns (total, {id: row})."""
    collected: dict = {}
    page = 1
    total = None
    while page <= max_pages:
        resp = req.get(_build_url(topic, page, rows_per, filters))
        if "session/login" in (resp.url or ""):
            raise SessionExpired()
        if resp.status != 200:
            break
        total, rows = _parse_results(resp.text())
        if not rows:
            break
        for r in rows:
            collected[r["id"]] = r
        if total is not None and page * rows_per >= total:
            break
        if len(rows) < rows_per:
            break
        page += 1
        time.sleep(delay)
    return total, collected


# ---------------------------------------------------------------------------
# Async enrich pass (playwright.async_api)
# ---------------------------------------------------------------------------


def _needs_enrich(rec: dict) -> bool:
    return not (rec.get("abstract") or rec.get("ai_summary"))


async def _fetch_one_detail(
    req, sem, rec: dict, delay: float, retries: int = 2
) -> dict:
    async with sem:
        last_err = ""
        for attempt in range(retries + 1):
            try:
                resp = await req.get(rec["url"], timeout=30000)
                if "session/login" in (resp.url or ""):
                    raise SessionExpired()
                if resp.status == 200:
                    data = _parse_detail(await resp.text())
                    if delay:
                        await asyncio.sleep(delay)
                    return {k: data.get(k, "") for k in DETAIL_FIELDS}
                last_err = f"HTTP {resp.status}"
            except SessionExpired:
                raise
            except Exception as e:
                last_err = str(e).splitlines()[0][:80]
            if attempt < retries:
                await asyncio.sleep(1.0 * (attempt + 1))
        out = {k: "" for k in DETAIL_FIELDS}
        out["_error"] = last_err
        return out


async def _enrich_records(
    records: list[dict], concurrency: int = 5, delay: float = 0.25
) -> None:
    """Fetch detail pages concurrently and merge fields into records in-place."""
    from playwright.async_api import async_playwright  # lazy

    todo = [r for r in records if _needs_enrich(r)]
    if not todo:
        return

    async with async_playwright() as p:
        req = await p.request.new_context(storage_state=str(STATE_PATH))
        sem = asyncio.Semaphore(concurrency)

        async def worker(rec: dict) -> None:
            fields = await _fetch_one_detail(req, sem, rec, delay)
            fields.pop("_error", None)
            rec.update(fields)

        tasks = [asyncio.create_task(worker(r)) for r in todo]
        try:
            await asyncio.gather(*tasks)
        except SessionExpired:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await req.dispose()
            raise
        await req.dispose()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def scrape_grants(
    topics: list[str],
    *,
    rows: int = 100,
    max_pages: int = 60,
    delay: float = 1.0,
    filters: list | None = None,
    enrich: bool = True,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """Scrape Pivot-RP funding opportunities for the given topics.

    Parameters
    ----------
    topics:
        Search queries / keywords to look up on Pivot.
    rows:
        Results per page (max 100 on Pivot's side).
    max_pages:
        Page cap per topic to avoid runaway pagination.
    delay:
        Seconds to sleep between paginated requests.
    filters:
        List of ``(key, value)`` facet filter pairs. Defaults to
        ``DEFAULT_FILTERS`` (research / academic / USD) when *None*.
    enrich:
        If True, fetch each opportunity's detail page to add ``amount``,
        ``website``, ``ai_summary``, and ``abstract``.
    log:
        Optional callable for progress messages.

    Returns
    -------
    list[dict]
        Records with keys ``id, title, sponsor, amount, website, deadline,
        deadline_date, matched_topics, ai_summary, abstract, url, scraped_at``.
    """
    from playwright.sync_api import sync_playwright  # lazy

    _log = log or (lambda _: None)

    if filters is None:
        filters = DEFAULT_FILTERS

    scraped_at = datetime.now(UTC).isoformat(timespec="seconds")
    _log(f"scrape_grants: {len(topics)} topic(s), filters={filters or 'none'}")

    # The Pivot funding search is query-driven — with no topics there is nothing to
    # search for and the loop below collects nothing. That used to look like a
    # successful scrape returning zero records, which is indistinguishable from "no
    # grants matched today"; say so plainly instead.
    if not topics:
        _log(
            "scrape_grants: no topics supplied — the Pivot funding search needs at "
            "least one query, so NO grants were scraped (this is a configuration "
            "problem, not an empty result set)."
        )
        return []

    master: dict = {}
    with sync_playwright() as p:
        req = p.request.new_context(storage_state=str(STATE_PATH))
        try:
            for topic in topics:
                _log(f"  [{topic}]")
                _, found = _scrape_topic(req, topic, rows, max_pages, delay, filters)
                for oid, row in found.items():
                    entry = master.setdefault(oid, {"row": row, "topics": set()})
                    entry["topics"].add(topic)
        finally:
            req.dispose()

    records: list[dict] = []
    for opp in master.values():
        rec = dict(opp["row"])
        rec["matched_topics"] = "; ".join(sorted(opp["topics"]))
        rec["scraped_at"] = scraped_at
        # Ensure all schema keys present
        for k in ("amount", "website", "ai_summary", "abstract"):
            rec.setdefault(k, "")
        records.append(rec)
    records.sort(key=lambda r: (r.get("deadline_date") or "9999", r.get("title", "")))

    if enrich and records:
        _log(f"  enriching {len(records)} opportunities…")
        asyncio.run(_enrich_records(records))

    return records
