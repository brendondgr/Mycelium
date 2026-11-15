"""EXP-2026-11-018: the experiment's own normaliser for dates, amounts,
percentages and text. Standard library only. Deliberately independent of
``tools/agent/verify.py`` (the checker under test in EXP-2026-11-020).

Frozen with the questions before any answer was generated.
"""

from __future__ import annotations

import re
import unicodedata

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"


def fold(text: str) -> str:
    """Lower case, no diacritics, every run of non-alphanumerics one space,
    padded with a space on each side so ``" word "`` matches whole words."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return f" {text.strip()} "


def has_phrase(answer: str, phrase: str) -> bool:
    return fold(phrase) in fold(answer)


# --- dates --------------------------------------------------------------------

def dates(text: str) -> set[tuple]:
    """Every full calendar day stated in ``text`` as ``(year or None, month, day)``.
    A month without a day ("March 2027") is not a date here."""
    t = str(text or "").lower()
    out: set[tuple] = set()
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        out.add((int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t):  # US m/d/y, as the corpus writes it
        out.add((int(m[3]), int(m[1]), int(m[2])))
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}(?:,?\s+(\d{{4}}))?", t):
        out.add((int(m[3]) if m[3] else None, MONTHS[m[2]], int(m[1])))
    for m in re.finditer(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", t):
        out.add((int(m[3]) if m[3] else None, MONTHS[m[1]], int(m[2])))
    return {d for d in out if 1 <= d[1] <= 12 and 1 <= d[2] <= 31}


def date_matches(found: tuple, gold: str) -> bool:
    y, mo, d = (int(x) for x in gold.split("-"))
    return found[1] == mo and found[2] == d and (found[0] is None or found[0] == y)


# --- amounts ------------------------------------------------------------------

_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "millions": 1e6,
          "bn": 1e9, "b": 1e9, "billion": 1e9}
_CUR_BEFORE = r"(€|\$|£|eur\b|usd\b|us\$|gbp\b)"
_CUR_AFTER = r"(euros?|eur|dollars?|usd|pounds?|gbp)\b"
_NUM = r"(\d{1,3}(?:[,   ]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_TOKEN = re.compile(
    rf"(?P<cur>{_CUR_BEFORE}\s?)?(?P<num>{_NUM})\s?(?P<scale>thousand|millions?|billion|mn|bn|k|m|b)?\b\s?(?P<cur2>{_CUR_AFTER})?",
    re.I,
)
_JOIN = re.compile(r"^\s*(–|-|—|to|and|up to)\s*$", re.I)


def amounts(text: str) -> set[float]:
    """Every money amount stated in ``text``. A number counts when it carries a
    currency mark, or is joined by a dash / "to" / "and" to one that does; a
    scale word ("million", "M", "k") multiplies it, and the first number of a
    range ("€3–15 million") takes the second's scale when it has none."""
    t = str(text or "")
    toks = []
    for m in _TOKEN.finditer(t):
        num = float(re.sub(r"[,   ]", "", m["num"]))
        scale = (m["scale"] or "").lower()
        toks.append({
            "start": m.start(), "end": m.end(), "num": num,
            "scale": _SCALE.get(scale) if scale else None,
            "cur": bool(m["cur"] or m["cur2"]),
        })
    for a, b in zip(toks, toks[1:]):
        between = t[a["end"]:b["start"]]
        if _JOIN.match(between) or between.strip() in ("–", "-", "—"):
            if a["scale"] is None and b["scale"] is not None:
                a["scale"] = b["scale"]
            if a["cur"] and not b["cur"]:
                b["cur"] = True
            if b["cur"] and not a["cur"]:
                a["cur"] = True
    return {round(x["num"] * (x["scale"] or 1), 2) for x in toks if x["cur"]}


def amount_matches(found: float, gold: float) -> bool:
    """Equal within 1% (a rounded "€8.9M" for €8,925,000 matches)."""
    return gold > 0 and abs(found - gold) / gold <= 0.01


# --- percentages --------------------------------------------------------------

def percents(text: str) -> set[float]:
    return {float(m[1]) for m in re.finditer(r"(\d+(?:\.\d+)?)\s?(%|percent\b|per cent\b)", str(text or ""), re.I)}


# --- declining ----------------------------------------------------------------

DECLINE = re.compile(
    r"(\bnot\b|n't\b|n’t\b|\bno\b|\bcannot\b|\bunable\b|\bnothing\b|\bnone\b|\bneither\b)"
    r"[^.!?\n]{0,80}?"
    r"\b(stor|record|list|availab|includ|provid|giv|stat|specif|mention|show|say|find|found|"
    r"see|know|contain|appear|have|has|access|track|hold|publish|disclos)",
    re.I,
)


def declines(text: str) -> bool:
    return bool(DECLINE.search(str(text or "")))
