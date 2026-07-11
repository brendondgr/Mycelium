"""Deterministic fellowship eligibility rule engine (no LLM, no embeddings).

Vendored and adapted from /home/bdgr/Tools/ProQuest/utils/Fellowships/recommend.py.
Fellowships are matched by eligibility facets rather than semantic similarity, so the
full pipeline (embed → retrieve → LLM score) is replaced by a simple rule check:

  1. Hard gates → not_eligible (citizenship, Illinois-only, Women/Equity restrictions).
  2. Soft signals → conditional when stage/field don't match, qualified otherwise.
  3. Fit score (0–1) weighs qualification tier, field/stage match, recency, stipend.

The public entry points are:

  eligibility_from_profile(profile) -> Elig
  match_fellowships(items, elig, today) -> list[dict]    # one dict per surfaced item

All functions are pure (no ORM, no I/O) except ``eligibility_from_profile``, which
reads ``profile.interests`` and ``profile.institution`` — both are accessed as
attributes from an already-fetched Django Profile object.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- Canonical facet strings (must match the Illinois Fellowship Finder vocab) -

US_FACET = "US Citizens, Nationals, or Permanent Residents"
INTL_FACET = "International Students"
ILLINOIS_LIMIT = "University of Illinois Students"
STIPEND_LIMIT = "Annual stipend of at least $10,000"

#: Group limits that are hard gates (user must opt in via eligible_restrictions).
GROUP_LIMITS: dict[str, str] = {
    "Women": "women applicants",
    "Equity": "underrepresented groups",
}

#: User stage token -> Illinois stage-facet string(s) it satisfies.
STAGE_MAP: dict[str, list[str]] = {
    "masters": ["Master's"],
    "doctoral_early": ["Early Years of Doctoral Program"],
    "doctoral_dissertation": ["Dissertation Research", "Dissertation Write-Up"],
    "postdoc": ["Postdoctoral/Post-graduate"],
}

TIER_RANK: dict[str, int] = {"qualified": 0, "conditional": 1, "not_eligible": 2}

# Maximum fellowships to surface per user per run.
FELLOWSHIP_SURFACE_LIMIT = 40


# ---- Eligibility profile -------------------------------------------------------


@dataclass
class Elig:
    """A user's eligibility profile, parsed from interests + institution."""

    citizenship: str = "us"                    # "us" | "international"
    stage_tokens: set = field(default_factory=set)   # Illinois stage facet strings
    fields: list = field(default_factory=list)       # broad field bucket strings
    university: str = ""
    is_illinois_student: bool = False
    eligible_restrictions: list = field(default_factory=list)   # ["Women","Equity"]


def eligibility_from_profile(profile) -> Elig:
    """Build an :class:`Elig` from a Django Profile object.

    Reads ``profile.interests.get("eligibility")`` for the user-supplied block
    and ``profile.institution`` for the university/Illinois check.  All fields
    default safely when absent so users without an eligibility block still get a
    sensible (US-citizen, empty stage/fields) profile.
    """
    interests = getattr(profile, "interests", None) or {}
    e = interests.get("eligibility") or {}
    university = (
        e.get("university")
        or getattr(profile, "institution", "")
        or ""
    )
    is_illinois = e.get("is_illinois_student")
    if is_illinois is None:
        is_illinois = "illinois" in university.lower()
    stage = e.get("stage") or ""
    return Elig(
        citizenship=(e.get("citizenship") or "us").lower(),
        stage_tokens=set(STAGE_MAP.get(stage, [])),
        fields=list(e.get("fields") or []),
        university=university,
        is_illinois_student=bool(is_illinois),
        eligible_restrictions=list(e.get("eligible_restrictions") or []),
    )


# ---- Eligibility evaluation ----------------------------------------------------


