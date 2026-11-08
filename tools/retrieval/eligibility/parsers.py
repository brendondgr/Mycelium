"""Fellowship field parsers — vendored from the ProQuest tool's
``utils/Fellowships/models.py``.

Provides:
- Facet vocabularies (FIELD, CITIZENSHIP, STAGE, AWARD_TYPE, LIMITS, FACET_BUCKETS)
- ``bucket_categories`` — maps a Categories string/list into the facet groups
- ``derive_flags`` — boolean convenience flags from facets
- ``classify_award`` — title-keyword award classification
- ``parse_deadline`` — typed deadline dict from a raw deadline label
- ``parse_amount`` — typed amount dict from a raw amount string
- ``deadline_status`` — {status: open|closed|unknown, summary} helper

All parsers are provider-agnostic; the HTML walking lives in the Illinois adapter.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Facet vocabularies (mirror the Illinois left-sidebar facets exactly)
# ---------------------------------------------------------------------------

FIELD = [
    "Social Sciences", "Sciences/Engineering/Math", "Professional Programs",
    "Fine Arts", "Humanities",
]
CITIZENSHIP = [
    "US Citizens, Nationals, or Permanent Residents", "International Students",
]
STAGE = [
    "Master's", "Early Years of Doctoral Program", "Dissertation Research",
    "Dissertation Write-Up", "Postdoctoral/Post-graduate",
]
AWARD_TYPE = [
    "Fellowship/Grant", "Research/Study Abroad", "Short-Term Travel",
    "Foreign Language Training", "Research Internships",
]
LIMITS = [
    "University of Illinois Students", "Women", "Equity",
    "Annual stipend of at least $10,000",
]
FACET_BUCKETS = {
    "field": FIELD,
    "citizenship": CITIZENSHIP,
    "stage": STAGE,
    "award_type": AWARD_TYPE,
    "limits": LIMITS,
}


def _norm(s: str) -> str:
    """Lowercase, collapse whitespace, and normalize curly apostrophes."""
    return " ".join((s or "").replace("’", "'").split()).lower()


# token(normalized) -> (bucket, canonical string)
_CAT_LOOKUP = {
    _norm(opt): (bucket, opt)
    for bucket, opts in FACET_BUCKETS.items()
    for opt in opts
}


def empty_facets() -> dict:
    return {b: [] for b in FACET_BUCKETS} | {"other": []}


def bucket_categories(categories) -> dict:
    """Bucket a ``;``-separated Categories line (or list) into the facet groups.

    Unrecognized tokens are preserved under ``other`` so nothing is silently
    dropped and new site categories surface rather than vanish.
    """
    if isinstance(categories, str):
        tokens = categories.split(";")
    else:
        tokens = list(categories or [])
    facets = empty_facets()
    for tok in tokens:
        tok = " ".join((tok or "").replace("’", "'").split())
        if not tok:
            continue
        hit = _CAT_LOOKUP.get(_norm(tok))
        if hit:
            bucket, canon = hit
            if canon not in facets[bucket]:
                facets[bucket].append(canon)
        elif tok not in facets["other"]:
            facets["other"].append(tok)
    return facets


def facets_incomplete(facets: dict) -> bool:
    """True when no facet bucket carries a single value.

    The signature of a scrape miss. Every eligibility test is written as "does the
    award's list conflict with the applicant" and an empty list conflicts with
    nobody, so a record in this state passes every gate for every user. It is not
    the same thing as an award with no restrictions — that award still lists a
    field and a citizenship — so it is worth telling apart. ``other`` is ignored:
    an unrecognized category is not eligibility information.
    """
    return not any(facets.get(bucket) for bucket in FACET_BUCKETS)


def derive_flags(facets: dict) -> dict:
    """Boolean convenience flags derived from the facet buckets."""
    cit = facets.get("citizenship", [])
    stage = facets.get("stage", [])
    has_us = "US Citizens, Nationals, or Permanent Residents" in cit
    has_intl = "International Students" in cit
    doctoral_stages = {
        "Early Years of Doctoral Program",
        "Dissertation Research",
        "Dissertation Write-Up",
    }
    return {
        "requires_us_citizenship": has_us and not has_intl,
        "open_to_international": has_intl,
        "masters": "Master's" in stage,
        "doctoral": bool(doctoral_stages.intersection(stage)),
        "postdoc": "Postdoctoral/Post-graduate" in stage,
    }


# ---------------------------------------------------------------------------
# Award classification
# ---------------------------------------------------------------------------

_CLASS_KEYWORDS = [
    ("fellowship", "fellowship"),
    ("scholarship", "scholarship"),
    ("internship", "internship"),
    ("grant", "grant"),
    ("award", "award"),
    ("prize", "prize"),
]


def classify_award(title: str, facets: dict | None = None) -> str:
    """Return the award class inferred from the title (and optionally facets)."""
    t = _norm(title)
    for needle, label in _CLASS_KEYWORDS:
        if needle in t:
            return label
    if facets and "Research Internships" in facets.get("award_type", []):
        return "internship"
    return "fellowship"


# ---------------------------------------------------------------------------
# Deadline parsing
# ---------------------------------------------------------------------------

_MDY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")   # 04/30/2026
_MY = re.compile(r"\b(\d{1,2})/(\d{4})\b")               # 04/2027
_PREV = re.compile(r"previous\s+deadline\s*:?\s*", re.I)


def _iso_from_token(text: str) -> str:
    """First MM/DD/YYYY -> YYYY-MM-DD, else first MM/YYYY -> YYYY-MM, else ''."""
    m = _MDY.search(text)
    if m:
        mo, da, yr = (int(x) for x in m.groups())
        if 1 <= mo <= 12 and 1 <= da <= 31:
            return f"{yr:04d}-{mo:02d}-{da:02d}"
    m = _MY.search(text)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{yr:04d}-{mo:02d}"
    return ""


def parse_deadline(raw: str) -> dict:
    """Return ``{type, date, previous_date, raw}`` for a deadline label.

    ``date`` is ISO ``YYYY-MM-DD``, or ``YYYY-MM`` when the source gives no day,
    or ``""`` for continuous/rolling/varies deadlines.
    """
    raw = " ".join((raw or "").split())
    low = raw.lower()

    # Peel off a "( Previous deadline .. )" note first.
    previous_date, main = "", raw
    pm = _PREV.search(raw)
    if pm:
        tail = raw[pm.end():]
        previous_date = _iso_from_token(tail)
        cut = raw.rfind("(", 0, pm.start())
        main = raw[:cut] if cut != -1 else raw[:pm.start()]

    if "anticipated" in low:
        dtype = "anticipated"
    elif "continuous" in low:
        dtype = "continuous"
    elif "rolling" in low or "ongoing" in low:
        dtype = "rolling"
    elif "varies" in low:
        dtype = "varies"
    elif "suspended" in low:
        dtype = "suspended"
    elif _MDY.search(main) or _MY.search(main):
        dtype = "true"
    else:
        dtype = "unknown"

    dateless = ("continuous", "rolling", "varies", "suspended")
    date = "" if dtype in dateless else _iso_from_token(main)
    return {"type": dtype, "date": date, "previous_date": previous_date, "raw": raw}


# ---------------------------------------------------------------------------
# Amount / currency parsing
# ---------------------------------------------------------------------------

_CURRENCY_PATTERNS = [
    (re.compile(r"\bCAD\b|CAD\s*\$", re.I), "CAD"),
    (re.compile(r"\bNT\s*\$|\bNT\$|\bTWD\b", re.I), "TWD"),
    (re.compile(r"\bNIS\b|₪"), "ILS"),
    (re.compile(r"\bKRW\b|₩"), "KRW"),
    (re.compile(r"\bJPY\b"), "JPY"),
    (re.compile(r"\bEUR\b|€"), "EUR"),
    (re.compile(r"\bGBP\b|£"), "GBP"),
    (re.compile(r"\bAUD\b", re.I), "AUD"),
    (re.compile(r"\bUSD\b|US\s*\$", re.I), "USD"),
    (re.compile(r"¥"), "JPY"),
    (re.compile(r"\$"), "USD"),
]
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?")
_OPEN_MIN = re.compile(r"\d[\d,]*(?:\.\d+)?\+")
_MULT = {"k": 1_000, "m": 1_000_000}


def _detect_currency(raw: str) -> str:
    for pat, iso in _CURRENCY_PATTERNS:
        if pat.search(raw):
            return iso
    return ""


def _to_number(digits: str, suffix: str):
    val = float(digits.replace(",", ""))
    if suffix:
        val *= _MULT[suffix.lower()]
    return int(val) if val.is_integer() else val


def parse_amount(raw: str, note: str = "") -> dict:
    """Return ``{kind, currency, min, max, raw, note}`` for an award amount.

    ``kind`` is one of range | exact | up_to | varies | unknown.
    """
    raw = " ".join((raw or "").split())
    note = " ".join((note or "").split())
    low = raw.lower()
    currency = _detect_currency(raw)

    numbers = [_to_number(d, s) for d, s in _NUM.findall(raw)]

    if not numbers:
        kind, lo, hi = ("varies" if raw else "unknown"), None, None
    elif "up to" in low:
        kind, lo, hi = "up_to", None, max(numbers)
    elif len(numbers) >= 2:
        kind, lo, hi = "range", min(numbers), max(numbers)
    elif _OPEN_MIN.search(raw):
        kind, lo, hi = "range", numbers[0], None
    else:
        kind, lo, hi = "exact", numbers[0], numbers[0]

    return {"kind": kind, "currency": currency, "min": lo, "max": hi,
            "raw": raw, "note": note}


# ---------------------------------------------------------------------------
# Deadline status helper
# ---------------------------------------------------------------------------

def deadline_status(deadline: dict, today: str) -> dict:
    """Return ``{status: open|closed|unknown, summary}`` for a deadline dict.

    - rolling / continuous / anticipated => open (still accepting)
    - suspended => closed
    - true-dated in the past (date < today) => closed
    - true-dated in the future / YYYY-MM in the future => open
    - everything else (unknown / no date) => unknown
    """
    dtype = (deadline or {}).get("type", "unknown")
    date = (deadline or {}).get("date", "")

    open_types = ("rolling", "continuous", "anticipated", "varies")
    if dtype in open_types:
        return {"status": "open", "summary": dtype.capitalize()}

    if dtype == "suspended":
        return {
            "status": "closed",
            "summary": "Award suspended / not currently accepting",
        }

    if dtype == "true" and date:
        # Coerce YYYY-MM to YYYY-MM-01 for comparison so month-only dates aren't
        # incorrectly treated as closed just because today is past the 1st.
        compare_date = date if len(date) == 10 else date + "-01"
        if compare_date < today:
            return {"status": "closed", "summary": f"Deadline passed ({date})"}
        return {"status": "open", "summary": f"Deadline {date}"}

    # anticipated with no date, unknown, etc.
    return {"status": "unknown", "summary": "Deadline unknown"}
