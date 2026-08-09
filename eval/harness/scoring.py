"""TREC run files, `ir_measures` scoring, and the committed results contract.

Never hand-roll a metric. `ir_measures` is the same implementation the LongEval
overview papers score with, so a number produced here is directly comparable to a
published one — which is the entire point of using an external collection.

The results record is the durable artifact. It is small, committed, and keyed by
git SHA so "did the change I made last Tuesday help?" stays answerable months
later. Two fields exist specifically to stop dishonest comparisons:

- `corpus_scope` — `full` or `pooled`. Reordering metrics (nDCG@10) are close
  between the two; **recall metrics are not**. A pooled number is a re-ranking
  result and cannot support a recall claim.
- `dirty` — whether the code that *feeds a run* (the ranking stack in
  `web/backend` and the harness in `eval/`) differed from the recorded commit.
  Such a number is not reproducible and must be visibly marked. Deliberately
  scoped: docs edits cannot move a metric, and the harness's own results/runs
  output would otherwise flag every run in a batch after the first.
"""

from __future__ import annotations

import gzip
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVAL_ROOT / "results"
RUNS_DIR = EVAL_ROOT / "runs"

#: Matched to what the LongEval overview reports, so the numbers line up.
DEFAULT_MEASURES = ["nDCG@10", "nDCG@100", "AP", "R@100", "RR", "P@10"]


@dataclass
class RunRecord:
    """One committed result row."""

    arm: str
    collection: str
    snapshot: str
    qrels: str
    corpus_scope: str  # "full" | "pooled"
    corpus_docs: int
    git_sha: str
    dirty: bool
    config_hash: str
    embedding_model: str | None
    metrics: dict[str, float]
    n_queries: int
    wall_clock_s: float
    timestamp: str
    notes: str = ""
    params: dict = field(default_factory=dict)
    #: Per-topic metrics, when the comparison is paired. Aggregate numbers cannot
    #: carry a confidence interval; the profile ablation compares ~30 profiles
    #: with effect sizes that may be small, so a paired bootstrap needs the rows,
    #: not the mean. Empty for the single-query arms, whose comparison is one
    #: number per snapshot.
    per_query: dict[str, dict[str, float]] = field(default_factory=dict)
    #: Free-form arm diagnostics (e.g. the abstention-floor histogram).
    diagnostics: dict = field(default_factory=dict)

    def filename(self) -> str:
        """A name unique to everything that can change the number.

        `config_hash` is part of it deliberately: two runs of the same arm at the
        same commit but different parameters (say `pool_per_interest` 100 vs
        1000) are *different results*, and leaving it out silently overwrote one
        with the other.
        """
        safe_snapshot = self.snapshot.replace("/", "_")
        return (
            f"{safe_snapshot}__{self.arm}__{self.corpus_scope}"
            f"__{self.qrels}__{self.config_hash}__{self.git_sha}.json"
        )

    def write(self, directory: Path | None = None) -> Path:
        directory = directory or RESULTS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.filename()
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")
        return path


def git_state(repo_root: Path) -> tuple[str, bool]:
    """`(short_sha, dirty)` for the tree the measured code came from."""
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    try:
        sha = run("rev-parse", "--short", "HEAD")
        # Scope dirtiness to what can actually change a number: the ranking
        # stack under test and the harness that drives it. A docs or changelog
        # edit cannot move a metric, and the harness writes its own results and
        # run files as a batch proceeds — counting either would mark almost
        # every run dirty and destroy the flag's meaning.
        status = run(
            "status", "--porcelain", "--",
            "web/backend", "eval",
            ":(exclude)eval/results", ":(exclude)eval/runs", ":(exclude)eval/cache",
        )
        dirty = bool(status.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", True
    return sha, dirty


def write_trec_run(
    ranking: dict[str, list[tuple[str, float]]],
    path: Path,
    *,
    tag: str,
    depth: int = 1000,
) -> Path:
    """Write a standard six-column TREC run file (gzipped).

    `ranking` maps `query_id -> [(doc_id, score), ...]` best first. Ranks are
    re-derived from list order so a caller cannot emit an inconsistent file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        for query_id, hits in ranking.items():
            for rank, (doc_id, score) in enumerate(hits[:depth], start=1):
                handle.write(f"{query_id} Q0 {doc_id} {rank} {score:.6f} {tag}\n")
    return path


def _as_run(ranking: dict[str, list[tuple[str, float]]]) -> dict:
    return {
        query_id: {doc_id: float(sc) for doc_id, sc in hits}
        for query_id, hits in ranking.items()
    }


def score(
    ranking: dict[str, list[tuple[str, float]]],
    dataset,
    *,
    measures: list[str] | None = None,
) -> dict[str, float]:
    """Score a ranking against a dataset's qrels with `ir_measures`."""
    import ir_measures
    from ir_measures import parse_measure

    parsed = [parse_measure(m) for m in (measures or DEFAULT_MEASURES)]
    qrels = list(dataset.qrels_iter())
    results = ir_measures.calc_aggregate(parsed, qrels, _as_run(ranking))
    return {str(measure): float(value) for measure, value in results.items()}


def score_per_topic(
    ranking: dict[str, list[tuple[str, float]]],
    qrels: dict[str, dict[str, int]],
    *,
    measures: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Per-topic `ir_measures` scores against **caller-supplied** qrels.

    The single-query arms score against a collection's own qrels, read straight
    off the dataset. A synthetic profile has no qrels in any collection — its
    judgments are the union of its constituent queries' — so they are passed in.
    The measure implementations are still `ir_measures`; only the judgment set is
    constructed. Returns `topic_id -> {measure: value}`.
    """
    import ir_measures
    from ir_measures import parse_measure

    parsed = [parse_measure(m) for m in (measures or DEFAULT_MEASURES)]
    flat = [
        ir_measures.Qrel(topic_id, doc_id, int(grade))
        for topic_id, judgments in qrels.items()
        for doc_id, grade in judgments.items()
    ]
    out: dict[str, dict[str, float]] = {topic_id: {} for topic_id in ranking}
    for metric in ir_measures.iter_calc(parsed, flat, _as_run(ranking)):
        out.setdefault(metric.query_id, {})[str(metric.measure)] = float(metric.value)
    return out


def aggregate(per_topic: dict[str, dict[str, float]]) -> dict[str, float]:
    """Unweighted mean of per-topic scores — the aggregate a paired test resamples."""
    totals: dict[str, list[float]] = {}
    for scores in per_topic.values():
        for name, value in scores.items():
            totals.setdefault(name, []).append(value)
    return {name: sum(vals) / len(vals) for name, vals in totals.items() if vals}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
