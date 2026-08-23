"""Per-theme orchestration: slates in, write-ups out.

The join between the deterministic half of the run (retrieve → fuse → slate per
cluster) and the model half (:mod:`.comprehension`, :mod:`.cluster_fit`). It is
the one place that decides *which* (cluster, item) pairs are worth a model call,
and it answers that with three rules in order:

1. **Reuse first.** A pair that already has a current write-up is served from
   store. A second run over an unchanged profile therefore makes zero model
   calls, and an item re-entering a slate makes zero as well — it is badged new
   again, which is the correct existing semantics, but "new to the reader's
   attention" is not "new to Mylo".
2. **Entitlement second.** Model reasoning is a paid layer. An unentitled target
   never reaches a prompt at all, and gets the deterministic write-up, which is
   the baseline product rather than a degraded one.
3. **Budget third.** Whatever is left is ordered priority-first — entrants ahead
   of standing members, then by position within the theme — and cut at the run
   budget. What does not fit carries to the next run rather than being dropped.

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
)
from .clustering import Cluster
from .comprehension import comprehend
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


def target_is_entitled(persist_kwargs: Mapping) -> bool:
    """Whether this target's plan includes model-written reasoning.

    The gate sits *before* any call, not after — the moment per-cluster budgets
    multiply calls per user, an unfiltered selection turns a pricing gap into a
    cost problem. A lab or project target inherits the entitlement of the plan
    that covers it; where no user can be resolved (a lab with no owner in the
    call site's hands) the deterministic path is chosen, which is safe in the
    direction that matters.
    """
    from apps.billing.entitlements import Feature, has_feature

    user = persist_kwargs.get("target_user")
    if user is not None:
        return has_feature(user, Feature.LLM_FIT_SCORING)

    lab = persist_kwargs.get("target_lab")
    project = persist_kwargs.get("target_project")
    scope_lab = lab if lab is not None else getattr(project, "scope_lab", None)
    if scope_lab is not None:
        return _lab_entitled(scope_lab)
    owner = getattr(project, "scope_user", None)
    if owner is not None:
        return has_feature(owner, Feature.LLM_FIT_SCORING)
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
    """Produce a write-up for every (cluster, item) pair in ``slates``.

    ``slates`` is :func:`apps.content.slates.compute_cluster_slates`' output
    (``{content_id: {cluster_id: entry}}``) and ``rows_by_id`` maps a content id
    to the item and the signals this run computed for it, so evidence is built
    from the fusion's own numbers rather than re-derived.

    ``reuse=False`` bypasses the store and re-writes every pair. It is what a
    profile edit needs — the judgement was made against different interests, so
    it is now answering the wrong question — and it is deliberately the *only*
    way to spend the budget on something already written.
    """
    result = ThemeRunResult()
    if not slates:
        return result
    by_id = {cluster.id: cluster for cluster in clusters}
    labels = {cluster.id: cluster.label for cluster in clusters}
    fingerprints = {c.id: areas_fingerprint(c.areas) for c in clusters}
    depth = slate_depth(content_type)
    result.entitled = (
        target_is_entitled(persist_kwargs) if entitled is None else entitled
    )
    stored = _stored_writeups(persist_kwargs, content_type)

    # Pass one: reuse, and collect what still needs writing.
    pending: list[tuple[str, str, Candidate]] = []  # (cluster_id, cid, candidate)
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
            if reuse and is_current(existing, fingerprints[cluster_id]):
                result.writeups.setdefault(cid, {})[cluster_id] = existing
                result.reused += 1
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

    if not pending:
        return result

    # Pass two: order priority-first across all themes jointly and cut at budget.
    # Jointly, not per theme, so one noisy theme cannot starve the others, and
    # independently of slate depth, so depth never becomes a cost dial.
    cap = writeup_budget() if budget is None else budget
    pending.sort(
        key=lambda triple: (
            0 if triple[2].evidence.is_new else 1,
            triple[2].evidence.position,
        )
    )
    funded = pending[:cap] if result.entitled else []
    unfunded = pending[len(funded) :]
    result.carried = len(unfunded) if result.entitled else 0

    if funded:
        precis = comprehend(
            [candidate.item for _cluster_id, _cid, candidate in funded],
            complete=complete,
        )
        by_cluster: dict[str, list[Candidate]] = {}
        for cluster_id, cid, candidate in funded:
            candidate.precis = precis.get(cid)
            by_cluster.setdefault(cluster_id, []).append(candidate)
        for cluster_id, candidates in by_cluster.items():
            cluster = by_id[cluster_id]
            written = write_cluster_fits(
                profile_text,
                cluster,
                [c.label for c in clusters if c.id != cluster_id],
                candidates,
                depth=depth,
                complete=complete,
                seed=seed,
            )
            for cid, writeup in written.items():
                result.writeups.setdefault(cid, {})[cluster_id] = writeup
                if writeup.get("source") == "llm":
                    result.written += 1
                else:
                    result.deterministic += 1

    # Pass three: everything not funded still gets a complete write-up.
    for cluster_id, cid, candidate in unfunded:
        if cluster_id in result.writeups.get(cid, {}):
            continue
        result.writeups.setdefault(cid, {})[cluster_id] = deterministic_writeup(
            candidate.item,
            by_id[cluster_id],
            candidate.evidence,
            depth=depth,
            fingerprint=fingerprints[cluster_id],
        )
        result.deterministic += 1
    return result


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
