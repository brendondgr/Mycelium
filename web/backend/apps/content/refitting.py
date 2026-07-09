"""Refit each user's personalized layer over the *existing* top results.

"Refitting" re-runs only the **personalization** half of the daily pipelines: for
each area (research papers, grants, conferences, fellowships) it takes the top
results already stored and re-scores them through the language model to refresh the
per-user layer — with **no** literature scan and **no** Pivot re-scrape. It is the
cheap, on-demand counterpart to the nightly jobs, used after a profile edit or to
re-personalize without paying the full ingest cost.

The two halves reuse the existing no-side-effect paths, so refitting shares the one
code path the daily jobs use:

- **Papers** → :func:`apps.content.pipeline.recommend_for_user` (retrieve → fuse →
  LLM suggest, against the already-populated store — no scanning of its own).
- **Grants / conferences / fellowships** →
  :func:`apps.content.opportunities.run_opportunities_for_user` (retrieve → fuse →
  LLM score over the existing Pivot corpus — no ingest). Fellowships score via the
  deterministic rule engine, so they refit without an LLM call.

Every seam (the language model in particular) is injectable via ``complete`` so the
suite runs offline, and a failure for one user is caught so it never sinks a batch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from django.contrib.auth.models import User

from .opportunities import run_opportunities_for_user
from .pipeline import recommend_for_user
from .suggest import CompleteFn

logger = logging.getLogger(__name__)

# The areas a refit covers, in report order. "papers" is the daily-suggestions
# layer; the rest are the opportunity layers (fellowships via the rule engine).
PAPER_AREA = "papers"
OPPORTUNITY_AREAS = ("grants", "conferences", "fellowships")
DEFAULT_AREAS: tuple[str, ...] = (PAPER_AREA, *OPPORTUNITY_AREAS)


@dataclass
class RefitResult:
    """A JSON-able report of one user's refit across every requested area."""

    username: str
    status: str  # ok | error
    areas: dict = field(default_factory=dict)  # area -> per-area summary dict
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _paper_summary(result) -> dict:
    return {
        "status": result.status,
        "retrieved": result.retrieved,
        "suggestions": result.suggestions,
        "llm": result.llm,
        "fallback": result.fallback,
    }


def _opportunity_summary(result) -> dict:
    return {
        "status": result.status,
        "retrieved": result.retrieved,
        "suggestions": result.suggestions,
        "llm": result.llm,
        "fallback": result.fallback,
        "new": result.new,
    }


def refit_user(
    user: User,
    *,
    areas: Sequence[str] = DEFAULT_AREAS,
    llm_limit: int | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
    log: Callable[[str], None] | None = None,
) -> RefitResult:
    """Refit one user's personalized layer over the already-stored top results.

    Runs the recommend (papers) and match (opportunities) halves with no scanning
    or ingest, re-scoring the existing corpus through the model. ``complete`` is the
    injectable LLM seam (``None`` uses the configured model; a stub forces the
    deterministic fallback); ``persist=False`` computes without writing scores.

    ``llm_limit`` sets how many of each area's surfaced items go to the model
    (the rest are filled deterministically). ``None`` keeps each pipeline's own
    default (top 10); a large value (e.g. the surfaced count) gives every surfaced
    item genuine LLM feedback — the point of a manual recovery refit. It is ignored
    for fellowships, which score via the deterministic rule engine (no LLM).
    """
    username = user.get_username()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}] {message}")

    # Only pass the limit through when set, so ``None`` defers to each pipeline's
    # own default rather than overriding it with a hardcoded number here.
    paper_kwargs = {} if llm_limit is None else {"suggestion_limit": llm_limit}
    opp_kwargs = {} if llm_limit is None else {"llm_limit": llm_limit}

    summaries: dict[str, dict] = {}

    if PAPER_AREA in areas:
        emit("refit papers (recommend over existing store)")
        paper = recommend_for_user(
            user, complete=complete, persist=persist, log=log, **paper_kwargs
        )
        summaries[PAPER_AREA] = _paper_summary(paper)

    opp_areas = tuple(a for a in areas if a in OPPORTUNITY_AREAS)
    if opp_areas:
        emit(f"refit opportunities: {', '.join(opp_areas)} (no ingest)")
        for result in run_opportunities_for_user(
            user,
            areas=opp_areas,
            complete=complete,
            persist=persist,
            log=log,
            **opp_kwargs,
        ):
            summaries[result.area] = _opportunity_summary(result)

    return RefitResult(username, "ok", areas=summaries)


def refit_batch(
    users: Sequence[User],
    *,
    areas: Sequence[str] = DEFAULT_AREAS,
    llm_limit: int | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
    log: Callable[[str], None] | None = None,
) -> list[RefitResult]:
    """Refit every user in turn; one user's failure never sinks the batch."""
    results: list[RefitResult] = []
    for user in users:
        username = user.get_username()
        try:
            results.append(
                refit_user(
                    user,
                    areas=areas,
                    llm_limit=llm_limit,
                    complete=complete,
                    persist=persist,
                    log=log,
                )
            )
        except Exception:
            logger.exception("refit failed for %s", username)
            if log is not None:
                log(f"[{username}] ERROR (see worker log)")
            results.append(RefitResult(username, "error", note="refit failed"))
    return results
