"""`Q-001` — does the union pool's advantage survive on the *production* corpus?

    docker compose up -d postgres
    uv run --project eval python \
      docs/research/experiments/EXP-2026-08-013-production-pool-contrast/code/run.py

Twelve experiments measured the pool contrast on LongEval-Sci, which is
`query -> documents`. This one runs it on the real `ContentItem` store against
the real declared interests of the real targets, which is `profile -> feed`.

There are no relevance judgments for this corpus (W5 is not started), so this
answers the *mechanism* half of `Q-001` — is there anything for a wider pool to
reach, and does it survive the deployed surfacing gates — and leaves the value
half explicitly open. See `PROTOCOL.md` §2 for why that asymmetry is the design
rather than a shortfall.

Writes `data/metrics.json`, `data/metrics.csv`, and `data/per_interest.csv`.
No LLM, no network.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(REPO_ROOT / "data" / "eval-cache" / "fastembed")
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

POOL_PER_INTEREST = 100
ARMS = ("a2_union_harness", "a2p_union_prod", "a3_union_fts", "a4_union_fts_or")
BETA = 0.15

#: Targets whose declared areas are plausibly a real researcher's rather than a
#: development fixture's. Fixed in PROTOCOL.md before any arm was scored.
REAL_TARGETS = {"user:brendondgr", "user:bdgr", "user:bdgr2", "lab:PULSE Lab"}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> int:
    import django

    django.setup()

    import numpy as np
    from apps.content import embeddings
    from apps.content.interests_query import search_interests
    from apps.content.lexical import _TOKEN_RE
    from apps.content.models import ContentItem
    from apps.content.retrieval import PgVectorIndex
    from apps.content.search import _search_query
    from django.contrib.postgres.search import SearchQuery, SearchRank
    from django.db.models import F

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import production_pool as pp

    # ---------------------------------------------------------------- gate 1
    probe = ContentItem.objects.filter(
        type=ContentItem.Type.PAPER, embedding__isnull=False
    ).first()
    meta = probe.metadata or {}
    probe_text = meta.get("search_text") or f"{meta.get('title', '')} {meta.get('abstract', '')}"
    probe_vec = embeddings.embed_text(probe_text)
    if probe_vec is None:
        log("FATAL: no embedder available")
        return 1
    a = np.asarray(probe_vec, dtype=np.float64)
    b = np.asarray(probe.embedding, dtype=np.float64)
    alignment = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    log(f"gate: embedder alignment cosine = {alignment:.10f}")
    if alignment < 0.999:
        log("FATAL: query-side and corpus-side embedders disagree; experiment void")
        return 1

    # ---------------------------------------------------------------- targets
    targets = load_targets()
    log(f"{len(targets)} targets, {sum(len(t['interests']) for t in targets)} interests")

    # ---------------------------------------------------------------- regimes
    regimes = build_regimes(ContentItem)
    only = os.environ.get("MYCELIUM_REGIMES")
    if only:
        wanted = tuple(only.split(","))
        regimes = [r for r in regimes if r["id"].startswith(wanted)]
    log("regimes: " + ", ".join(f"{r['id']}({r['corpus_size']})" for r in regimes))

    embed_cache: dict[str, list[float] | None] = {}

    def embed(text: str):
        if text not in embed_cache:
            embed_cache[text] = embeddings.embed_text(text)
        return embed_cache[text]

    per_interest_rows: list[dict] = []
    per_target_rows: list[dict] = []

    for regime in regimes:
        corpus = list(regime["queryset"])
        if not corpus:
            log(f"{regime['id']}: empty scope, skipped")
            continue
        log(f"{regime['id']}: building corpus-wide BM25 over {len(corpus)} docs …")
        bm25_topk = memoize(pp.bm25_lexical(corpus))

        base_qs = regime["queryset"]

        def _fts(query, limit, _base=base_qs):
            rows = (
                _base.filter(search_vector=query)
                .annotate(lex_rank=SearchRank(F("search_vector"), query))
                .order_by("-lex_rank", "id")[:limit]
            )
            return [(item, 1.0 / (rank + 1)) for rank, item in enumerate(rows)]

        @memoize
        def fts_topk(query_text: str, limit: int):
            """`/api/search/`'s channel verbatim — `websearch`, which ANDs terms."""
            return _fts(_search_query(query_text), limit)

        @memoize
        def fts_or_topk(query_text: str, limit: int):
            """The same index under OR semantics.

            `websearch` ANDs unquoted terms, which is right for a query somebody
            typed and wrong for an interest carrying a keyword suffix — every term
            must appear. This is the fair test of whether the *index* can serve as
            the corpus-wide lexical channel, separated from the query syntax
            `/api/search/` happens to use.
            """
            tokens = [t for t in _TOKEN_RE.findall(query_text.casefold()) if t]
            if not tokens:
                return []
            return _fts(SearchQuery(" | ".join(tokens), search_type="raw"), limit)

        index = PgVectorIndex(
            content_type=regime["content_type"], created_on=regime["created_on"]
        )
        # Embeddings of every in-scope document, for completing the cosine gate
        # over union-only candidates (see RESULTS.md §3).
        emb_by_id = {
            str(item.id): np.asarray(item.embedding, dtype=np.float32)
            for item in corpus
            if item.embedding is not None
        }

        for target in targets:
            search_ints = search_interests(target["raw_interests"])
            if not search_ints:
                continue

            a1_pool, a1_scores, a1_cos = pp.dense_pool(
                search_ints, index=index, pool_per_interest=POOL_PER_INTEREST
            )
            a2_pool, a2_scores, a2_cos = pp.union_pool_harness(
                search_ints,
                index=index,
                pool_per_interest=POOL_PER_INTEREST,
                lexical_topk=bm25_topk,
                embed=embed,
            )
            a2p_pool, a2p_scores, a2p_cos = pp.union_pool_prod(
                search_ints,
                index=index,
                pool_per_interest=POOL_PER_INTEREST,
                lexical_topk=bm25_topk,
                embed=embed,
            )
            a3_pool, a3_scores, a3_cos = pp.union_pool_prod(
                search_ints,
                index=index,
                pool_per_interest=POOL_PER_INTEREST,
                lexical_topk=fts_topk,
                embed=embed,
            )
            a4_pool, a4_scores, a4_cos = pp.union_pool_prod(
                search_ints,
                index=index,
                pool_per_interest=POOL_PER_INTEREST,
                lexical_topk=fts_or_topk,
                embed=embed,
            )

            # ---- primary: how much of corpus-wide BM25's top-100 is already in
            #      the dense pool the deployed builder would have used?
            for interest in search_ints:
                lex = bm25_topk(interest.query_text, POOL_PER_INTEREST)
                fts = fts_topk(interest.query_text, POOL_PER_INTEREST)
                fts_or = fts_or_topk(interest.query_text, POOL_PER_INTEREST)
                per_interest_rows.append({
                    "regime": regime["id"],
                    "scope_size": len(corpus),
                    "target": target["key"],
                    "real_target": target["key"] in REAL_TARGETS,
                    "interest": interest.label,
                    "interest_words": len(interest.label.split()),
                    "bm25_hits": len(lex),
                    "bm25_reachability": reachability(lex, a1_pool),
                    "fts_hits": len(fts),
                    "fts_reachability": reachability(fts, a1_pool),
                    "fts_or_hits": len(fts_or),
                    "fts_or_reachability": reachability(fts_or, a1_pool),
                    "emitted_after_floor": len(a1_scores.get(interest.label, {})),
                    "emitted_after_floor_union": len(a2p_scores.get(interest.label, {})),
                })

            # ---- secondary: does anything reach the reader?
            a1_surfaced = set(
                surface(a1_scores, a1_pool, a1_cos, regime["threshold"])
            )
            row = {
                "regime": regime["id"],
                "scope_size": len(corpus),
                "target": target["key"],
                "real_target": target["key"] in REAL_TARGETS,
                "n_interests": len(search_ints),
                "threshold": regime["threshold"],
                "dense_pool": len(a1_pool),
            }
            for arm, (pool, scores, cos) in {
                "a1_dense": (a1_pool, a1_scores, a1_cos),
                "a2_union_harness": (a2_pool, a2_scores, a2_cos),
                "a2p_union_prod": (a2p_pool, a2p_scores, a2p_cos),
                "a3_union_fts": (a3_pool, a3_scores, a3_cos),
                "a4_union_fts_or": (a4_pool, a4_scores, a4_cos),
            }.items():
                row[f"{arm}__pool"] = len(pool)
                row[f"{arm}__novel"] = len(set(pool) - set(a1_pool))
                # As deployed: the cosine gate is populated only by the dense
                # channel, so a union-only candidate is gated at 0.0.
                deployed = surface(scores, pool, cos, regime["threshold"])
                # As a correct fix would: complete the gate over the whole pool.
                completed_cos = dict(cos)
                if arm != "a1_dense":
                    complete_cosines(
                        completed_cos, pool, search_ints, embed, emb_by_id, np
                    )
                fixed = surface(scores, pool, completed_cos, regime["threshold"])
                row[f"{arm}__surfaced_deployed_gate"] = len(deployed)
                row[f"{arm}__surfaced_completed_gate"] = len(fixed)
                deployed_entrants = set(deployed) - a1_surfaced
                row[f"{arm}__entrants_deployed_gate"] = len(deployed_entrants)
                # The invariant worth measuring rather than arguing: under the
                # deployed gate a union-only candidate carries no cosine at all,
                # so it is compared at 0.0 and can never clear the threshold.
                row[f"{arm}__entrants_deployed_union_only"] = len(
                    deployed_entrants - set(a1_pool)
                )
                entrants = set(fixed) - a1_surfaced
                row[f"{arm}__entrants_completed_gate"] = len(entrants)
                row[f"{arm}__entrants_union_only"] = len(entrants - set(a1_pool))
                row[f"{arm}__entrants_reordered_in"] = len(entrants & set(a1_pool))
            row["a1_surfaced"] = len(a1_surfaced)
            per_target_rows.append(row)
            log(
                f"  {regime['id']} {target['key']}: dense pool {len(a1_pool)} -> "
                f"union {len(a2p_pool)} (+{len(set(a2p_pool) - set(a1_pool))}); "
                f"surfaced {len(a1_surfaced)}"
            )

    write_outputs(per_interest_rows, per_target_rows)
    return 0


