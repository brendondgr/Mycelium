"""TypeSafe rerank of each theme's slate head — the ``RERANK_METHOD`` switch.

Retrieval and fusion (:mod:`.retrieval`, :mod:`.lexical`, :mod:`.fusion`) decide
*which* candidates a target sees and, per theme, in what order; the optional
cross-encoder (:mod:`.reranking`) may reorder the head of that pool. This stage
sits **after** all of it: once each theme's own ranked group exists and before
the slate is cut, it asks TypeSafe's decision model one question per (theme,
item) pair for the top ``TYPESAFE_RERANK_WINDOW`` of every group and reorders
that head by the returned ``worth`` probability, fused position breaking ties.
Nothing below the window moves, nothing is added or dropped, and the pool is
exactly what production already built.

``RERANK_METHOD`` chooses:

* ``local`` — the deployed stack as it was: BM25 + dense fusion, plus the
  cross-encoder when ``RERANK_ENABLED``. Not a line of this module runs.
* ``typesafe`` — the same local stack produces the ordering, then this module
  re-orders each theme's top window. It is the default. Without a
  ``TYPESAFE_API_KEY`` it degrades to ``local`` with one log line, and any
  failed call leaves that whole theme in fused order: a slate is never a mix of
  judged and unjudged rows.

Why one item per call, and why ``worth``
----------------------------------------

Each call carries the reader (the production profile text), the strand (the
theme's label and declared interests) and **one** candidate. The model never
sees the other candidates, so there is no order for it to be biased by (C-015)
and every probability means the same thing across items, which is what makes
sorting by it legitimate. ``worth`` is the yes/no framing; the four-level
``fit`` Score is asked in the same call (a second question is free) and stored,
but it does not decide the order — on LongEval the yes/no framing ordered
significantly better than the rubric (``EXP-2026-09-004``).

What the evidence is, and is not
--------------------------------

On one reader's own grant and conference slates the model's verdicts agreed
with the prose model's on 56 % of pairs and the reader preferred its order
(``EXP-2026-09-003``). On LongEval-Sci over BM25's top 20 it was +0.0185 nDCG@10
with the interval spanning zero — not a measured gain, and the first reranker
in the record whose delta was positive on short queries (``EXP-2026-09-004``,
C-027 refuted as written, Q-040 open). This stage ships on that basis, chosen
by the operator, and every reorder it makes is logged so tonight's run is the
shadow verification.

Reuse
-----

A judgement is keyed on (item, theme, target) and stored on the row at
``signals["typesafe"][cluster_id]`` with a fingerprint of everything that went
into the call — model, question version, profile text, strand, candidate text.
An unchanged pair is served from the previous run's row and costs nothing; the
opportunity feeds are a stock, so most nights most pairs are reused.

What leaves the host: the target's profile text and the candidate's public text,
per pair, to ``api.typesafe.ai``. That is a deployment decision recorded in
``docs/architecture.md``; ``local`` sends nothing anywhere.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.utils import timezone

from tools.recommendation.clustering import Cluster
from tools.recommendation.models import RelevanceScore
from tools.recommendation.verdicts import FILE, READ, SKIM, SKIP, VERDICT_BLURBS
from tools.retrieval.models import ContentItem

logger = logging.getLogger(__name__)

METHOD_LOCAL = "local"
METHOD_TYPESAFE = "typesafe"
METHODS = (METHOD_LOCAL, METHOD_TYPESAFE)

#: Bump whenever a question or the state layout below changes, so stored
#: judgements from the old wording are not reused under the new one.
QUESTION_VERSION = "2026-09-17.1"

DEFAULT_WINDOW = 20
DEFAULT_CONTENT_TYPES = ("paper", "grant", "conference", "fellowship")
DEFAULT_CONCURRENCY = 12
#: Characters of abstract / description per candidate — the same truncation the
#: LongEval arm used, so the deployed state matches what was measured.
TEXT_CHARS = 600

#: Low to high; the Score's level index is 0 = skip … 3 = read.
LEVELS = (SKIP, FILE, SKIM, READ)

Judgement = dict[str, Any]
Groups = Mapping[str, Sequence[str]]


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


def _setting(name: str, default: Any) -> Any:
    from django.conf import settings

    return getattr(settings, name, default)


def method() -> str:
    """``local`` or ``typesafe``; an unknown value is ``local`` with a warning."""
    value = str(_setting("RERANK_METHOD", METHOD_TYPESAFE) or "").strip().lower()
    if value not in METHODS:
        logger.warning("RERANK_METHOD=%r is not one of %s; using local", value, METHODS)
        return METHOD_LOCAL
    return value


def enabled_for(
    content_type: str | None, persist_kwargs: Mapping | None = None
) -> bool:
    """Is the TypeSafe stage on for ``content_type`` and this target?

    Requires ``RERANK_METHOD=typesafe``, a listed content type, a key, and —
    when ``persist_kwargs`` names a target — a plan that carries
    ``Feature.TYPESAFE_RERANK`` (paid tiers; Free keeps the local order). The
    entitlement is read through ``billing.entitlements``, the single read path,
    so with enforcement off it grants everyone. A missing key is logged once per
    process and falls back to ``local``: the nightly run must never fail because
    a sidecar is unconfigured.
    """
    if method() != METHOD_TYPESAFE or not content_type:
        return False
    allowed = _setting("TYPESAFE_RERANK_CONTENT_TYPES", DEFAULT_CONTENT_TYPES)
    if isinstance(allowed, str):
        allowed = [a.strip() for a in allowed.split(",")]
    if content_type not in {str(a) for a in allowed}:
        return False
    if not _setting("TYPESAFE_API_KEY", ""):
        _warn_once("RERANK_METHOD=typesafe but TYPESAFE_API_KEY is empty; using local")
        return False
    if persist_kwargs is not None and not target_is_entitled(persist_kwargs):
        return False
    return True


def target_is_entitled(persist_kwargs: Mapping) -> bool:
    """Paid plans only, through the same gate the prose write-ups use."""
    from apps.billing.entitlements import Feature

    from tools.recommendation.theme_run import target_is_entitled as _entitled

    return _entitled(persist_kwargs, Feature.TYPESAFE_RERANK)


def head_ids(groups: Mapping[str, Sequence[Any]], size: int | None = None) -> list[str]:
    """Every id inside the windows — hits ``(item, score)`` or plain ids."""
    limit = size or window()
    out: list[str] = []
    for members in groups.values():
        for member in list(members)[:limit]:
            out.append(str(member[0].id) if isinstance(member, tuple) else str(member))
    return out


def user_profile_meta(user: Any) -> dict:
    """Career stage and institution, as
    :func:`tools.recommendation.targets.target_for_user`."""
    profile = getattr(user, "profile", None)
    return {
        "academic_title": getattr(profile, "academic_title", "") if profile else "",
        "institution": getattr(profile, "institution", "") if profile else "",
    }


_warned: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        logger.warning(message)


def window() -> int:
    return max(1, int(_setting("TYPESAFE_RERANK_WINDOW", DEFAULT_WINDOW)))


# --------------------------------------------------------------------------- #
# State and questions — the same shapes EXP-2026-09-003 measured
# --------------------------------------------------------------------------- #


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value else ""


def profile_block(interests: Mapping | None, profile_meta: Mapping | None) -> str:
    """The reader, as the opportunity prompts describe them (one shared text)."""
    from tools.recommendation.opportunity_llm import _profile_text

    return _profile_text(dict(interests or {}), dict(profile_meta or {}))


def candidate_block(content_type: str, item: Any) -> dict:
    """Title plus a bounded slice of the item's own text, per content type."""
    meta = getattr(item, "metadata", None) or {}
    if content_type == ContentItem.Type.PAPER:
        return {
            "title": _clean(meta.get("title")) or "(untitled)",
            "abstract": _clean(meta.get("abstract") or meta.get("search_text"))[
                :TEXT_CHARS
            ],
        }
    from tools.recommendation.opportunity_llm import _candidate_brief

    brief = _candidate_brief(content_type, 1, item)
    if brief.startswith("[1] "):
        brief = brief[4:]
    block: dict = {"brief": brief}
    if content_type == ContentItem.Type.GRANT:
        eligibility = meta.get("eligibility")
        if isinstance(eligibility, list):
            eligibility = "; ".join(_clean(e) for e in eligibility if _clean(e))
        block["eligibility"] = _clean(eligibility)[:900]
        applicants = meta.get("applicant_types")
        if isinstance(applicants, list):
            block["applicant_types"] = [_clean(a) for a in applicants if _clean(a)][:12]
    return block