def evaluate_eligibility(metadata: dict, elig: Elig) -> dict:
    """Tier a fellowship for a user: qualified | conditional | not_eligible.

    Hard gates (any failure -> not_eligible):
      - Citizenship mismatch (international-only vs US citizen, or vice versa).
      - Illinois-student restriction when the user is not at Illinois.
      - Women/Equity group restriction the user has not opted into.

    Soft signals (mismatch -> conditional, not hidden):
      - Stage: typically doctoral_early, but fellowships are fuzzy.
      - Field: broad bucket match; mismatches surface as conditional.
    """
    facets = metadata.get("facets") or {}
    cit = facets.get("citizenship") or []
    lim = facets.get("limits") or []
    stage_f = set(facets.get("stage") or [])
    field_f = set(facets.get("field") or [])
    flags = metadata.get("flags") or {}
    gates: list[str] = []
    reasons: list[str] = []

    # Citizenship
    if elig.citizenship == "us":
        if INTL_FACET in cit and US_FACET not in cit:
            gates.append("International students only")
        else:
            reasons.append("US citizen / permanent resident eligible")
    else:
        if (US_FACET in cit and INTL_FACET not in cit) or flags.get(
            "requires_us_citizenship"
        ):
            gates.append("Requires US citizen / permanent resident")
        else:
            reasons.append("Open to international students")

    # Illinois restriction
    if ILLINOIS_LIMIT in lim and not elig.is_illinois_student:
        gates.append("Restricted to University of Illinois students")

    # Group restrictions (Women / Equity)
    for limit, phrase in GROUP_LIMITS.items():
        if limit in lim and limit not in elig.eligible_restrictions:
            gates.append(f"Restricted to {phrase}")

    # Soft signals
    stage_match = (not stage_f) or bool(stage_f & elig.stage_tokens)
    field_match = (not field_f) or bool(field_f & set(elig.fields))
    has_stipend = STIPEND_LIMIT in lim

    if gates:
        tier = "not_eligible"
    elif stage_match and field_match:
        tier = "qualified"
    else:
        tier = "conditional"

    if stage_f:
        reasons.append(
            "Stage matches"
            if stage_match
            else "Stage: typically for " + ", ".join(sorted(stage_f))
        )
    if field_f:
        reasons.append(
            "Field matches"
            if field_match
            else "Field: " + ", ".join(sorted(field_f))
        )
    if has_stipend:
        reasons.append("Stipend ≥ $10,000")

    return {
        "tier": tier,
        "gates_failed": gates,
        "reasons": reasons,
        "stage_match": stage_match,
        "field_match": field_match,
        "has_stipend": has_stipend,
    }


# ---- Deadline status -----------------------------------------------------------


def _is_future(date_str: str, today: str) -> bool:
    """ISO date string >= today, compared at the date's own granularity."""
    if not date_str:
        return False
    return date_str >= today[: len(date_str)]


def fellowship_status(metadata: dict, today: str) -> dict:
    """Uniform ``{status, actionable_date, summary}`` for a fellowship deadline.

    Reads the structured ``metadata["deadline"]`` dict produced by the scraper:
      type: "true" | "anticipated" | "continuous" | "rolling" | "suspended" | "unknown"
      date: ISO date (or "" for dateless types)
    """
    d = metadata.get("deadline") or {}
    t = d.get("type", "")
    date_str = d.get("date") or ""

    if t == "suspended":
        return {
            "status": "suspended", "actionable_date": "", "summary": "Award suspended"
        }
    if t in ("continuous", "rolling"):
        return {
            "status": "open",
            "actionable_date": "",
            "summary": t.capitalize() + " / rolling deadline",
        }
    if t == "anticipated":
        return {
            "status": "open",
            "actionable_date": date_str,
            "summary": (
                f"Anticipated deadline {date_str}"
                if date_str
                else "Anticipated (recurring)"
            ),
        }
    if t == "true":
        if _is_future(date_str, today):
            return {
                "status": "open",
                "actionable_date": date_str,
                "summary": f"Deadline {date_str}",
            }
        return {
            "status": "closed",
            "actionable_date": date_str,
            "summary": f"Deadline passed ({date_str})",
        }
    return {
        "status": "unknown",
        "actionable_date": date_str,
        "summary": "No fixed deadline listed",
    }


# ---- Fit score -----------------------------------------------------------------