def memoize(fn):
    """Cache a lexical channel per ``(query_text, limit)``.

    Each channel is asked for the same interest several times per target — once
    per arm that uses it, once for the reachability row — and the underlying call
    is a full-corpus BM25 scoring pass or a database round trip. The cache is
    per-regime because the closures are rebuilt per regime.
    """
    cache: dict[tuple[str, int], list] = {}

    def wrapped(query_text: str, limit: int):
        key = (query_text, limit)
        if key not in cache:
            cache[key] = fn(query_text, limit)
        return cache[key]

    return wrapped


def reachability(hits, dense_pool) -> float | None:
    """Fraction of a corpus-wide lexical top-k already inside the dense pool."""
    if not hits:
        return None
    inside = sum(1 for item, _ in hits if str(item.id) in dense_pool)
    return inside / len(hits)


def complete_cosines(cos, pool, search_ints, embed, emb_by_id, np) -> None:
    """Fill the cosine gate for every pool member, not only the dense hits.

    The deployed builder records ``best_cosine`` only for candidates the dense
    channel returned, so a union-only candidate is gated at 0.0 and can never
    clear ``PAPER_MATCH_THRESHOLD``. Any real fix has to compute it; this is that
    computation, and the gap between the two is reported rather than hidden.
    """
    keys = [k for k in pool if k in emb_by_id]
    if not keys:
        return
    matrix = np.stack([emb_by_id[k] for k in keys])
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    for interest in search_ints:
        vector = embed(interest.embed_text)
        if vector is None:
            continue
        q = np.asarray(vector, dtype=np.float32)
        q = q / np.linalg.norm(q)
        sims = matrix @ q
        for key, sim in zip(keys, sims, strict=True):
            value = float(max(0.0, min(1.0, sim)))
            if value > cos.get(key, 0.0):
                cos[key] = value