def build_state(profile_text: str, cluster: Cluster, candidate: dict) -> dict:
    return {
        "researcher": profile_text,
        "strand": {"label": cluster.label, "interests": list(cluster.areas)},
        "opportunity": candidate,
    }


def questions_for(content_type: str) -> dict:
    from apps.core.systemone import noul, score

    out = {
        "worth": noul(
            "Is this item worth this researcher's attention today, for this "
            "strand of their work?",
            true=(
                "The item's subject matches this strand's listed interests "
                "specifically enough that the researcher could realistically act "
                "on it — read it, apply, submit, or build on it."
            ),
            false=(
                "The item is generic, aimed at a different field or method, or "
                "matches only a shared word rather than the strand's actual work."
            ),
        ),
        "fit": score(
            "Where does this item sit for THIS strand of the researcher's work? "
            "Judge fit to the strand's listed interests and the researcher's "
            "stated methods, not to the researcher in general.",
            [
                (
                    f"Skip. {VERDICT_BLURBS[SKIP]} Off-topic for this strand, or "
                    "only superficially related."
                ),
                (
                    f"File. {VERDICT_BLURBS[FILE]} On-topic but not something to "
                    "act on now."
                ),
                (
                    f"Skim. {VERDICT_BLURBS[SKIM]} Clearly relevant; worth reading "
                    "the summary to decide."
                ),
                (
                    f"Read. {VERDICT_BLURBS[READ]} A strong, specific match to this "
                    "strand that the researcher should act on."
                ),
            ],
        ),
    }
    if content_type == ContentItem.Type.GRANT:
        out["eligible"] = noul(
            "Can this researcher, at their stated career stage and institution, "
            "plausibly apply to this grant as a principal or co-investigator?",
            true=(
                "The stated eligibility and applicant types include someone in "
                "the researcher's position, or place no restriction that excludes "
                "them."
            ),
            false=(
                "The eligibility text names a category (career stage, institution "
                "type, nationality, organisation) that excludes the researcher."
            ),
        )
    elif content_type == ContentItem.Type.CONFERENCE:
        out["venue_fit"] = noul(
            "Would a paper from this strand be in scope for this conference's "
            "call, as the call describes its topics and tracks?",
            true="The call's scope or tracks name the strand's topics or methods.",
            false=(
                "The call is for a different community; the strand would be out "
                "of scope or a poor fit for the tracks listed."
            ),
        )
    return out


