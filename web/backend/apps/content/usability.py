"""Can we use this? The facts an announcement and a feed card show about an
opportunity, read from its record by code.

Every check returns a :class:`Check`: a status, a short label a reader sees, and the
record field it read, so each posted fact traces to a field (plan D4). The four
statuses mean:

* ``ok`` — the record says yes.
* ``warn`` — usable, but something needs a person's attention.
* ``block`` — not usable as it stands. An announcement stops here and the item is
  shown under "Mylo held back" with this label as the reason.
* ``unknown`` — the record does not say. **A missing field is never ``ok``.**

The checks never touch the database: callers pass the facts about the reader
(institution type, country, deadline buffer, award preference, eligibility counts,
who suits it) as a :class:`Reader`, which keeps them pure and testable on real
records. The ``reader_for_*`` builders at the bottom are the only part that reads
models (an org profile and the timeline settings). No percentage, score or name of
an ineligible person ever comes out of here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from apps.content.deadlines_projection import deadline_specs_for
from apps.content.models import ContentDeadline, ContentItem, SavedOpportunity

OK, WARN, BLOCK, UNKNOWN = "ok", "warn", "block", "unknown"
NO_SUBMISSION_DEADLINE = "No submission deadline published yet"
_RANK = {BLOCK: 3, WARN: 2, UNKNOWN: 1, OK: 0}


@dataclass(frozen=True)
class Check:
    key: str
    status: str
    label: str
    field: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Reader:
    """Who would act on the item. Every field optional; blank means "not said"."""

    institution_type: str = ""  # accounts.InstitutionType value
    country: str = ""  # ISO 3166-1 alpha-2
    buffer_days: int | None = None
    min_award: float | None = None
    #: ``(may_be_eligible, people_checked)`` for a fellowship, or None.
    fellowship_counts: tuple[int, int] | None = None
    #: Display names of the people Mylo thinks should look, or None if not known.
    suited: tuple[str, ...] | None = None


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
def assess(item: ContentItem, reader: Reader, today: date) -> list[Check]:
    """Every check that applies to ``item`` for ``reader``, in display order."""
    meta = item.metadata or {}
    checks = [_open_check(item.type, meta)]
    due, due_check = _deadline_check(item, today)
    checks.append(due_check)
    if due is not None and reader.buffer_days is not None:
        checks.append(_feasible_check(due, reader.buffer_days, today))
    if item.type == ContentItem.Type.GRANT:
        if reader.institution_type:
            checks.append(_applicant_check(meta, reader.institution_type))
        if reader.country:
            checks.append(_country_check(meta, reader.country))
        if reader.min_award is not None:
            checks.append(_award_check(meta, reader.min_award))
    if item.type == ContentItem.Type.FELLOWSHIP and reader.fellowship_counts:
        checks.append(_fellowship_check(*reader.fellowship_counts))
    if reader.suited is not None:
        checks.append(_team_check(reader.suited))
    return checks


def verdict(checks: Iterable[Check]) -> str:
    """The worst status among ``checks``: what the item amounts to overall."""
    worst = OK
    for check in checks:
        if _RANK[check.status] > _RANK[worst]:
            worst = check.status
    return worst


def blocking(checks: Iterable[Check]) -> Check | None:
    """The first check that holds the item back, if any."""
    return next((c for c in checks if c.status == BLOCK), None)


def summary(checks: list[Check]) -> dict:
    """The serializer shape: ``{"verdict", "checks": [...]}``."""
    return {"verdict": verdict(checks), "checks": [c.as_dict() for c in checks]}


# --------------------------------------------------------------------------- #
# Open, and the next round
# --------------------------------------------------------------------------- #
def _open_check(item_type: str, meta: dict) -> Check:
    status = (meta.get("status") or "").strip().lower()
    if status == "open":
        return Check("open", OK, "Open", "status")
    if status == "closed":
        return Check("open", BLOCK, "Closed", "status")
    if status in ("forecasted", "forecast"):
        return Check("open", WARN, "Forecast: not open yet", "status")
    if item_type == ContentItem.Type.CONFERENCE:
        # Conferences carry no open/closed status; the deadline check decides.
        return Check("open", OK, "Accepting submissions", "deadlines")
    return Check("open", UNKNOWN, "Status not listed", "status")


def _deadline_check(item: ContentItem, today: date) -> tuple[date | None, Check]:
    """``(next due date or None, check)`` from the deadline projection."""
    specs = deadline_specs_for(item, today.isoformat())
    if item.type == ContentItem.Type.CONFERENCE:
        specs = [s for s in specs if s.kind != SavedOpportunity.DeadlineKind.EVENT]
    dated = sorted(
        (s for s in specs if s.due_date is not None and s.due_date >= today),
        key=lambda s: (s.due_date, s.round_key),
    )
    if dated:
        spec = dated[0]
        when = _day(spec.due_date)
        days = (spec.due_date - today).days
        label = f"{spec.label}: {when} ({_days(days)})"
        if spec.confidence == ContentDeadline.Confidence.ANTICIPATED:
            check = Check(
                "deadline", WARN, f"Expected {when}, not confirmed", "deadline_date"
            )
            return spec.due_date, check
        return spec.due_date, Check("deadline", OK, label, "deadline_date")
    if any(s.due_date is not None for s in specs) or _had_dated_round(item):
        return None, Check("deadline", BLOCK, "The last deadline has passed",
                           "deadline_date")
    if item.type == ContentItem.Type.CONFERENCE:
        return None, Check("deadline", BLOCK, NO_SUBMISSION_DEADLINE, "deadlines")
    return None, Check("deadline", UNKNOWN, "No deadline listed", "deadline_date")


def _had_dated_round(item: ContentItem) -> bool:
    """A conference's projection drops past rounds, so ask the record itself."""
    if item.type != ContentItem.Type.CONFERENCE:
        return False
    entries = (item.metadata or {}).get("deadlines_structured") or []
    return any(isinstance(e, dict) and e.get("instant") for e in entries)


