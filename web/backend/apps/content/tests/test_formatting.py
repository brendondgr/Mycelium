"""``apps.content.formatting.normalize_amount`` — display-time amount distillation.

This file exists because the function's only prior coverage
(``test_normalize_amount_distills_prose`` in the now-deleted
``apps/scraper/tests/test_pivot_ingest.py``) was deleted along with the rest of
the Pivot package during the open-collector migration, even though
``normalize_amount`` itself was lifted out of Pivot and into
``apps.content.formatting`` first — precisely so it would keep running. The
function is called at **read time** from both ``GrantSerializer`` and
``SearchResultSerializer`` on every grant card on every feed
(``apps/content/serializers.py``), so a regression here is not a scrape-time
inconvenience: it is a live 500 or a silently mangled amount on production
traffic. ``formatting.py``'s own module docstring says as much. Recovering
these cases, unchanged, closes that gap.
"""

import pytest

from apps.content.formatting import normalize_amount

# A grant that put a whole budget paragraph in its Amount field (the real NIH
# Common Fund UG3/UH3 case) — the amount distiller must reduce this to a range.
_BUDGET_PROSE = (
    "The NIH Common Fund intends to commit funds for approximately 6-8 UG3/UH3 "
    "awards. Applicants should request a budget appropriate for the proposed "
    "scope of work, not to exceed $450,000 in direct costs per year for UG3 and "
    "$800,000 for UH3 phases. The total project period may not exceed six years."
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$450,000", "$450,000"),  # tidy value: unchanged
        ("Upper: $70,000 USD", "Upper: $70,000 USD"),  # short prose: kept
        ("", ""),
        (_BUDGET_PROSE, "$450,000–$800,000"),  # paragraph -> range
        ("$450,000–$800,000", "$450,000–$800,000"),  # idempotent
        ("$1.5 million", "$1.5 million"),  # short, unchanged
        (  # long prose, one figure -> single amount
            "Applicants may request up to $2,500,000 in total costs over the "
            "full multi-year project period, subject to available funds.",
            "$2,500,000",
        ),
        (  # long prose with a scale word
            "The foundation expects to make several awards and anticipates "
            "committing roughly $3.5 million per awardee across the program.",
            "$3,500,000",
        ),
        (  # long prose naming no dollar figure -> dropped
            "Budget guidance will be provided to invited applicants after the "
            "preliminary review stage is complete; see the full solicitation.",
            "",
        ),
    ],
)
def test_normalize_amount_distills_prose(raw: str, expected: str) -> None:
    assert normalize_amount(raw) == expected