AREA_QUESTION = {
    ContentItem.Type.GRANT: "eligible",
    ContentItem.Type.CONFERENCE: "venue_fit",
}


def fingerprint(model: str, state: Mapping) -> str:
    """Everything that went into a call, so a stored answer is reused only when
    the question it answered is the one being asked."""
    import json

    payload = json.dumps(
        {"m": model, "v": QUESTION_VERSION, "s": state}, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Reuse
# --------------------------------------------------------------------------- #


def prior_judgements(
    persist_kwargs: Mapping, content_type: str, content_ids: Sequence[str]
) -> dict[str, dict[str, Judgement]]:
    """``{content_id: {cluster_id: judgement}}`` from the previous run's rows."""
    if not content_ids:
        return {}
    out: dict[str, dict[str, Judgement]] = {}
    rows = RelevanceScore.objects.filter(
        content__type=content_type, content_id__in=list(content_ids), **persist_kwargs
    ).only("content_id", "signals")
    for row in rows:
        stored = (row.signals or {}).get("typesafe")
        if isinstance(stored, Mapping) and stored:
            out[str(row.content_id)] = {
                k: dict(v) for k, v in stored.items() if isinstance(v, Mapping)
            }
    return out


def attach(
    rows: Sequence[tuple[Any, float, dict]], judgements: Mapping[str, Mapping]
) -> None:
    """Write judgements into the persist rows' ``extra`` so they ride into signals."""
    if not judgements:
        return
    for item, _score, extra in rows:
        found = judgements.get(str(item.id))
        if found:
            extra["typesafe"] = {k: dict(v) for k, v in found.items()}


# --------------------------------------------------------------------------- #
# The reorder
# --------------------------------------------------------------------------- #


def _client(content_type: str):
    from apps.core.systemone import build_systemone_client

    return build_systemone_client(component=f"typesafe_rerank.{content_type}")


def _judgement_from(
    result: Any, content_type: str, fp: str, model: str
) -> Judgement | None:
    answers = result.answers_as_dicts()
    worth = answers.get("worth", {}).get("noul")
    fit = answers.get("fit", {})
    if not isinstance(worth, (int, float)) or "score" not in fit:
        return None
    probabilities = fit.get("probabilities") or {}
    verdict = None
    if probabilities:
        best = max(probabilities.items(), key=lambda kv: kv[1])[0]
        try:
            verdict = LEVELS[int(best)]
        except (ValueError, IndexError):
            verdict = None
    area_key = AREA_QUESTION.get(content_type)
    return {
        "worth": round(float(worth), 4),
        "fit": round(float(fit["score"]), 4),
        "confidence": round(float(fit.get("confidence") or 0.0), 4),
        "verdict": verdict,
        "area": (
            round(float(answers[area_key]["noul"]), 4)
            if area_key and area_key in answers and "noul" in answers[area_key]
            else None
        ),
        "fingerprint": fp,
        "model": model,
        "judged_on": timezone.now().date().isoformat(),
        "reused": False,
    }


def reorder_id_groups(
    groups: Groups,
    *,
    items_by_id: Mapping[str, Any],
    interests: Mapping | None,
    profile_meta: Mapping | None,
    clusters: Sequence[Cluster],
    content_type: str,
    prior: Mapping[str, Mapping[str, Judgement]] | None,
    emit: Callable[[str], None],
    client: Any | None = None,
    window_size: int | None = None,
    concurrency: int | None = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Judgement]]]:
    """Reorder the head of every theme's id list by TypeSafe ``worth``.

    Returns ``(groups, judgements)``. ``groups`` keeps every key and every id;
    only the first ``window_size`` of each theme may change order. A theme with
    any unjudged head item is returned untouched, and said so.
    """
    prior = prior or {}
    size = window_size or window()
    by_cluster = {c.id: c for c in clusters}
    profile_text = profile_block(interests, profile_meta)
    model = str(_setting("TYPESAFE_MODEL", ""))

    # Plan every (theme, item) in the windows; reuse what the fingerprint allows.
    todo: list[tuple[str, str, dict, str]] = []  # (cluster_id, cid, state, fp)
    judgements: dict[str, dict[str, Judgement]] = {}
    reused = 0
    for cluster_id, ids in groups.items():
        cluster = by_cluster.get(cluster_id)
        if cluster is None:
            continue
        for cid in list(ids)[:size]:
            item = items_by_id.get(str(cid))
            if item is None:
                continue
            state = build_state(
                profile_text, cluster, candidate_block(content_type, item)
            )
            fp = fingerprint(model, state)
            stored = (prior.get(str(cid)) or {}).get(cluster_id)
            if (
                stored
                and stored.get("fingerprint") == fp
                and stored.get("worth") is not None
            ):
                kept = dict(stored)
                kept["reused"] = True
                judgements.setdefault(str(cid), {})[cluster_id] = kept
                reused += 1
            else:
                todo.append((cluster_id, str(cid), state, fp))

    asked = failed = 0
    if todo:
        if client is None:
            client = _client(content_type)
        questions = questions_for(content_type)
        workers = max(
            1,
            min(
                concurrency
                or int(_setting("TYPESAFE_RERANK_CONCURRENCY", DEFAULT_CONCURRENCY)),
                len(todo),
            ),
        )

        def one(job):
            cluster_id, cid, state, fp = job
            try:
                result = client.ask(state, questions, model=model or None)
                return (
                    cluster_id,
                    cid,
                    _judgement_from(result, content_type, fp, result.model),
                )
            except Exception as exc:  # noqa: BLE001 — a failed pair is a kept fused position
                logger.warning(
                    "typesafe rerank call failed for %s/%s: %s", cluster_id, cid, exc
                )
                return cluster_id, cid, None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for cluster_id, cid, judgement in pool.map(one, todo):
                asked += 1
                if judgement is None:
                    failed += 1
                else:
                    judgements.setdefault(cid, {})[cluster_id] = judgement

    # Reorder each theme's head; leave a theme alone if any head item is unjudged.
    out: dict[str, list[str]] = {}
    moved_total = skipped = 0
    for cluster_id, ids in groups.items():
        ids = [str(i) for i in ids]
        head, tail = ids[:size], ids[size:]
        cluster = by_cluster.get(cluster_id)
        worths = {
            cid: (judgements.get(cid) or {}).get(cluster_id, {}).get("worth")
            for cid in head
        }
        if cluster is None or not head or any(w is None for w in worths.values()):
            out[cluster_id] = ids
            if cluster is not None and head:
                skipped += 1
            continue
        position = {cid: i for i, cid in enumerate(head)}
        reordered = sorted(head, key=lambda cid: (-worths[cid], position[cid]))
        moved = sum(1 for a, b in zip(head, reordered, strict=True) if a != b)
        moved_total += moved
        out[cluster_id] = reordered + tail
        emit(f"typesafe {cluster.label}: top-{len(head)} reordered, {moved} moved")
    emit(
        f"typesafe rerank ({content_type}): {asked} asked, {reused} reused, "
        f"{failed} failed, {moved_total} moved"
        + (f", {skipped} theme(s) left in fused order" if skipped else "")
    )
    return out, judgements


def reorder_slate_groups(
    slate_groups: Mapping[str, Sequence[tuple[Any, float]]],
    **kwargs: Any,
) -> tuple[dict[str, list[tuple[Any, float]]], dict[str, dict[str, Judgement]]]:
    """The :func:`reorder_id_groups` wrapper for ``{cluster_id: [(item, score)]}``."""
    hits_by_id: dict[str, tuple[Any, float]] = {}
    id_groups: dict[str, list[str]] = {}
    for cluster_id, hits in slate_groups.items():
        ids = []
        for hit in hits:
            cid = str(hit[0].id)
            hits_by_id[cid] = hit
            ids.append(cid)
        id_groups[cluster_id] = ids
    items_by_id = {cid: hit[0] for cid, hit in hits_by_id.items()}
    new_ids, judgements = reorder_id_groups(
        id_groups, items_by_id=items_by_id, **kwargs
    )
    return (
        {
            cluster_id: [hits_by_id[cid] for cid in ids]
            for cluster_id, ids in new_ids.items()
        },
        judgements,
    )