def _feasible_check(due: date, buffer_days: int, today: date) -> Check:
    days = (due - today).days
    if days < buffer_days:
        return Check(
            "feasible",
            BLOCK,
            f"Closes in {_days(days)}, inside your {buffer_days}-day buffer",
            "deadline_date",
        )
    return Check("feasible", OK, f"{_days(days)} left; buffer {buffer_days}",
                 "deadline_date")


# --------------------------------------------------------------------------- #
# Who may apply
# --------------------------------------------------------------------------- #
#: grants.gov applicant-type wording → the institution types it admits.
_APPLICANT_TYPES: tuple[tuple[str, frozenset[str]], ...] = (
    ("unrestricted", frozenset({"higher_ed", "nonprofit", "government", "company"})),
    ("institutions of higher education", frozenset({"higher_ed"})),
    ("nonprofits", frozenset({"nonprofit"})),
    ("small businesses", frozenset({"company"})),
    ("for profit", frozenset({"company"})),
)
_TEXT_ONLY = "others (see text"
_IHE_TEXT = re.compile(
    r"institutions? of higher education|\bIHEs?\b|universit(?:y|ies)|colleges?",
    re.IGNORECASE,
)
_INSTITUTION_NOUN = {
    "higher_ed": "Universities",
    "nonprofit": "Non-profits",
    "government": "Government labs",
    "company": "Companies",
}


def _applicant_check(meta: dict, institution_type: str) -> Check:
    types = [str(t) for t in meta.get("applicant_types") or []]
    noun = _INSTITUTION_NOUN.get(institution_type, "Your institution")
    admitted: set[str] = set()
    text_only = False
    for raw in types:
        low = raw.lower()
        if low.startswith(_TEXT_ONLY):
            text_only = True
            continue
        for needle, kinds in _APPLICANT_TYPES:
            if needle in low:
                admitted |= kinds
    if institution_type in admitted:
        if any(t.lower().startswith("unrestricted") for t in types):
            return Check("applicant", OK, "Any applicant type", "applicant_types")
        return Check("applicant", OK, f"{noun} can apply", "applicant_types")

    text = _text(meta, "eligibility")
    if (text_only or not types) and text:
        if institution_type == "higher_ed" and _IHE_TEXT.search(text):
            return Check("applicant", OK, f"{noun} can apply (stated in the text)",
                         "eligibility")
        return Check("applicant", UNKNOWN, "Eligibility is described only in the text",
                     "eligibility")
    if not types:
        return Check("applicant", UNKNOWN, "Applicant types not listed",
                     "applicant_types")
    named = [t for t in types if not t.lower().startswith(_TEXT_ONLY)]
    if text_only:
        label = f"Listed for {_short_list(named)}; check the text"
        return Check("applicant", WARN, label, "applicant_types")
    return Check("applicant", BLOCK, f"Applicants must be {_short_list(named)}",
                 "applicant_types")


# EU member states plus the countries associated to Horizon Europe across all its
# pillars. A university elsewhere can still join a consortium, usually unfunded.
_HORIZON_COUNTRIES = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES "
    "SE NO IS LI GB CH IL TR UA RS MD ME MK AL BA GE AM TN FO".split()
)
_US_SOURCES = frozenset({"grants_gov", "nsf", "nih_guide"})
_US_ONLY_TEXT = re.compile(
    r"located in the (?:U\.?S\.?|United States)|(?:U\.?S\.?|domestic) "
    r"(?:institutions|organizations)|campus located in the U",
    re.IGNORECASE,
)


def _country_check(meta: dict, country: str) -> Check:
    country = country.upper()
    sources = set(meta.get("contributing_sources") or [])
    funder = (meta.get("funder_canonical") or meta.get("funder") or "").lower()
    if "eu_portal" in sources or funder == "european commission":
        if country in _HORIZON_COUNTRIES:
            return Check("country", OK, "Eligible country for EU funding",
                         "contributing_sources")
        return Check(
            "country",
            WARN,
            "EU-led consortium. Institutions outside Europe usually join as "
            "associated partners without EU funding",
            "contributing_sources",
        )
    if sources & _US_SOURCES:
        if country == "US":
            return Check("country", OK, "US institutions can apply",
                         "contributing_sources")
        text = _text(meta, "eligibility")
        if text and _US_ONLY_TEXT.search(text):
            return Check("country", BLOCK, "US organisations only", "eligibility")
        return Check("country", WARN, "A US federal call: check foreign eligibility",
                     "contributing_sources")
    return Check("country", UNKNOWN, "Eligible countries not listed",
                 "contributing_sources")


