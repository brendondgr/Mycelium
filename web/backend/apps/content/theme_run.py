"""Per-theme orchestration: slates in, write-ups out.

The join between the deterministic half of the run (retrieve → fuse → slate per
cluster) and the model half (:mod:`.comprehension`, :mod:`.cluster_fit`). It is
the one place that decides *which* (cluster, item) pairs are worth a model call,
and it answers that with three rules in order:

1. **Reuse first.** A pair that already has a current write-up is served from
   store. A second run over an unchanged profile therefore makes zero model
   calls, and an item re-entering a slate makes zero as well — it is badged new
   again, which is the correct existing semantics, but "new to the reader's
   attention" is not "new to Mylo". For an entitled target a *deterministic*
   write-up is not reusable: it stands in for a call the budget could not pay
   for, and reusing it is what used to strand it there for good.
2. **Entitlement second.** Model reasoning is a paid layer. An unentitled target
   never reaches a prompt at all, and gets the deterministic write-up, which is
   the baseline product rather than a degraded one.
3. **Budget third.** Whatever is left is ordered by position within the theme —
   the slate's own order, so it follows whichever ``RERANK_METHOD`` produced it —
   with entrants ahead of standing members at the same position, and cut at the
   run budget. What does not fit carries to the next run rather than being
   dropped. Position leads because the head of a slate is the head of the feed:
   funding an entrant at 25th ahead of a carried item at 2nd is how the reader's
   first papers ended up the ones Mylo had not read.

Everything the slate holds ends up with a write-up either way, so a section is
never a mix of explained and unexplained rows.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .cluster_fit import (
    Candidate,
    Evidence,
    areas_fingerprint,
    deterministic_writeup,
    is_current,
    stored_writeup,
    write_cluster_fits,
    writeup_budget,
    writeup_concurrency,
)
from .clustering import Cluster
from .comprehension import (
    extract_many,
    load_comprehensions,
    store_comprehensions,
)
from .models import ContentItem, RelevanceScore
from .slates import slate_depth

logger = logging.getLogger(__name__)


@dataclass
class ThemeRunResult:
    """What one target's write-up pass did — the line the run log prints."""

    reused: int = 0
    written: int = 0
    deterministic: int = 0
    carried: int = 0
    entitled: bool = False
    #: ``{content_id: {cluster_id: writeup}}`` — everything the persist step writes.
    writeups: dict[str, dict[str, dict]] = field(default_factory=dict)

    def note(self) -> str:
        bits = [
            f"{self.written} written",
            f"{self.reused} reused",
            f"{self.deterministic} deterministic",
        ]
        if self.carried:
            bits.append(f"{self.carried} carried to the next run")
        if not self.entitled:
            bits.append("model reasoning not entitled")
        return ", ".join(bits)


def target_is_entitled(persist_kwargs: Mapping, feature: str | None = None) -> bool:
    """Whether this target's plan includes ``feature`` (default: model reasoning).

    The gate sits *before* any call, not after — the moment per-cluster budgets
    multiply calls per user, an unfiltered selection turns a pricing gap into a
    cost problem. A lab or project target inherits the entitlement of the plan
    that covers it; where no user can be resolved (a lab with no owner in the
    call site's hands) the deterministic path is chosen, which is safe in the
    direction that matters.
    """
    from apps.billing.entitlements import Feature, has_feature

    feature = feature or Feature.LLM_FIT_SCORING
    user = persist_kwargs.get("target_user")
    if user is not None:
        return has_feature(user, feature)

    lab = persist_kwargs.get("target_lab")
    project = persist_kwargs.get("target_project")
    scope_lab = lab if lab is not None else getattr(project, "scope_lab", None)
    if scope_lab is not None:
        return _lab_entitled(scope_lab)
    owner = getattr(project, "scope_user", None)
    if owner is not None:
        return has_feature(owner, feature)
    return False


def _lab_entitled(lab) -> bool:
    """A lab is entitled when it holds an active plan of its own or via its dept."""
    from apps.billing.models import Subscription

    return Subscription.objects.filter(
        status=Subscription.Status.ACTIVE
    ).filter(
        scope_lab=lab
    ).exists() or (
        lab.department_id is not None
        and Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, scope_department_id=lab.department_id
        ).exists()
    )