def surface(scores, pool, best_cosine, threshold) -> list[str]:
    """The deployed threshold-mode surfacing, mirrored from `fuse_interests_pool`."""
    from apps.content.fusion import combine_interests

    if not scores:
        return []
    combined = combine_interests(scores, pool, beta=BETA)
    return [
        str(hit.item.id)
        for hit in combined
        if best_cosine.get(str(hit.item.id), 0.0) >= threshold
    ]


def load_targets() -> list[dict]:
    """Every profile in the store carrying at least one declared area."""
    from apps.accounts.models import LabProfile, Profile
    from apps.content.interests_query import search_interests
    from apps.content.models import ProjectProfile

    out: list[dict] = []
    for profile in Profile.objects.select_related("user"):
        out.append(("user:" + profile.user.get_username(), profile.interests))
    for profile in LabProfile.objects.select_related("lab"):
        out.append(("lab:" + profile.lab.name, profile.interests))
    for profile in ProjectProfile.objects.all():
        out.append((f"project:{profile.pk}", profile.interests))

    targets = []
    for key, interests in out:
        ints = search_interests(interests or {})
        if ints:
            targets.append({"key": key, "raw_interests": interests, "interests": ints})
    return sorted(targets, key=lambda t: t["key"])


def build_regimes(ContentItem) -> list[dict]:
    """R1 (papers per gather day), R2 (papers corpus-wide), R3 (opportunities)."""
    from django.conf import settings

    papers = ContentItem.objects.filter(
        type=ContentItem.Type.PAPER, embedding__isnull=False
    )
    paper_threshold = getattr(settings, "PAPER_MATCH_THRESHOLD", 0.5)

    regimes: list[dict] = []
    for day in papers.dates("created_at", "day"):
        qs = papers.filter(created_at__date=day)
        regimes.append({
            "id": f"R1:papers:{day.isoformat()}",
            "queryset": qs,
            "content_type": ContentItem.Type.PAPER,
            "created_on": day,
            "corpus_size": qs.count(),
            "threshold": paper_threshold,
        })
    regimes.append({
        "id": "R2:papers:corpus",
        "queryset": papers,
        "content_type": ContentItem.Type.PAPER,
        "created_on": None,
        "corpus_size": papers.count(),
        "threshold": paper_threshold,
    })
    for content_type, setting in (
        (ContentItem.Type.GRANT, "GRANT_MATCH_THRESHOLD"),
        (ContentItem.Type.CONFERENCE, "CONFERENCE_MATCH_THRESHOLD"),
        (ContentItem.Type.FELLOWSHIP, "FELLOWSHIP_MATCH_THRESHOLD"),
    ):
        qs = ContentItem.objects.filter(type=content_type, embedding__isnull=False)
        regimes.append({
            "id": f"R3:{content_type}:corpus",
            "queryset": qs,
            "content_type": content_type,
            "created_on": None,
            "corpus_size": qs.count(),
            "threshold": getattr(settings, setting, 0.4),
        })
    return regimes