# --------------------------------------------------------------------------- #
# Award, fellowship eligibility, team
# --------------------------------------------------------------------------- #
def _award_check(meta: dict, min_award: float) -> Check:
    floor, ceiling = meta.get("award_floor"), meta.get("award_ceiling")
    if ceiling is None and floor is None:
        return Check("award", UNKNOWN, "No award range listed", "award_ceiling")
    top = ceiling if ceiling is not None else floor
    currency = meta.get("currency") or ""
    if top < min_award:
        return Check(
            "award",
            BLOCK,
            f"Largest award {_money(top, currency)} is below your minimum",
            "award_ceiling",
        )
    return Check("award", OK, f"Up to {_money(top, currency)}", "award_ceiling")


def _fellowship_check(may_be_eligible: int, checked: int) -> Check:
    """Counts only: who is or is not eligible is told to each person privately."""
    if checked <= 0:
        return Check("eligibility", UNKNOWN, "Nobody's eligibility could be checked",
                     "facets")
    if may_be_eligible <= 0:
        return Check("eligibility", BLOCK, "Nobody here looks eligible", "facets")
    people = "person" if may_be_eligible == 1 else "people"
    return Check("eligibility", OK, f"{may_be_eligible} {people} may be eligible",
                 "facets")


def _team_check(suited: tuple[str, ...]) -> Check:
    if not suited:
        return Check("team", WARN, "Nobody's profile matches it closely", "member_fit")
    if len(suited) == 1:
        return Check("team", OK, f"{suited[0]} could lead", "member_fit")
    return Check("team", OK, f"{len(suited)} people could take it on", "member_fit")


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def _text(meta: dict, key: str) -> str:
    value = meta.get(key)
    return value if isinstance(value, str) else ""


def _day(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


def _days(n: int) -> str:
    if n == 0:
        return "today"
    return "1 day" if n == 1 else f"{n} days"


def _short_list(names: list[str]) -> str:
    cleaned = [re.sub(r"\s*\(.*?\)\s*", " ", n).strip().lower() for n in names]
    if len(cleaned) <= 2:
        return " or ".join(cleaned)
    return ", ".join(cleaned[:2]) + f" or {len(cleaned) - 2} other types"


def _money(amount: float, currency: str) -> str:
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
    if amount >= 1_000_000:
        text = f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    elif amount >= 1_000:
        text = f"{amount / 1_000:.0f}K"
    else:
        text = f"{amount:.0f}"
    return f"{symbol}{text}" if symbol else f"{text} {currency}".strip()


# --------------------------------------------------------------------------- #
# Readers — the one part of this module that reads models
# --------------------------------------------------------------------------- #
def reader_for_lab(lab, *, min_award: float | None = None) -> Reader:
    """A lab: its profile's institution type and country, and its buffer."""
    from apps.content.timeline_settings import effective_timeline

    profile = getattr(lab, "profile", None)
    return Reader(
        institution_type=getattr(profile, "institution_type", "") or "",
        country=getattr(profile, "country", "") or "",
        buffer_days=effective_timeline(reader=lab).buffer_days,
        min_award=min_award,
    )


def reader_for_department(department, *, min_award: float | None = None) -> Reader:
    from apps.content.timeline_settings import SYSTEM_BUFFER_DAYS

    profile = getattr(department, "profile", None)
    return Reader(
        institution_type=getattr(profile, "institution_type", "") or "",
        country=getattr(profile, "country", "") or "",
        buffer_days=SYSTEM_BUFFER_DAYS,
        min_award=min_award,
    )


def reader_for_user(user) -> Reader:
    """A person's own feed: only their deadline buffer applies. Who may apply is a
    fact about an institution, and a person's fellowship eligibility already has its
    own strip."""
    from apps.content.timeline_settings import effective_timeline

    return Reader(buffer_days=effective_timeline(reader=user).buffer_days)


def fellowship_counts(member_ids: list, items: list, today: date) -> dict:
    """``{content_id: (may_be_eligible, checked)}`` over members with a profile.

    Counts only: who is or is not eligible never appears on a lab surface.
    """
    from django.contrib.auth import get_user_model

    from apps.content.fellowships import eligibility_from_profile, evaluate_eligibility

    if not member_ids or not items:
        return {}
    users = get_user_model().objects.filter(id__in=member_ids).select_related("profile")
    eligs = [
        eligibility_from_profile(user.profile)
        for user in users
        if getattr(user, "profile", None) is not None
    ]
    if not eligs:
        return {}
    iso = today.isoformat()
    out = {}
    for item in items:
        metadata = item.metadata or {}
        fine = sum(
            evaluate_eligibility(metadata, elig, iso)["tier"] != "not_eligible"
            for elig in eligs
        )
        out[str(item.id)] = (fine, len(eligs))
    return out
