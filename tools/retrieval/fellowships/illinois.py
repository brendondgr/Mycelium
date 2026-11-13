"""University of Illinois Graduate College Fellowship Finder adapter.

Site: https://fellowship-finder.grad.illinois.edu

Two very different surfaces:

* **Listing** is plain server-rendered HTML — one page, every fellowship as a
  ``<tr>`` with a ``/Fellowship/<id>`` link, a short blurb, a concise amount,
  and a deadline label. A single HTTP GET gets them all, so ``fetch_listing``
  uses an APIRequestContext, not a browser.
* **Detail** is a **Blazor Server** app: the raw HTTP response is only a
  "Loading…" shell, so ``render_detail`` drives a real Chromium page and waits
  for the interactive circuit to render the content.

Pure parsers (``parse_listing`` / ``parse_detail`` / ``build_record``) are kept
separate from the async fetch/render so they're unit-testable against saved HTML.

``bs4`` and ``playwright`` are optional extras — this module imports cleanly when
they are absent; the imports happen inside functions (``fetch_listing``,
``render_detail``) so the package loads without the optional ``fellowships``
extra.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from tools.retrieval.eligibility.parsers import (
    bucket_categories,
    classify_award,
    derive_flags,
    parse_amount,
    parse_deadline,
)

SOURCE = "illinois-fellowship-finder"
BASE = "https://fellowship-finder.grad.illinois.edu"
LISTING_URL = f"{BASE}/SearchResult/selectedValues=&SearchBy="

# Browser args for Blazor pages (mirrors common.py in the tool).
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
CONTEXT_KWARGS = {
    "viewport": {"width": 1440, "height": 900},
    "locale": "en-US",
}


def detail_url(fid: str) -> str:
    return f"{BASE}/SearchResult/Fellowship/{fid}"


def _clean_text(text: str) -> str:
    """Collapse all whitespace runs (incl. newlines) to single spaces."""
    return " ".join((text or "").split())


def _sentence_split(text: str) -> list[str]:
    """Split prose into trimmed sentence-ish chunks (for list fallbacks)."""
    text = _clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Listing parsing
# ---------------------------------------------------------------------------


def parse_listing(html: str) -> list[dict]:
    """Every result row -> ``{id, title, blurb, amount_raw, deadline_raw, source_url}``.

    De-duplicated by fellowship id. bs4 is imported lazily inside this function.
    """
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.select('td.fellowship-name a[href*="/Fellowship/"]'):
        fid = a.get("href", "").rstrip("/").split("/")[-1]
        if not fid.isdigit() or fid in seen:
            continue
        seen.add(fid)
        tr = a.find_parent("tr")
        blurb = tr.select_one("td.fellowship-name span.smalltext") if tr else None
        amount = tr.select_one("td.fellowship-amount") if tr else None
        deadline = tr.select_one("td.fellowship-deadline") if tr else None
        rows.append({
            "id": fid,
            "title": _clean_text(a.get_text()),
            "blurb": _clean_text(blurb.get_text()) if blurb else "",
            "amount_raw": _clean_text(amount.get_text()) if amount else "",
            "deadline_raw": _clean_text(deadline.get_text()) if deadline else "",
            "source_url": detail_url(fid),
        })
    return rows


# ---------------------------------------------------------------------------
# Detail parsing
# ---------------------------------------------------------------------------

_HEADERS = {
    "eligibility": "eligibility",
    "award amount": "award",
    "contact": "contact",
    "url": "url",
}


def _section_header(el):
    """If ``el`` starts a labelled section, return its key, else None."""
    if not getattr(el, "name", None):
        return None
    strong = el.find("strong")
    if not strong:
        return None
    lbl = _clean_text(strong.get_text()).rstrip(":").lower()
    return _HEADERS.get(lbl)


def _strip_label(text: str, label: str) -> str:
    return re.sub(rf"^\s*{re.escape(label)}\s*:?\s*", "", text, flags=re.I).strip()


def parse_detail(html: str) -> dict:
    """Pull the structured detail fields out of a rendered detail page.

    bs4 is imported lazily inside this function.
    """
    from bs4 import BeautifulSoup  # lazy

    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main.main-content") or soup.body or soup
    out = {
        "title": "", "deadline_raw": "", "note": "", "description": "",
        "eligibility": [], "award_note": "", "external_url": "",
        "contact_email": "", "categories": "",
    }
    if main is None:
        return out

    h1 = main.select_one("h1")
    out["title"] = _clean_text(h1.get_text()) if h1 else ""

    for p in main.find_all("p"):
        t = _clean_text(p.get_text())
        if t.lower().startswith("deadline"):
            out["deadline_raw"] = _strip_label(t, "Deadline")
            break

    note = main.select_one("p.logistics")
    if note:
        out["note"] = re.sub(r"^!\s*", "", _clean_text(note.get_text())).strip()

    desc = main.select_one("div.description")
    if desc is not None:
        sections: dict[str, list] = {
            "description": [], "eligibility": [], "award": [],
            "contact": [], "url": [],
        }
        current = "description"
        for child in desc.children:
            if not getattr(child, "name", None):
                continue
            header = _section_header(child)
            if header:
                current = header
            sections[current].append(child)

        out["description"] = _clean_text(
            " ".join(el.get_text(" ") for el in sections["description"])
        )

        # Eligibility: prefer explicit <li> items; else sentence-split the prose.
        items: list[str] = []
        for el in sections["eligibility"]:
            items += [_clean_text(li.get_text(" ")) for li in el.select("li")]
        items = [i for i in items if i]
        if not items and sections["eligibility"]:
            text = _clean_text(
                " ".join(el.get_text(" ") for el in sections["eligibility"])
            )
            text = _strip_label(text, "Eligibility")
            text = re.sub(r"^Applicants?(\s+must)?\s*:?\s*", "", text, flags=re.I)
            items = _sentence_split(text)
        out["eligibility"] = items

        award = _clean_text(" ".join(el.get_text(" ") for el in sections["award"]))
        out["award_note"] = _strip_label(award, "Award amount")

        contact = _clean_text(" ".join(el.get_text(" ") for el in sections["contact"]))
        _EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
        for el in sections["contact"]:
            mail = el.select_one('a[href^="mailto:"]')
            if mail:
                text = _clean_text(mail.get_text())
                href = mail.get("href", "")[len("mailto:"):].strip()
                out["contact_email"] = text if _EMAIL.fullmatch(text) else href
                break
        if not out["contact_email"]:
            m = _EMAIL.search(contact)
            if m:
                out["contact_email"] = m.group(0)

        for el in sections["url"]:
            link = el.select_one("a[href]")
            if link and link.get("href", "").startswith("http"):
                out["external_url"] = link["href"].strip()
                break
        if not out["external_url"]:
            url_text = _strip_label(
                _clean_text(" ".join(el.get_text(" ") for el in sections["url"])), "URL"
            )
            if url_text.startswith("http"):
                out["external_url"] = url_text.split()[0]

    comments = main.select_one("p.comments")
    if comments:
        out["categories"] = _strip_label(
            _clean_text(comments.get_text(" ")), "Categories"
        )
    return out


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------


def build_record(row: dict, detail: dict, scraped_at: str | None = None) -> dict:
    """Merge a listing row + parsed detail into one structured record."""
    scraped_at = scraped_at or datetime.now(UTC).isoformat(timespec="seconds")
    detail = detail or {}
    title = detail.get("title") or row.get("title", "")
    facets = bucket_categories(detail.get("categories", ""))
    deadline_raw = detail.get("deadline_raw") or row.get("deadline_raw", "")
    return {
        "id": row["id"],
        "source": SOURCE,
        "source_url": row.get("source_url") or detail_url(row["id"]),
        "external_url": detail.get("external_url", ""),
        "title": title,
        "blurb": row.get("blurb", ""),
        "description": detail.get("description", "") or row.get("blurb", ""),
        "award_class": classify_award(title, facets),
        "deadline": parse_deadline(deadline_raw),
        "award_amount": parse_amount(
            row.get("amount_raw", ""), detail.get("award_note", "")
        ),
        "eligibility": detail.get("eligibility", []),
        "facets": facets,
        "flags": derive_flags(facets),
        "note": detail.get("note", ""),
        "contact_email": detail.get("contact_email", ""),
        "scraped_at": scraped_at,
    }


# ---------------------------------------------------------------------------
# Async fetch / render
# ---------------------------------------------------------------------------


async def fetch_listing(request) -> str:
    """GET the (server-rendered) listing page via a Playwright APIRequestContext.

    playwright is imported lazily at call sites; this coroutine is only invoked
    from within an already-running async_playwright context.
    """
    resp = await request.get(LISTING_URL, timeout=60000)
    if resp.status != 200:
        raise RuntimeError(f"listing HTTP {resp.status}")
    return await resp.text()


async def render_detail(page, fid: str, timeout: int = 45000) -> str:
    """Render a Blazor detail page and return its HTML once content appears.

    Retries once if the interactive circuit throws its "An error has occurred"
    banner instead of rendering. Returns "" if it never renders.

    playwright is imported lazily at call sites; this coroutine is only invoked
    from within an already-running async_playwright context.
    """
    url = detail_url(fid)
    html = ""
    for attempt in range(2):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                await page.wait_for_selector(
                    "main.main-content div.description, main.main-content p.comments",
                    timeout=20000,
                )
            except Exception:
                pass
            html = await page.content()
        except Exception:
            html = ""
        if html and "An error has occurred" not in html and "<h1" in html:
            return html
        if attempt == 0:
            try:
                await page.wait_for_timeout(1000)
            except Exception:
                pass
    return html or ""