def write_outputs(per_interest_rows: list[dict], per_target_rows: list[dict]) -> None:
    data = EXP_DIR / "data"
    data.mkdir(exist_ok=True)
    _write_csv(data / "per_interest.csv", per_interest_rows)
    _write_csv(data / "metrics.csv", per_target_rows)

    def med(values):
        values = [v for v in values if v is not None]
        return statistics.median(values) if values else None

    by_regime: dict[str, list[dict]] = defaultdict(list)
    for row in per_interest_rows:
        by_regime[row["regime"]].append(row)

    summary = {
        "n_targets": len({r["target"] for r in per_target_rows}),
        "n_interests": len({r["interest"] for r in per_interest_rows}),
        "bm25_reachability_median_overall": med(
            [r["bm25_reachability"] for r in per_interest_rows]
        ),
        "bm25_reachability_median_real_targets": med(
            [r["bm25_reachability"] for r in per_interest_rows if r["real_target"]]
        ),
        "fts_reachability_median_overall": med(
            [r["fts_reachability"] for r in per_interest_rows]
        ),
        "fts_or_reachability_median_overall": med(
            [r["fts_or_reachability"] for r in per_interest_rows]
        ),
        "fts_queries_returning_nothing": sum(
            1 for r in per_interest_rows if r["fts_hits"] == 0
        ),
        "by_regime": {
            regime: {
                "scope_size": rows[0]["scope_size"],
                "n_interest_queries": len(rows),
                "bm25_reachability_median": med([r["bm25_reachability"] for r in rows]),
                "fts_reachability_median": med([r["fts_reachability"] for r in rows]),
                "fts_or_reachability_median": med(
                    [r["fts_or_reachability"] for r in rows]
                ),
                "emitted_after_floor_median": med(
                    [r["emitted_after_floor"] for r in rows]
                ),
            }
            for regime, rows in sorted(by_regime.items())
        },
        "entrants": {
            arm: {
                "deployed_gate_total": sum(
                    r[f"{arm}__entrants_deployed_gate"] for r in per_target_rows
                ),
                "deployed_gate_union_only_total": sum(
                    r[f"{arm}__entrants_deployed_union_only"] for r in per_target_rows
                ),
                "completed_gate_total": sum(
                    r[f"{arm}__entrants_completed_gate"] for r in per_target_rows
                ),
                "union_only_total": sum(
                    r[f"{arm}__entrants_union_only"] for r in per_target_rows
                ),
                "reordered_in_total": sum(
                    r[f"{arm}__entrants_reordered_in"] for r in per_target_rows
                ),
                "pairs_with_any_union_only_entrant": sum(
                    1 for r in per_target_rows if r[f"{arm}__entrants_union_only"] > 0
                ),
                "pairs": len(per_target_rows),
            }
            for arm in ARMS
        },
    }
    (data / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