def build_evidence(
    signals: Mapping,
    cluster: Cluster,
    item: ContentItem,
    *,
    position: int,
    is_new: bool,
    also_in: Sequence[str],
) -> Evidence:
    """The retrieval evidence packet for one (item, theme) pair.

    Every field is already known — the per-interest scores the fusion recorded,
    the theme's own interests, and the slate map. Nothing here costs a query, and
    without it the model is guessing why the system surfaced something.
    """
    per_interest = signals.get("per_interest")
    per_interest = per_interest if isinstance(per_interest, dict) else {}
    own = {area.casefold() for area in cluster.areas}
    matched = sorted(
        (
            (label, score)
            for label, score in per_interest.items()
            if label.casefold() in own
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    meta = item.metadata or {}
    haystack = " ".join(
        str(meta.get(key) or "")
        for key in ("title", "name", "abstract", "summary", "description")
    ).casefold()
    literal = [area for area in cluster.areas if area.casefold() in haystack]
    return Evidence(
        matched_interests=[label for label, _score in matched],
        literal_terms=literal,
        also_in=list(also_in),
        is_new=is_new,
        position=position,
    )


@dataclass
class ThemePlan:
    """The DB-resolved half of a write-up pass, ready for the model.

    Split out so the model calls can run in a worker thread while every ORM read
    and write stays on a database thread. :func:`plan_theme_writeups` builds it,
    :func:`execute_theme_plan` is pure and does the calling, and
    :func:`store_theme_plan` writes the précis rows back.
    """

    clusters: list[Cluster] = field(default_factory=list)
    profile_text: str = ""
    depth: int = 10
    entitled: bool = False
    seed: int = 0
    #: Already-current write-ups, served from store — no call, ever.
    reused: dict[str, dict[str, dict]] = field(default_factory=dict)
    #: ``[(cluster_id, content_id, candidate)]`` this run will pay for.
    funded: list[tuple[str, str, Candidate]] = field(default_factory=list)
    #: The same, beyond the budget — deterministic now, carried to the next run.
    unfunded: list[tuple[str, str, Candidate]] = field(default_factory=list)
    #: Items with no current précis, which the model half will read.
    needs_precis: list[ContentItem] = field(default_factory=list)
    fingerprints: dict[str, str] = field(default_factory=dict)
    #: The project's stated claim, as the prompt reads it, and the fingerprint of
    #: the slow state it came from. Both empty for a person or a lab, and for a
    #: project that has not said what it claims — in which case the prompt and
    #: the cost are exactly what they were.
    project_claim: str = ""
    state_fingerprint: str = ""


def _project_claim(persist_kwargs: Mapping) -> dict:
    """``{project_claim, state_fingerprint}`` for a project target, else empty.

    Read from the project's stored state. A project that has not been asked yet
    contributes nothing, so its prompt and its cost are exactly a person's —
    which is what lets the state be optional rather than a gate on the feature.
    """
    from .cluster_fit import project_claim_block

    project = persist_kwargs.get("target_project")
    state = getattr(project, "state", None) if project is not None else None
    if state is None:
        return {"project_claim": "", "state_fingerprint": ""}
    claim = project_claim_block(getattr(state, "slow", None))
    if not claim:
        return {"project_claim": "", "state_fingerprint": ""}
    return {
        "project_claim": claim,
        "state_fingerprint": str(getattr(state, "slow_fingerprint", "") or ""),
    }


def plan_theme_writeups(
    persist_kwargs: dict,
    content_type: str,
    clusters: Sequence[Cluster],
    slates: Mapping[str, Mapping[str, dict]],
    rows_by_id: Mapping[str, tuple[ContentItem, dict]],
    *,
    profile_text: str,
    entitled: bool | None = None,
    budget: int | None = None,
    seed: int = 0,
    reuse: bool = True,
) -> ThemePlan:
    """Decide what this run owes the model — all database work, no calls.

    ``slates`` is :func:`apps.content.slates.compute_cluster_slates`' output
    (``{content_id: {cluster_id: entry}}``) and ``rows_by_id`` maps a content id
    to the item and the signals this run computed for it, so evidence is built
    from the fusion's own numbers rather than re-derived.

    ``reuse=False`` bypasses the store and re-writes every pair. It is what a
    profile edit needs — the judgement was made against different interests, so
    it is now answering the wrong question — and it is deliberately the *only*
    way to spend the budget on something already written.
    """
    by_id = {cluster.id: cluster for cluster in clusters}
    labels = {cluster.id: cluster.label for cluster in clusters}
    plan = ThemePlan(
        clusters=list(clusters),
        profile_text=profile_text,
        depth=slate_depth(content_type),
        seed=seed,
        fingerprints={c.id: areas_fingerprint(c.areas) for c in clusters},
        entitled=(
            target_is_entitled(persist_kwargs) if entitled is None else entitled
        ),
        **_project_claim(persist_kwargs),
    )
    if not slates:
        return plan
    stored = _stored_writeups(persist_kwargs, content_type)

    pending: list[tuple[str, str, Candidate]] = []
    for cid, entries in slates.items():
        row = rows_by_id.get(cid)
        if row is None:
            continue
        item, signals = row
        for cluster_id, entry in entries.items():
            cluster = by_id.get(cluster_id)
            if cluster is None:
                continue
            existing = stored.get(cid, {}).get(cluster_id)
            if (
                reuse
                and is_current(
                    existing, plan.fingerprints[cluster_id], plan.state_fingerprint
                )
                and not (plan.entitled and existing.get("source") == "deterministic")
            ):
                plan.reused.setdefault(cid, {})[cluster_id] = existing
                continue
            evidence = build_evidence(
                signals,
                cluster,
                item,
                position=entry["rank"],
                is_new=entry["is_new"],
                also_in=[
                    labels.get(other, "")
                    for other in entries
                    if other != cluster_id and labels.get(other)
                ],
            )
            pending.append((cluster_id, cid, Candidate(item=item, evidence=evidence)))

    # Priority-first across all themes **jointly**, so one noisy theme cannot
    # starve the others, and independently of slate depth, so depth never becomes
    # a cost dial by accident. Position leads — every theme's 1st, then every 2nd
    # — so the budget covers the head of the feed before any tail. Whatever falls
    # past the cut is written deterministically now and carried to the next run.
    cap = writeup_budget() if budget is None else budget
    pending.sort(
        key=lambda triple: (
            triple[2].evidence.position,
            0 if triple[2].evidence.is_new else 1,
        )
    )
    if plan.entitled:
        plan.funded = pending[:cap]
        plan.unfunded = pending[cap:]
    else:
        plan.unfunded = pending

    if plan.funded:
        items = {cid: candidate.item for _cluster, cid, candidate in plan.funded}
        cached = load_comprehensions(items.values())
        for _cluster_id, cid, candidate in plan.funded:
            candidate.precis = cached.get(cid)
        plan.needs_precis = [
            item for cid, item in items.items() if cid not in cached
        ]
    return plan


def execute_theme_plan(
    plan: ThemePlan, *, complete=None
) -> tuple[dict[str, dict[str, dict]], dict[str, dict]]:
    """Run the model over a plan. **Pure** — no ORM, safe in a worker thread.

    Returns ``(writeups, precis_fields)``: the write-ups keyed
    ``{content_id: {cluster_id: entry}}``, and the freshly-extracted précis fields
    for :func:`apps.content.comprehension.store_comprehensions` to persist.
    """
    writeups: dict[str, dict[str, dict]] = {}
    precis_fields: dict[str, dict] = {}
    if not plan.funded:
        return writeups, precis_fields

    if plan.needs_precis:
        precis_fields = extract_many(plan.needs_precis, complete=complete)

    by_id = {cluster.id: cluster for cluster in plan.clusters}
    by_cluster: dict[str, list[Candidate]] = {}
    for cluster_id, _cid, candidate in plan.funded:
        by_cluster.setdefault(cluster_id, []).append(candidate)

    # Themes are independent, so they run side by side and share the target's
    # in-flight budget (``WRITEUP_LLM_CONCURRENCY``): each theme's batches get
    # an equal slice, so the total never exceeds the budget.
    total = writeup_concurrency()
    theme_workers = max(1, min(total, len(by_cluster)))
    per_theme = max(1, total // theme_workers)

    def one(job: tuple[str, list[Candidate]]) -> tuple[str, dict[str, dict]]:
        cluster_id, candidates = job
        cluster = by_id[cluster_id]
        return cluster_id, write_cluster_fits(
            plan.profile_text,
            cluster,
            [c.label for c in plan.clusters if c.id != cluster_id],
            candidates,
            depth=plan.depth,
            complete=complete,
            seed=plan.seed,
            project_claim=plan.project_claim,
            state_fingerprint=plan.state_fingerprint,
            concurrency=per_theme,
        )

    jobs = list(by_cluster.items())
    if theme_workers == 1:
        results = [one(job) for job in jobs]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=theme_workers) as pool:
            results = list(pool.map(one, jobs))
    for cluster_id, written in results:
        for cid, writeup in written.items():
            writeups.setdefault(cid, {})[cluster_id] = writeup
    return writeups, precis_fields


def collect_theme_result(
    plan: ThemePlan, writeups: Mapping[str, Mapping[str, dict]]
) -> ThemeRunResult:
    """Fold a plan and the model's answers into the run's final write-up map.

    Everything the slate holds ends up with a write-up either way, so a section is
    never a mix of explained and unexplained rows: whatever the model did not
    cover — because it was unfunded, unreachable, or answered without the
    mandatory caveat — falls back to the deterministic write-up for that pair.
    """
    result = ThemeRunResult(entitled=plan.entitled, carried=len(plan.unfunded))
    by_id = {cluster.id: cluster for cluster in plan.clusters}
    for cid, entries in plan.reused.items():
        for cluster_id, entry in entries.items():
            result.writeups.setdefault(cid, {})[cluster_id] = entry
            result.reused += 1
    for cid, entries in (writeups or {}).items():
        for cluster_id, entry in entries.items():
            result.writeups.setdefault(cid, {})[cluster_id] = entry
            if entry.get("source") == "llm":
                result.written += 1
            else:
                result.deterministic += 1
    for cluster_id, cid, candidate in [*plan.funded, *plan.unfunded]:
        if cluster_id in result.writeups.get(cid, {}):
            continue
        result.writeups.setdefault(cid, {})[cluster_id] = deterministic_writeup(
            candidate.item,
            by_id[cluster_id],
            candidate.evidence,
            depth=plan.depth,
            fingerprint=plan.fingerprints[cluster_id],
        )
        result.deterministic += 1
    if not plan.entitled:
        result.carried = 0
    return result


def run_theme_writeups(
    persist_kwargs: dict,
    content_type: str,
    clusters: Sequence[Cluster],
    slates: Mapping[str, Mapping[str, dict]],
    rows_by_id: Mapping[str, tuple[ContentItem, dict]],
    *,
    profile_text: str,
    complete=None,
    entitled: bool | None = None,
    budget: int | None = None,
    seed: int = 0,
    reuse: bool = True,
) -> ThemeRunResult:
    """Plan, call, store — the all-in-one wrapper for callers on a DB thread."""
    plan = plan_theme_writeups(
        persist_kwargs,
        content_type,
        clusters,
        slates,
        rows_by_id,
        profile_text=profile_text,
        entitled=entitled,
        budget=budget,
        seed=seed,
        reuse=reuse,
    )
    writeups, precis_fields = execute_theme_plan(plan, complete=complete)
    if precis_fields:
        store_comprehensions(plan.needs_precis, precis_fields)
    return collect_theme_result(plan, writeups)


def _stored_writeups(
    persist_kwargs: dict, content_type: str
) -> dict[str, dict[str, dict]]:
    """Every write-up already on this target's rows, ``{content_id: {cid: entry}}``.

    Read in one query before the run writes. Write-ups **persist** through a
    slate exit — an item dropping out of a live theme loses its position but
    keeps its reasoning, so re-entry costs nothing.
    """
    out: dict[str, dict[str, dict]] = {}
    rows = RelevanceScore.objects.filter(
        **persist_kwargs, content__type=content_type
    ).only("content_id", "signals")
    for row in rows:
        writeups = (row.signals or {}).get("writeups")
        if isinstance(writeups, dict) and writeups:
            out[str(row.content_id)] = {
                cluster_id: entry
                for cluster_id, entry in writeups.items()
                if isinstance(entry, dict)
            }
    return out


def carry_stored_writeups(
    signals: dict, stored: Mapping[str, dict], fresh: Mapping[str, dict]
) -> dict:
    """Merge this run's write-ups over whatever the row already held.

    Union rather than replacement: the row keeps reasoning for themes this run
    did not revisit, which is what makes a slate exit free. Only
    :func:`apps.content.slates.prune_cluster_slates` ever deletes one, and only
    when the theme itself is gone.
    """
    merged = {**(stored or {}), **(fresh or {})}
    if merged:
        signals["writeups"] = merged
    else:
        signals.pop("writeups", None)
    return signals


def stored_for(signals: Mapping | None, cluster_id: str) -> dict | None:
    """Convenience re-export so renderers need only one import."""
    return stored_writeup(signals, cluster_id)
