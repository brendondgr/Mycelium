"""Word-format dates -> ISO ``YYYY-MM-DD`` + de-dup for scraped Pivot data.

Vendored (pure parts) from the ProQuest tool's ``utils/ProQuest/normalize.py`` —
the single source of truth for Pivot date parsing. No models / DB / network, so it
is trivially unit-testable and shared by both the collect and match sides.

``normalize_amount`` used to live here too, but it is not Pivot-shaped — it is
called at *read* time by the content serializers, not at scrape time — so it now
lives at :mod:`apps.content.formatting`. It is re-imported below because this
module's own :func:`~apps.scraper.pivot.records.build_pivot_item` still calls it
locally; importing it here (rather than editing every internal caller) keeps this
module's public surface unchanged while the canonical implementation lives with
its real read-time consumers.
"""

from __future__ import annotations

import re
from datetime import datetime

# Layering inversion, left deliberately: this points the dependency arrow from
# `scraper` into `content`, backwards from the rest of the codebase. Not fixed
# here because `apps/scraper/pivot/` is deleted wholesale in Phase 6 of
# docs/plans/open-opportunity-collector.md, which removes this import along
# with the rest of the file — refactoring it now would be churn on a module
# with days to live. Do not "fix" this without re-reading that plan.
from apps.content.formatting import normalize_amount  # noqa: F401 - re-exported

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A date token in prose, e.g. "01 Apr 2027" or "1 April 2027".
WORD_DATE_RE = re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b")
_FORMATS = ("%d %b %Y", "%d %B %Y")


def normalize_date(s: str) -> str:
    """Return an ISO ``YYYY-MM-DD`` date, or "" if unparseable.

    Idempotent: an already-ISO string is returned unchanged.
    """
    s = (s or "").strip()
    if not s:
        return ""
    if ISO_RE.match(s):
        return s
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _iso_or_original(token: str) -> str:
    return normalize_date(token) or token


def _timeline_line(entry: dict) -> str:
    date, desc = entry.get("date", ""), entry.get("description", "")
    return f"{date} ({desc})" if desc else date


def normalize_record(rec: dict, area: str) -> dict:
    """Rewrite a record's dates to ISO in place (and return it)."""
    if area == "conferences":
        timeline = rec.get("timeline") or []
        for entry in timeline:
            entry["date"] = _iso_or_original(entry.get("date", ""))
        deadlines = [
            _timeline_line(e)
            for e in timeline
            if re.search(r"deadline", e.get("description", ""), re.I)
        ]
        _event_re = re.compile(r"(start|end)\s+date\s+of\s+event", re.I)
        events = [
            _timeline_line(e)
            for e in timeline
            if _event_re.search(e.get("description", ""))
        ]
        if timeline:
            rec["deadlines"] = "; ".join(deadlines)
            rec["event_dates"] = "; ".join(events)
        else:
            for key in ("deadlines", "event_dates"):
                if rec.get(key):
                    rec[key] = WORD_DATE_RE.sub(
                        lambda m: _iso_or_original(m.group(1)), rec[key]
                    )
    elif area == "grants":
        if rec.get("deadline_date"):
            rec["deadline_date"] = _iso_or_original(rec["deadline_date"])
        if rec.get("deadline"):
            rec["deadline"] = WORD_DATE_RE.sub(
                lambda m: _iso_or_original(m.group(1)), rec["deadline"]
            )
    return rec


# Per-area field listing which searches surfaced a record (merged on de-dup).
_TAG_FIELD = {"conferences": "matched_subjects", "grants": "matched_topics"}


def _merge_tags(a: str, b: str) -> str:
    parts: list[str] = []
    for s in (a or "", b or ""):
        parts.extend(p.strip() for p in s.split(";") if p.strip())
    return "; ".join(sorted(dict.fromkeys(parts)))


def dedupe(records, area: str) -> list[dict]:
    """Collapse records sharing an ``id``, merging their multi-source tags."""
    tag = _TAG_FIELD.get(area)
    out: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("id")
        if rid in out:
            if tag:
                out[rid][tag] = _merge_tags(out[rid].get(tag, ""), rec.get(tag, ""))
        else:
            out[rid] = rec
    return list(out.values())


def normalize_records(records, area: str) -> list[dict]:
    """Normalize dates + de-duplicate a list of records (returns a new list)."""
    deduped = dedupe(records, area)
    for rec in deduped:
        normalize_record(rec, area)
    return deduped