def _days_until(date_str: str, today: str) -> int | None:
    from datetime import datetime

    if not date_str:
        return None
    d = date_str + "-01" if len(date_str) == 7 else date_str
    try:
        a = datetime.strptime(d, "%Y-%m-%d")
        b = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        return None
    return (a - b).days


def recency(date_str: str, today: str) -> float:
    """1.0 for an imminent future date, decaying to 0 over ~18 months; 0 if past."""
    dd = _days_until(date_str, today)
    if dd is None or dd < 0:
        return 0.0
    return max(0.0, 1.0 - dd / 540.0)


def fit(evaluation: dict, status: dict, today: str) -> float:
    """Compute a 0–1 fit score from tier, field/stage match, recency, stipend."""
    qual = {"qualified": 1.0, "conditional": 0.55}.get(evaluation["tier"], 0.0)
    score = (
        0.45 * qual
        + 0.15 * (1.0 if evaluation["field_match"] else 0.0)
        + 0.12 * (1.0 if evaluation["stage_match"] else 0.0)
        + 0.18 * recency(status.get("actionable_date", ""), today)
        + 0.10 * (1.0 if evaluation["has_stipend"] else 0.0)
    )
    return round(score, 4)


# ---- Top-level match -----------------------------------------------------------


def match_fellowships(
    items,
    elig: Elig,
    today: str,
    *,
    match_threshold: float = 0.0,
    max_surface: int = FELLOWSHIP_SURFACE_LIMIT,
) -> list[dict]:
    """Evaluate + filter + rank fellowship ContentItems for a user.

    Args:
        items: iterable of ContentItem queryset rows with ``.id``, ``.metadata``.
        elig:  the user's :class:`Elig` profile from :func:`eligibility_from_profile`.
        today: ISO date string (``YYYY-MM-DD``).
        match_threshold: minimum ``fit`` (0–1) a fellowship must reach to surface,
            applied *after* the hard eligibility gate — so ``0.0`` (the default)
            surfaces every fellowship the user is actually eligible for, and raising
            it trims weak-fit conditionals. This is what makes the feed
            variable-length instead of a fixed top-N.
        max_surface: backstop cap on how many fellowships to return.

    Returns:
        List of suggestion dicts, sorted by (tier_rank, -fit, actionable_date):
        every eligible fellowship whose ``fit`` clears ``match_threshold``, capped at
        ``max_surface``.  ``not_eligible`` and closed/suspended items are excluded.
    """
    ranked: list[tuple[float, str, dict]] = []

    for item in items:
        meta = item.metadata or {}

        # Skip grants that slipped into the fellowship corpus.
        if meta.get("award_class") == "grant":
            continue

        ev = evaluate_eligibility(meta, elig)
        st = fellowship_status(meta, today)

        # Drop hard-ineligible and closed/suspended.
        if ev["tier"] == "not_eligible":
            continue
        if st["status"] in ("closed", "suspended"):
            continue

        fit_score = fit(ev, st, today)

        # Fit threshold: eligibility already gated "qualified for"; this trims the
        # weakly-related tail so the feed stays "most related" (0.0 keeps everything).
        if fit_score < match_threshold:
            continue

        tier_rank = TIER_RANK[ev["tier"]]
        actionable = st.get("actionable_date") or "9999-99"

        headline = (
            "Strong eligibility match"
            if ev["tier"] == "qualified"
            else "Possible fit"
        )
        reason = "; ".join(ev["reasons"]) if ev["reasons"] else ""

        suggestion = {
            "content_id": str(item.id),
            "tier": ev["tier"],
            "fit": fit_score,
            "similarity": fit_score,
            "match_percent": round(fit_score * 100),
            "gates_failed": ev["gates_failed"],
            "reasons": ev["reasons"],
            "headline": headline,
            "reason": reason,
            "source": "rules",
            "status": st["status"],
            "actionable_date": st["actionable_date"],
            "status_summary": st["summary"],
        }
        ranked.append((tier_rank, -fit_score, actionable, suggestion))

    ranked.sort(key=lambda x: (x[0], x[1], x[2]))

    out = []
    for rank, (_, _, _, suggestion) in enumerate(ranked[:max_surface], start=1):
        suggestion["rank"] = rank
        out.append(suggestion)

    return out
