"""What changed, and when.

The store upserts in place, so a deadline extension, a budget change or a
reissue left no trace — yet the sources hand us the diff directly. Grants.gov
publishes ``synopsisModifiedFields`` on 374 records (31%), a literal list of
what the agency changed, and ``originalDueDate`` on 755 (63%), the deadline
before it was extended. Both were discarded.

``Store._upsert_one`` already computes exactly which columns differ, because it
has to in order to decide whether to write at all. Recording that comparison
instead of throwing it away is the whole mechanism, and it is what turns a daily
run from a list into a monitor: "what is new since Monday", "did anything I was
tracking move", "was this deadline extended".

Only fields a *reader* would act on are tracked. Recording that a raw payload's
byte order shifted would bury the deadline change that matters in noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Columns whose change is worth telling someone about, with the phrasing to use.
#: Everything else — raw payloads, bookkeeping, derived facets — changes for
#: reasons that are about us rather than about the opportunity.
TRACKED_FIELDS: dict[str, str] = {
    "close_date": "deadline",
    "additional_due_dates": "due dates",
    "intent_date": "letter-of-intent deadline",
    "open_date": "opening date",
    "expiration_date": "expiration",
    "status": "status",
    "award_ceiling": "award ceiling",
    "award_floor": "award floor",
    "total_program_funding": "programme funding",
    "expected_awards": "expected awards",
    "title": "title",
    "eligibility": "eligibility",
    "applicant_types": "eligible applicants",
    "cost_sharing": "cost sharing",
}

#: A description edit is worth knowing about but its text is far too long to
#: store per revision, so the change is recorded without the before and after.
SUMMARY_ONLY = frozenset({"description"})

#: How a change reads when the value moved in a direction that matters.
_DEADLINE_FIELDS = frozenset({"close_date", "intent_date", "expiration_date"})


@dataclass
class Change:
    stable_key: str
    field: str
    label: str
    before: str
    after: str
    at: str

    @property
    def direction(self) -> str:
        """"extended", "brought forward", or "" — only meaningful for dates.

        Worth distinguishing because they are opposite news: an extension is
        breathing room and a date brought forward is an emergency.
        """
        if self.field not in _DEADLINE_FIELDS or not (self.before and self.after):
            return ""
        if self.after > self.before:
            return "extended"
        if self.after < self.before:
            return "brought forward"
        return ""

    def describe(self) -> str:
        if self.field in SUMMARY_ONLY:
            return f"{self.label} rewritten"
        direction = f" ({self.direction})" if self.direction else ""
        before = self.before or "—"
        after = self.after or "—"
        return f"{self.label}: {before} → {after}{direction}"


#: Fields whose values are money and should read as money.
_MONEY_FIELDS = frozenset(
    {"award_ceiling", "award_floor", "total_program_funding"}
)


def _money(value: float) -> str:
    if abs(value) >= 1e9:
        return f"{value / 1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f}M"
    if abs(value) >= 1e3:
        return f"{value / 1e3:,.0f}K"
    return f"{value:,.0f}"


def _render(value: object, field: str = "") -> str:
    """A stored value as short readable text.

    JSON lists are unwrapped and amounts abbreviated, because the point of this
    table is a line someone reads in passing. "20000000.0 → 40000000.0" makes a
    reader count digits; "20.0M → 40.0M" does not.
    """
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        return ", ".join(str(item) for item in parsed)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if field in _MONEY_FIELDS and isinstance(value, int | float):
        return _money(float(value))
    return str(value)


def diff_rows(stable_key: str, before: dict, after: dict, at: str) -> list[Change]:
    """The reader-visible differences between a stored row and its replacement."""
    changes: list[Change] = []
    for field, label in TRACKED_FIELDS.items():
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        changes.append(
            Change(stable_key, field, label, _render(old, field), _render(new, field), at)
        )
    for field in SUMMARY_ONLY:
        if before.get(field) != after.get(field):
            # Recorded without the text: a revision history of 5 KB descriptions
            # would dwarf the store it describes.
            changes.append(Change(stable_key, field, "description", "", "", at))
    return changes
