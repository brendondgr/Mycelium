"""Frequency-rank a normalized draft's term lists.

The brief assigns aggregation to one place because it is the *same* logic
regardless of source: collapse the per-work term occurrences a normalizer
gathered into a frequency-ranked, de-duplicated distribution. It runs on the
normalized :class:`AuthorProfileDraft`, never on a source's raw payload.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace

from .drafts import AuthorProfileDraft

AREA_CAP = 12
KEYWORD_CAP = 20
METHOD_CAP = 12
COAUTHOR_CAP = 25


def rank_terms(terms: Iterable[str], *, cap: int | None = None) -> list[str]:
    """Most-frequent-first, case-folded, whitespace-normalized, order-stable.

    Ties keep first-seen order (``Counter.most_common`` preserves insertion
    order for equal counts), so the result is deterministic for a fixed input.
    """

    counter: Counter[str] = Counter()
    display: dict[str, str] = {}
    for raw in terms:
        text = " ".join(str(raw).split())
        if not text:
            continue
        key = text.casefold()
        counter[key] += 1
        display.setdefault(key, text)
    ranked = [display[key] for key, _ in counter.most_common()]
    return ranked[:cap] if cap is not None else ranked


def aggregate(
    draft: AuthorProfileDraft,
    *,
    area_cap: int = AREA_CAP,
    keyword_cap: int = KEYWORD_CAP,
    method_cap: int = METHOD_CAP,
    coauthor_cap: int = COAUTHOR_CAP,
) -> AuthorProfileDraft:
    """Return a copy of ``draft`` with its term lists frequency-ranked + capped."""

    return replace(
        draft,
        areas=rank_terms(draft.areas, cap=area_cap),
        keywords=rank_terms(draft.keywords, cap=keyword_cap),
        methods=rank_terms(draft.methods, cap=method_cap),
        coauthors=rank_terms(draft.coauthors, cap=coauthor_cap),
    )
