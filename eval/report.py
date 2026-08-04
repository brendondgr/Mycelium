"""Regenerate the `docs/evaluation.md` leaderboard from `eval/results/`.

    uv run --project eval eval/report.py

The table is **generated, never hand-written**. A hand-maintained number drifts
from the run that produced it, and a drifted number is worse than none — the same
failure mode as the "multi-agent" docstring this work also corrected.

Everything between the two marker comments in `docs/evaluation.md` is replaced;
the prose around them (in particular the claims boundary) is preserved.
"""

from __future__ import annotations

import json
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
RESULTS = EVAL_ROOT / "results"
TARGET = REPO_ROOT / "docs" / "evaluation.md"

BEGIN = "<!-- BEGIN GENERATED LEADERBOARD -->"
END = "<!-- END GENERATED LEADERBOARD -->"

COLUMNS = ["nDCG@10", "nDCG@100", "AP", "R@100", "RR", "P@10"]


def _load_baselines() -> list[dict]:
    """Third-party published baselines, if any have been scored."""
    path = EVAL_ROOT / "baselines.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("baselines", [])


def load() -> list[dict]:
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        rows.append(json.loads(path.read_text()))
    return rows


def _table(rows: list[dict]) -> list[str]:
    header = "| Arm | Corpus | Docs | Queries | " + " | ".join(COLUMNS) + " | Run |"
    sep = "|---|---|---:|---:|" + "---:|" * len(COLUMNS) + "---|"
    lines = [header, sep]
    for row in rows:
        cells = []
        for column in COLUMNS:
            value = row["metrics"].get(column)
            cells.append("—" if value is None else f"{value:.4f}")
        flag = " ⚠️dirty" if row.get("dirty") else ""
        lines.append(
            f"| `{row['arm']}` | {row['corpus_scope']} | {row['corpus_docs']:,} | "
            f"{row['n_queries']} | "
            + " | ".join(cells)
            + f" | `{row['git_sha']}`{flag} |"
        )
    return lines


def render(rows: list[dict]) -> str:
    if not rows:
        return f"{BEGIN}\n\n_No runs recorded yet._\n\n{END}"

    out = [BEGIN, ""]
    by_group: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        by_group.setdefault((row["snapshot"], row["qrels"]), []).append(row)

    for (snapshot, qrels), group in sorted(by_group.items()):
        group.sort(key=lambda r: (r["corpus_scope"], r["arm"]))
        out.append(f"### `{snapshot}` — qrels `{qrels}`")
        out.append("")
        out.extend(_table(group))
        out.append("")

    baselines = _load_baselines()
    if baselines:
        out.append("### Published baselines (external, for comparison)")
        out.append("")
        out.append(
            "Scored by this harness with the same `ir_measures` call used above, "
            "from the LongEval'26 organizers' own published runs — not numbers "
            "quoted from a paper."
        )
        out.append("")
        header = "| System | Snapshot | qrels | " + " | ".join(COLUMNS) + " |"
        out.append(header)
        out.append("|---|---|---|" + "---:|" * len(COLUMNS))
        for base in baselines:
            cells = [
                "—" if base["metrics"].get(c) is None else f"{base['metrics'][c]:.4f}"
                for c in COLUMNS
            ]
            out.append(
                f"| {base['name']} | `{base['snapshot']}` | {base['qrels']} | "
                + " | ".join(cells)
                + " |"
            )
        out.append("")

    scopes = {row["corpus_scope"] for row in rows}
    if len(scopes) > 1:
        out.append(
            "> **Do not compare across corpus scopes.** A `pooled` row is a "
            "re-ranking result over the judged set plus a lexical pool; a `full` "
            "row ranks the entire snapshot. Reordering metrics (nDCG@10) are "
            "broadly comparable, recall metrics are not."
        )
        out.append("")
    out.append(END)
    return "\n".join(out)


def main() -> int:
    rows = load()
    block = render(rows)
    text = TARGET.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{TARGET} is missing the generated-block markers")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    TARGET.write_text(head + block + tail)
    print(f"wrote {len(rows)} run(s) into {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
