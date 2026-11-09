"""EXP-2026-11-004: full-text coverage of the live paper corpus, free sources.

Run from web/backend (see PROTOCOL.md):

    uv run --no-sync --directory web/backend python ../../<exp>/run.py \
        --sample 200 --out ../../<exp>/data

Reads the corpus (read-only), freezes a deterministic sample, runs the
full-text engine on it with this instance's configuration, a fresh cache and
in-process state, and writes the per-paper results and the metrics. Writes
nothing to the app database or to the tool's store.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

from tools.fulltext import config  # noqa: E402
from tools.fulltext.engine.pipeline import Engine  # noqa: E402
from tools.fulltext.engine.state import MemoryState  # noqa: E402

SALT = "fulltext-coverage-2026-11"


def draw(n: int) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id::text, metadata->>'doi', metadata->>'pmid', "
            "metadata->>'pmcid', metadata->>'arxiv', metadata->>'year', source "
            "FROM content_contentitem WHERE type = 'paper' "
            "ORDER BY md5(id::text || %s) LIMIT %s",
            [SALT, n],
        )
        rows = cur.fetchall()
    out = []
    for pk, doi, pmid, pmcid, arxiv, year, source in rows:
        ident = {k: v for k, v in (("doi", doi), ("pmid", pmid), ("pmcid", pmcid),
                                   ("arxiv", arxiv)) if v}
        out.append({"id": pk, "corpus_source": source, "year": year, "identifier": ident})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sample = draw(args.sample)
    (args.out / "sample.json").write_text(json.dumps(sample, indent=1))

    cache = Path(tempfile.mkdtemp(prefix="fulltext-coverage-"))
    engine = Engine(config.credentials(), cache, state=MemoryState(),
                    order=config.source_order(), min_chars=500, workers=4)
    live = [s["source"] for s in engine.sources() if s["available"]]
    off = {s["source"]: s["reason"] for s in engine.sources() if not s["available"]}

    # An item with no identifier at all cannot be asked for; it stays in the
    # denominator as invalid_identifier, which is what the tool would answer.
    t0 = time.time()
    results = engine.fetch([s["identifier"] or "" for s in sample])
    wall = time.time() - t0

    with (args.out / "results.jsonl").open("w") as fh:
        for s, r in zip(sample, results, strict=True):
            fh.write(json.dumps({
                "id": s["id"], "corpus_source": s["corpus_source"], "year": s["year"],
                "ids": r.get("ids"), "status": r["status"], "source": r.get("source"),
                "chars": r.get("chars"), "attempts": r.get("attempts"),
                "explanation": r.get("explanation"),
            }) + "\n")

    n = len(results)
    status = Counter(r["status"] for r in results)
    full = [r for r in results if r["status"] == "full_text"]
    by_source = Counter(r["source"] for r in full)
    with_pmc = [r for r in results if (r.get("ids") or {}).get("pmcid")]
    without_pmc = [r for r in results if not (r.get("ids") or {}).get("pmcid")]

    def rate(rows):
        return round(sum(r["status"] == "full_text" for r in rows) / len(rows), 4) if rows else 0.0

    values = {"full_text_rate": {"mean": rate(results), "n": n}}
    for src, k in sorted(by_source.items()):
        values[f"full_text_by_source.{src}"] = {"mean": round(k / n, 4), "n": n}
    for st, k in sorted(status.items()):
        values[f"status.{st}"] = k
    values["full_text_rate_with_pmcid"] = {"mean": rate(with_pmc), "n": len(with_pmc)}
    values["full_text_rate_without_pmcid"] = {"mean": rate(without_pmc),
                                              "n": len(without_pmc)}
    values["median_chars"] = int(statistics.median(r["chars"] for r in full)) if full else 0
    values["wall_clock_seconds"] = round(wall, 1)

    metrics = {"primary": "full_text_rate", "values": values,
               "sources_live": live, "sources_off": off, "sample": n, "salt": SALT}
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    with (args.out / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value", "n"])
        for k, v in values.items():
            w.writerow([k, v["mean"], v["n"]] if isinstance(v, dict) else [k, v, n])

    table = ["| Metric | Value | n |", "|---|---|---|"]
    for k, v in values.items():
        table.append(f"| `{k}` | {v['mean'] if isinstance(v, dict) else v} | "
                     f"{v['n'] if isinstance(v, dict) else n} |")
    tables = HERE / "tables"
    tables.mkdir(exist_ok=True)
    (tables / "summary.md").write_text(
        "<!-- generated by run.py from data/metrics.json -->\n"
        + "\n".join(table) + "\n\n"
        + f"Sources on: {', '.join(live)}. Off: "
        + "; ".join(f"{s} ({why})" for s, why in off.items()) + ".\n")
    print(json.dumps(values, indent=1))


if __name__ == "__main__":
    main()
