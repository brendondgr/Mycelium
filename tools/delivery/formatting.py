"""Display-time text formatting shared across content serializers.

``normalize_amount`` lives here, not in a scrape package, because it is not a
scrape-time transform at all: both
:class:`~tools.delivery.serializers.GrantSerializer` and
:class:`~tools.delivery.serializers.SearchResultSerializer` call it **at read
time**, on every request, to distill whatever a source's raw amount field
happens to hold into something short enough to show on a card. Living inside a
provider-specific scrape package would make that read-time dependency
invisible; removing that provider could delete it and 500 every content
endpoint without touching a single content-app file. It has no
models/DB/network dependency, so it is trivially unit-testable on its own.
"""

from __future__ import annotations

import re

# A dollar figure with an optional scale word, e.g. "$450,000", "$1.5 million",
# "$800k". The scale is bounded by ``\b`` so prose like "$3 basis points" is read
# as "$3", not "$3 billion".
_CURRENCY_VALUE_RE = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s*(million|billion|thousand|mm|bn|k|m|b)\b)?",
    re.I,
)
_SCALES = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "mm": 1_000_000,
    "m": 1_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "b": 1_000_000_000,
}
# An amount longer than this is treated as prose to distill, not a tidy value.
_AMOUNT_MAX_LEN = 48


def _amount_value(num: str, scale: str | None) -> float | None:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    if scale:
        value *= _SCALES.get(scale.lower(), 1)
    return value


def _fmt_amount(value: float) -> str:
    return f"${int(round(value)):,}"


def normalize_amount(text: str) -> str:
    """Distill a scraped funding 'amount' to a concise value or range.

    A source's Amount field is usually a tidy figure ("$450,000"), but some
    grants drop a whole budget paragraph there (e.g. "...not to exceed $450,000
    in direct costs per year for UG3 and $800,000 for UH3 phases..."). A short,
    tidy value passes through unchanged; a long prose value is reduced to the
    dollar figures it names — a single amount, or a "$low–$high" range — and
    dropped when it names none, so the UI and embeddings never carry a
    paragraph. Idempotent.
    """
    text = " ".join((text or "").split())
    if not text or len(text) <= _AMOUNT_MAX_LEN:
        return text
    values = [
        v
        for m in _CURRENCY_VALUE_RE.finditer(text)
        if (v := _amount_value(m.group(1), m.group(2))) is not None
    ]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    return _fmt_amount(lo) if lo == hi else f"{_fmt_amount(lo)}–{_fmt_amount(hi)}"
