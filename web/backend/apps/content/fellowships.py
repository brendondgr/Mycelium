"""Hybrid fellowship ranking: deterministic eligibility, then research-fit.

Vendored and adapted from /home/bdgr/Tools/ProQuest/utils/Fellowships/recommend.py,
then extended with the embedding-match signal the grants/conferences matchers
already use. Fellowships still gate on eligibility facets, not semantic similarity
— citizenship, career stage, institutional/demographic restrictions have no
embedding — but eligibility alone says nothing about whether an eligible
fellowship is actually *relevant* to a researcher's work (an agriculture
scholarship a computer scientist happens to qualify for is not a good match). So
ranking is now a three-stage hybrid:

  1. Hard eligibility gates → not_eligible (citizenship, Illinois-only, Women/
     Equity restrictions) and closed/suspended items are dropped outright.
  2. Embedding relevance gate → when the caller supplies ``embed_by_id`` (the
     researcher declared interests and the fellowship corpus is embedded), an
     eligible item whose cosine match to those interests falls below
     ``embed_threshold`` is dropped too — the "eligible but irrelevant" case.
  3. Blended fit score → eligibility's tier/field/stage/recency/stipend rule score
     is blended with the embedding cosine (65% embedding / 35% rules) into one
     ``fit`` that ranks the survivors. With no ``embed_by_id`` (no declared
     interests, or retrieval unavailable) this degrades to the original rule-only
     fit and ordering — nothing regresses for users with no interest signal.

The public entry points are:

  eligibility_from_profile(profile) -> Elig
  match_fellowships(items, elig, today, embed_by_id=..., ...) -> list[dict]

All functions are pure (no ORM, no I/O, no embedder calls) except
``eligibility_from_profile``, which reads ``profile.interests`` and
``profile.institution`` — both accessed as attributes from an already-fetched
Django Profile object. The embedding lookups themselves happen in the caller
(:mod:`apps.content.opportunities`); this module only ever sees the resulting
``{content_id: cosine}`` dict.
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


#: Blend weights for the hybrid fit score: mostly the embedding (topical
#: relevance), a smaller share for the rule engine (eligibility strength).
_EMBED_WEIGHT = 0.65
_RULE_WEIGHT = 0.35

#: Embedding cosine at/above which a rules-sourced headline calls out the
#: research fit explicitly rather than falling back to the tier-based phrasing.
_STRONG_RESEARCH_FIT = 0.6


def match_fellowships(
    items,
    elig: Elig,
    today: str,
    *,
    match_threshold: float = 0.0,
    max_surface: int = FELLOWSHIP_SURFACE_LIMIT,
    embed_by_id: dict[str, float] | None = None,
    embed_threshold: float = 0.0,
) -> list[dict]:
    """Evaluate + filter + rank fellowship ContentItems for a user.

    Args:
        items: iterable of ContentItem queryset rows with ``.id``, ``.metadata``.
        elig:  the user's :class:`Elig` profile from :func:`eligibility_from_profile`.
        today: ISO date string (``YYYY-MM-DD``).
        match_threshold: minimum ``fit`` (0–1) a fellowship must reach to surface,
            applied *after* the eligibility gate (and, when ``embed_by_id`` is
            given, the embedding relevance gate below). ``0.0`` (the default)
            surfaces every eligible/relevant fellowship; raising it trims the
            weak tail. This is what makes the feed variable-length instead of a
            fixed top-N.
        max_surface: backstop cap on how many fellowships to return.
        embed_by_id: ``{content_id: cosine}`` — the researcher's embedding match
            to each fellowship, in ``[0, 1]``, from the caller's own
            retrieve+fuse step. ``None`` (the default) means no interest signal
            was available (no declared interests/watch topics, or retrieval
            failed) — in that case this function behaves exactly as it always
            has: a pure eligibility/recency rule ranking, no embedding gate or
            blend. A fellowship absent from the dict counts as ``0.0`` — it
            simply was not retrieved as relevant to any declared interest.
        embed_threshold: minimum embedding cosine an eligible fellowship must
            clear to surface at all, when ``embed_by_id`` is given. This is the
            "eligible but irrelevant" gate — an agriculture scholarship a CS
            researcher happens to qualify for is dropped here, before the blend.

    Returns:
        List of suggestion dicts, best first (``-fit``, then earliest actionable
        deadline, then title): every eligible fellowship that clears the
        embedding relevance gate (if any) and ``match_threshold``, capped at
        ``max_surface``. ``not_eligible`` and closed/suspended items are always
        excluded. Each dict carries ``fit`` (the blended score used to rank —
        equal to the rule fit when there is no embedding signal), ``rule_fit``
        (the pure eligibility/recency score), and, when ``embed_by_id`` was
        given, ``embedding_match`` (the raw cosine) — the same signal name the
        grants/conferences matchers persist, so the serializer reads it
        unchanged.
    """
    ranked: list[tuple[float, str, str, dict]] = []

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

        content_id = str(item.id)
        rule_fit = fit(ev, st, today)

        embed_match: float | None = None
        if embed_by_id is not None:
            embed_match = embed_by_id.get(content_id, 0.0)
            # Relevance gate: eligible-but-irrelevant fellowships stop here,
            # before they ever reach the blend or the rank.
            if embed_match < embed_threshold:
                continue
            blended = round(_EMBED_WEIGHT * embed_match + _RULE_WEIGHT * rule_fit, 4)
        else:
            blended = rule_fit

        # Fit threshold: trims the weakly-related tail so the feed stays "most
        # related" (0.0 keeps everything that passed the gates above).
        if blended < match_threshold:
            continue

        actionable = st.get("actionable_date") or "9999-99"
        title = meta.get("title") or ""

        if embed_match is not None and embed_match >= _STRONG_RESEARCH_FIT:
            headline = "Strong research-fit match"
        elif ev["tier"] == "qualified":
            headline = "Strong eligibility match"
        else:
            headline = "Possible fit"
        reason = "; ".join(ev["reasons"]) if ev["reasons"] else ""

        # match_percent is the topical percent (the embedding cosine) once a
        # research-fit signal exists — the old rule-fit percent conflated
        # eligibility strength with relevance, which is exactly what caused an
        # eligible-but-irrelevant fellowship to read as an 84% match.
        match_percent = (
            round(embed_match * 100)
            if embed_match is not None
            else round(rule_fit * 100)
        )

        suggestion = {
            "content_id": content_id,
            "tier": ev["tier"],
            "fit": blended,
            "rule_fit": rule_fit,
            "similarity": blended,
            "match_percent": match_percent,
            "gates_failed": ev["gates_failed"],
            "reasons": ev["reasons"],
            "headline": headline,
            "reason": reason,
            "source": "rules",
            "status": st["status"],
            "actionable_date": st["actionable_date"],
            "status_summary": st["summary"],
        }
        if embed_match is not None:
            suggestion["embedding_match"] = round(embed_match, 4)

        ranked.append((-blended, actionable, title, suggestion))

    ranked.sort(key=lambda x: (x[0], x[1], x[2]))

    out = []
    for rank, (_, _, _, suggestion) in enumerate(ranked[:max_surface], start=1):
        suggestion["rank"] = rank
        out.append(suggestion)

    return out
