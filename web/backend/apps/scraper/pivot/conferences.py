"""Pivot-RP papers-invited (conferences) scraper — vendored from the ProQuest tool.

Condenses ``utils/ProQuest/conferences/{scrape,detail,enrich}.py`` into a
single module. The public entry point is :func:`scrape_conferences`; it returns
a list of record dicts ready for the Mycelium ingest layer.

``playwright`` and ``bs4`` are optional extras — this module imports cleanly
when they are absent; the imports happen inside functions.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime
from math import ceil
from urllib.parse import quote

from .common import BASE, STATE_PATH
from .normalize import normalize_date

MAIN_PATH = "/papers_invited/main"
RESULTS_PATH = "/papers_invited/results"

ID_RE = re.compile(r"/papers_invited/(\d+)")
SUBJECT_RE = re.compile(r"subject(?:\[\]|%5B%5D)=(\d+)")
COUNT_RE = re.compile(r"\((\d[\d,]*)\)\s*$")
DATE_RE = re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}")
EVENT_DATE_RE = re.compile(r"(start|end)\s+date\s+of\s+event", re.I)
DEADLINE_RE = re.compile(r"deadline", re.I)

DETAIL_FIELDS = [
    "name",
    "location",
    "country",
    "scope",
    "website",
    "keywords",
    "organizers",
    "eligibility",
    "language",
    "submission_guidelines",
    "timeline",
    "deadlines",
    "event_dates",
]
FALLBACK_FIELDS = ["name", "organizers", "event_dates", "deadlines"]


class SessionExpired(Exception):
    pass


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _build_results_url(code: str, page: int, rows: int) -> str:
    pairs = [("subject[]", code), ("rows", rows), ("page", page)]
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in pairs)
    return f"{BASE}{RESULTS_PATH}?{qs}"


# ---------------------------------------------------------------------------
# HTML parsing (BeautifulSoup)
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _parse_subjects(html: str) -> list[dict]:
    """Return [{code, name, count}] from the browse-by-subject main page."""
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    seen: set = set()
    out = []
    for a in soup.select('a[href*="papers_invited/results"]'):
        href = a.get("href", "")
        m = SUBJECT_RE.search(href)
        if not m:
            continue
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)
        label = " ".join(a.get_text(" ", strip=True).split())
        cm = COUNT_RE.search(label)
        count = int(cm.group(1).replace(",", "")) if cm else None
        name = COUNT_RE.sub("", label).strip()
        out.append({"code": code, "name": name, "count": count})
    return out


def _row_inline_fields(cell) -> dict:
    """Pull event_dates, deadlines, organizers from a results-row cell (fallback)."""
    out = {"event_dates": "", "deadlines": "", "organizers": ""}
    if cell is None:
        return out
    sub = cell.select_one("span.pi-sub-title")
    if sub:
        out["event_dates"] = re.sub(
            r"^Event Date:\s*", "", _clean(sub.get_text(" ", strip=True))
        )
    deadlines = []
    for lab in cell.select("span.dl-label"):
        label = _clean(lab.get_text(" ", strip=True)).rstrip(":")
        nxt = lab.next_sibling
        date = ""
        while nxt is not None:
            txt = (
                nxt.get_text(" ", strip=True)
                if hasattr(nxt, "get_text")
                else str(nxt)
            )
            m = DATE_RE.search(txt or "")
            if m:
                date = m.group(0)
                break
            if getattr(nxt, "name", None) == "span":
                break
            nxt = nxt.next_sibling
        if date:
            deadlines.append(f"{date} ({label})" if label else date)
    out["deadlines"] = "; ".join(deadlines)
    orgs = [
        _clean(s.get_text(" ", strip=True))
        for s in cell.select("span[tabindex]")
        if not s.get("class")
    ]
    out["organizers"] = ", ".join(o for o in orgs if o)
    return out


def _parse_results(html: str):
    """Return (total_count_or_None, [row dicts]) from a subject results page."""
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    total = None
    m = re.search(r"([\d,]+)\s+Results", soup.get_text())
    if m:
        total = int(m.group(1).replace(",", ""))
    rows: list[dict] = []
    seen: set = set()
    for a in soup.select("a.results-title-link, a.pi-name-link"):
        href = a.get("href", "")
        idm = ID_RE.search(href)
        if not idm:
            continue
        cid = idm.group(1)
        if cid in seen:
            continue
        seen.add(cid)
        cell = a.find_parent("td") or a.find_parent("tr")
        rec = {
            "id": cid,
            "name": _clean(a.get_text(" ", strip=True)),
            "url": f"{BASE}/papers_invited/{cid}",
        }
        rec.update(_row_inline_fields(cell))
        rows.append(rec)
    return total, rows


# ---------------------------------------------------------------------------
# Detail-page parsing
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    text = " ".join((text or "").split())
    text = re.sub(r"\s*\b(Show\s+)?(more|less)\s*$", "", text, flags=re.I)
    return text.strip()


def _label_value_map(soup):
    out = {}
    for lab in soup.select("span.small-label"):
        label = " ".join(lab.get_text(" ", strip=True).split())
        label = re.sub(r"^.*?(AI Generated (?:Title|Summary))$", r"\1", label)
        col = lab.find_parent("div")
        value = col.find_next_sibling("div") if col else None
        if label and value is not None and label not in out:
            out[label] = value
    return out


def _text(value_col) -> str:
    if value_col is None:
        return ""
    return _clean_text(value_col.get_text(" ", strip=True))


def _detail_website(value_col) -> str:
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


def _timeline(value_col) -> list[dict]:
    out = []
    if value_col is None:
        return out
    for dt in value_col.select("dt"):
        date = _clean_text(dt.get_text(" ", strip=True))
        dd = dt.find_next_sibling("dd")
        desc = _clean_text(dd.get_text(" ", strip=True)) if dd else ""
        if date:
            out.append({"date": normalize_date(date) or date, "description": desc})
    return out


def _parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    fields = _label_value_map(soup)

    tl = _timeline(fields.get("Timeline / Important Dates"))
    deadlines = [
        f"{e['date']} ({e['description']})" if e["description"] else e["date"]
        for e in tl
        if DEADLINE_RE.search(e["description"])
    ]
    event_dates = [
        f"{e['date']} ({e['description']})" if e["description"] else e["date"]
        for e in tl
        if EVENT_DATE_RE.search(e["description"])
    ]

    return {
        "name": _text(fields.get("Conference Name")),
        "location": _text(fields.get("Conference Location")),
        "country": _text(fields.get("Conference Country")),
        "scope": _text(fields.get("Scope")),
        "website": _detail_website(fields.get("Website")),
        "keywords": _text(fields.get("Keywords")),
        "organizers": _text(fields.get("Organizers")),
        "eligibility": _text(fields.get("Eligibility")),
        "language": _text(fields.get("Language")),
        "submission_guidelines": _text(fields.get("Submission Guidelines")),
        "timeline": tl,
        "deadlines": "; ".join(deadlines),
        "event_dates": "; ".join(event_dates),
    }


# ---------------------------------------------------------------------------
# Async listing pass
# ---------------------------------------------------------------------------


async def _fetch_html(req, sem, url: str, delay: float, retries: int = 2) -> str:
    async with sem:
        last_err = ""
        for attempt in range(retries + 1):
            try:
                resp = await req.get(url, timeout=30000)
                if "session/login" in (resp.url or ""):
                    raise SessionExpired()
                if resp.status == 200:
                    html = await resp.text()
                    if delay:
                        await asyncio.sleep(delay)
                    return html
                last_err = f"HTTP {resp.status}"
            except SessionExpired:
                raise
            except Exception as e:
                last_err = str(e).splitlines()[0][:80]
            if attempt < retries:
                await asyncio.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"{url}: {last_err}")


def _merge(collected: dict, rows: list[dict]) -> None:
    for r in rows:
        collected[r["id"]] = r


async def _scrape_subject(
    req, sem, subject: dict, rows_per: int, max_pages: int, delay: float
):
    code = subject["code"]
    collected: dict = {}
    try:
        html = await _fetch_html(req, sem, _build_results_url(code, 1, rows_per), delay)
    except SessionExpired:
        raise
    except RuntimeError:
        return subject, collected

    total, rows = _parse_results(html)
    _merge(collected, rows)

    if total is not None:
        npages = min(max_pages, max(1, ceil(total / rows_per)))
        if npages > 1:
            urls = [
                _build_results_url(code, pg, rows_per) for pg in range(2, npages + 1)
            ]
            results = await asyncio.gather(
                *[_fetch_html(req, sem, u, delay) for u in urls],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, SessionExpired):
                    raise r
                if isinstance(r, Exception):
                    continue
                _, rws = _parse_results(r)
                _merge(collected, rws)
    else:
        page = 1
        while len(rows) == rows_per and page < max_pages:
            page += 1
            url = _build_results_url(code, page, rows_per)
            html = await _fetch_html(req, sem, url, delay)
            _, rows = _parse_results(html)
            _merge(collected, rows)

    return subject, collected


async def _scrape_all(
    subject_filter: list[str] | None,
    limit_subjects: int | None,
    rows_per: int,
    max_pages: int,
    list_concurrency: int,
    delay: float,
) -> dict:
    from playwright.async_api import async_playwright  # lazy

    master: dict = {}
    tasks: list = []
    async with async_playwright() as p:
        req = await p.request.new_context(storage_state=str(STATE_PATH))
        sem = asyncio.Semaphore(list_concurrency)
        try:
            main_html = await _fetch_html(req, sem, f"{BASE}{MAIN_PATH}", delay)
            subjects = _parse_subjects(main_html)
            if subject_filter:
                wanted = set(subject_filter)
                subjects = [s for s in subjects if s["code"] in wanted]
            if limit_subjects:
                subjects = subjects[:limit_subjects]
            if not subjects:
                await req.dispose()
                return {}
            tasks = [
                asyncio.create_task(
                    _scrape_subject(req, sem, s, rows_per, max_pages, delay)
                )
                for s in subjects
            ]
            results = await asyncio.gather(*tasks)
        except SessionExpired:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await req.dispose()
            raise
        await req.dispose()

    for subject, collected in results:
        for cid, row in collected.items():
            entry = master.setdefault(cid, {"row": row, "subjects": set()})
            entry["subjects"].add(subject["name"])
    return master


# ---------------------------------------------------------------------------
# Async enrich pass
# ---------------------------------------------------------------------------


def _needs_enrich(rec: dict) -> bool:
    return not (rec.get("scope") or rec.get("location"))


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
            # Keep row-supplied fallback fields if detail page returned empty.
            for k in FALLBACK_FIELDS:
                if not fields.get(k) and rec.get(k):
                    fields.pop(k, None)
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
# Sort helper
# ---------------------------------------------------------------------------


def _sort_key(rec: dict):
    dates = DATE_RE.findall(
        " ".join([rec.get("deadlines", ""), rec.get("event_dates", "")])
    )
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(d, "%d %b %Y"))
        except ValueError:
            try:
                parsed.append(datetime.strptime(d, "%d %B %Y"))
            except ValueError:
                pass
    key = min(parsed).strftime("%Y-%m-%d") if parsed else "9999-99-99"
    return (key, rec.get("name", ""))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def scrape_conferences(
    *,
    subjects: list[str] | None = None,
    limit_subjects: int | None = None,
    rows: int = 100,
    max_pages: int = 60,
    list_concurrency: int = 5,
    enrich_concurrency: int = 5,
    delay: float = 0.25,
    enrich: bool = True,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """Scrape Pivot-RP papers-invited (conference) listings.

    Parameters
    ----------
    subjects:
        Pivot subject codes to restrict scraping to. Defaults to all subjects.
    limit_subjects:
        Cap on the number of subjects to scrape (useful for testing).
    rows:
        Results per page (max 100).
    max_pages:
        Page cap per subject.
    list_concurrency:
        Maximum parallel fetches during the listing phase.
    enrich_concurrency:
        Maximum parallel fetches during the detail-page enrichment phase.
    delay:
        Seconds to sleep after each HTTP response.
    enrich:
        If True, fetch each conference's detail page to add ``location``,
        ``country``, ``scope``, ``website``, ``keywords``, ``organizers``,
        ``eligibility``, and ``timeline``.
    log:
        Optional callable for progress messages.

    Returns
    -------
    list[dict]
        Records with keys ``id, name, location, country, event_dates,
        deadlines, scope, website, keywords, organizers, eligibility,
        matched_subjects, url, timeline, scraped_at``.
    """
    _log = log or (lambda _: None)
    scraped_at = datetime.now(UTC).isoformat(timespec="seconds")
    _log("scrape_conferences: discovering subjects…")

    master = asyncio.run(
        _scrape_all(subjects, limit_subjects, rows, max_pages, list_concurrency, delay)
    )
    if not master:
        return []

    records: list[dict] = []
    for _cid, entry in master.items():
        rec = dict(entry["row"])
        rec["matched_subjects"] = "; ".join(sorted(entry["subjects"]))
        rec["scraped_at"] = scraped_at
        # Ensure all schema keys present
        for k in (
            "location",
            "country",
            "scope",
            "website",
            "keywords",
            "organizers",
            "eligibility",
            "language",
            "submission_guidelines",
            "timeline",
        ):
            rec.setdefault(k, "" if k != "timeline" else [])
        records.append(rec)
    records.sort(key=_sort_key)

    if enrich and records:
        _log(f"  enriching {len(records)} conferences…")
        asyncio.run(
            _enrich_records(records, concurrency=enrich_concurrency, delay=delay)
        )

    return records
