"""EXP-2026-11-005: full-text coverage of EXP-2026-11-004's sample, own PubMed ids.

Run from web/backend (see PROTOCOL.md):

    uv run --no-sync --directory web/backend python ../../<exp>/run.py

Loads the frozen sample, corrects PubMed-sourced papers' ids with the repair's
own decision code (what ``repair_pubmed_ids --apply`` writes), and runs the
full-text engine twice: on all 200 papers with corrected ids (own) and on the
papers whose ids changed with their stored ids (stored, the same-day control).
Writes nothing to the app database or to the tool's store.
"""

from __future__ import annotations

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

from tools.fulltext import config  # noqa: E402
from tools.fulltext.engine.pipeline import Engine  # noqa: E402
from tools.fulltext.engine.state import MemoryState  # noqa: E402
from tools.retrieval.pubmed_repair import (  # noqa: E402
    RepairStats,
    _decide,
    efetch_client,
    parse_own_ids,
)
from tools.retrieval.sources.record import normalize_doi, normalize_pmcid  # noqa: E402


def own_ids(sample: list[dict]) -> list[dict]:
    """Each paper's identifier dict as the repaired corpus would hold it."""
    pubmed = [s for s in sample
              if s["corpus_source"] == "PubMed" and s["identifier"].get("pmid")]
    fetched = parse_own_ids(efetch_client()([s["identifier"]["pmid"] for s in pubmed]))
    out = []
    for s in sample:
        ident = dict(s["identifier"])
        ids = fetched.get(ident.get("pmid")) if s in pubmed else None
        if ids is not None:
            stats = RepairStats()
            doi = _decide(stats, "doi", normalize_doi(ident.get("doi")),
                          ids.doi, ids.ref_dois)
            pmc = _decide(stats, "pmcid", normalize_pmcid(ident.get("pmcid")),
                          ids.pmcid, ids.ref_pmcids)
            ident.pop("doi", None)
            ident.pop("pmcid", None)
            if doi:
                ident["doi"] = doi
            if pmc:
                ident["pmcid"] = pmc
        out.append(ident)
    return out


def _same(a: dict, b: dict) -> bool:
    def norm(d):
        return (normalize_doi(d.get("doi")), d.get("pmid"),
                normalize_pmcid(d.get("pmcid")), d.get("arxiv"))
    return norm(a) == norm(b)


def engine() -> Engine:
    cache = Path(tempfile.mkdtemp(prefix="fulltext-coverage-own-"))
    return Engine(config.credentials(), cache, state=MemoryState(),
                  order=config.source_order(), min_chars=500, workers=4)


def rate(rows) -> float:
    return round(sum(r["status"] == "full_text" for r in rows) / len(rows), 4) if rows else 0.0


def main() -> None:
    data = HERE / "data"
    sample = json.loads((data / "sample.json").read_text())
    corrected = own_ids(sample)
    changed = [i for i, s in enumerate(sample)
               if not _same(s["identifier"], corrected[i])]

    eng = engine()
    live = [s["source"] for s in eng.sources() if s["available"]]
    off = {s["source"]: s["reason"] for s in eng.sources() if not s["available"]}
    t0 = time.time()
    own = eng.fetch([c or "" for c in corrected])
    wall = time.time() - t0
    stored = engine().fetch([sample[i]["identifier"] or "" for i in changed])
    stored_by_idx = dict(zip(changed, stored, strict=True))

    with (data / "results.jsonl").open("w") as fh:
        for i, (s, r) in enumerate(zip(sample, own, strict=True)):
            row = {
                "id": s["id"], "corpus_source": s["corpus_source"],
                "stored_ids": s["identifier"], "own_ids": corrected[i],
                "ids_changed": i in stored_by_idx,
                "status": r["status"], "source": r.get("source"),
                "chars": r.get("chars"), "explanation": r.get("explanation"),
            }
            if i in stored_by_idx:
                st = stored_by_idx[i]
                row["stored_status"] = st["status"]
                row["stored_source"] = st.get("source")
            fh.write(json.dumps(row) + "\n")

    n = len(own)
    status = Counter(r["status"] for r in own)
    full = [r for r in own if r["status"] == "full_text"]
    by_source = Counter(r["source"] for r in full)
    with_pmc = [r for r in own if (r.get("ids") or {}).get("pmcid")]
    without_pmc = [r for r in own if not (r.get("ids") or {}).get("pmcid")]
    own_changed = [own[i] for i in changed]
    was_mismatch = [i for i in changed
                    if stored_by_idx[i]["status"] == "identifier_mismatch"]

    values = {"full_text_rate": {"mean": rate(own), "n": n}}
    for src, k in sorted(by_source.items()):
        values[f"full_text_by_source.{src}"] = {"mean": round(k / n, 4), "n": n}
    for st, k in sorted(status.items()):
        values[f"status.{st}"] = k
    values["ids_changed"] = len(changed)
    values["changed.full_text_rate.own"] = {"mean": rate(own_changed), "n": len(changed)}
    values["changed.full_text_rate.stored"] = {"mean": rate(stored), "n": len(changed)}
    for st, k in sorted(Counter(r["status"] for r in stored).items()):
        values[f"changed.stored_status.{st}"] = k
    values["mismatch_resolved"] = {
        "mean": sum(own[i]["status"] != "identifier_mismatch" for i in was_mismatch),
        "n": len(was_mismatch)}
    values["mismatch_now_full_text"] = {
        "mean": sum(own[i]["status"] == "full_text" for i in was_mismatch),
        "n": len(was_mismatch)}
    values["full_text_rate_with_pmcid"] = {"mean": rate(with_pmc), "n": len(with_pmc)}
    values["full_text_rate_without_pmcid"] = {"mean": rate(without_pmc),
                                              "n": len(without_pmc)}
    values["median_chars"] = int(statistics.median(r["chars"] for r in full)) if full else 0
    values["wall_clock_seconds"] = round(wall, 1)

    metrics = {"primary": "full_text_rate", "values": values,
               "sources_live": live, "sources_off": off, "sample": n}
    (data / "metrics.json").write_text(json.dumps(metrics, indent=1))
    with (data / "metrics.csv").open("w", newline="") as fh:
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
