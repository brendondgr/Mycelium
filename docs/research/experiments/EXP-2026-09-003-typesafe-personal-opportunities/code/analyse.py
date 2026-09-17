"""EXP-2026-09-003 — metrics and tables from ``data/pairs.json``. No network.

    uv run --project eval python .../code/analyse.py

Writes ``data/metrics.json``, ``data/metrics.csv``, ``tables/grants.md``,
``tables/conferences.md`` and ``tables/summary.md``. Re-runnable for free.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
LEVELS = ("skip", "file", "skim", "read")
AREA_QUESTION = {"grant": "eligible", "conference": "venue_fit"}


def kendall_tau_a(xs: list[float], ys: list[float]) -> float | None:
    """Tau-a over all pairs; a tie in either series counts as neither."""
    n = len(xs)
    if n < 2:
        return None
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            product = dx * dy
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    return (concordant - discordant) / (n * (n - 1) / 2)


def argmax_level(fit: dict) -> str | None:
    probabilities = fit.get("probabilities") or {}
    if not probabilities:
        return None
    best = max(probabilities.items(), key=lambda kv: kv[1])[0]
    try:
        return LEVELS[int(best)]
    except (ValueError, IndexError):
        return None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return ordered[k]


def main() -> int:
    payload = json.loads((EXP_DIR / "data" / "pairs.json").read_text())
    pairs = [p for p in payload["pairs"] if p.get("typesafe", {}).get("ok")]
    failed = [p for p in payload["pairs"] if not p.get("typesafe", {}).get("ok")]
    price = payload["meta"]["price_per_million_input_usd"]

    # -- per pair derived fields --------------------------------------------
    for p in pairs:
        answers = p["typesafe"]["answers"]
        fit = answers.get("fit", {})
        p["ts_verdict"] = argmax_level(fit)
        p["ts_fit_score"] = fit.get("score")
        p["ts_fit_conf"] = fit.get("confidence")
        p["ts_p_read"] = (fit.get("probabilities") or {}).get("3")
        p["ts_worth"] = answers.get("worth", {}).get("noul")
        p["ts_area_q"] = answers.get(AREA_QUESTION[p["area"]], {}).get("noul")

    # -- per theme ---------------------------------------------------------
    themes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in pairs:
        themes[(p["area"], p["cluster_label"])].append(p)
    per_theme = {}
    for (area, label), rows in sorted(themes.items()):
        rows.sort(key=lambda r: r["rank"])
        worth = [r["ts_worth"] for r in rows if r["ts_worth"] is not None]
        ranks = [r["rank"] for r in rows if r["ts_worth"] is not None]
        # fused rank ascending vs worth descending: agreement is tau on (rank, -worth)
        tau = kendall_tau_a(ranks, [-w for w in worth])
        distinct = len({round(r["ts_fit_score"], 2) for r in rows if r["ts_fit_score"] is not None})
        # TypeSafe order: by worth desc, then fused rank as tiebreak
        ordered = sorted(rows, key=lambda r: (-(r["ts_worth"] or -1), r["rank"]))
        for position, r in enumerate(ordered, start=1):
            r["ts_rank"] = position
        per_theme[f"{area}::{label}"] = {
            "n": len(rows),
            "tau_fused_vs_worth": tau,
            "distinct_fit_scores": distinct,
            "verdict_exact": _share(rows, lambda r: r["ts_verdict"] == r["stored_verdict"]),
            "mean_worth": _mean([r["ts_worth"] for r in rows]),
            "mean_area_question": _mean([r["ts_area_q"] for r in rows]),
        }

    # -- headline ----------------------------------------------------------
    judged = [p for p in pairs if p["stored_verdict"] in LEVELS and p["ts_verdict"]]
    exact = _share(judged, lambda r: r["ts_verdict"] == r["stored_verdict"])
    within_one = _share(
        judged,
        lambda r: abs(LEVELS.index(r["ts_verdict"]) - LEVELS.index(r["stored_verdict"])) <= 1,
    )
    taus = [t["tau_fused_vs_worth"] for t in per_theme.values() if t["tau_fused_vs_worth"] is not None]
    latencies = [p["typesafe"]["latency_ms"] for p in pairs]
    input_tokens = sum(p["typesafe"]["usage"]["input_tokens"] for p in pairs)
    output_tokens = sum(p["typesafe"]["usage"]["output_tokens"] for p in pairs)

    # determinism — worth (the pre-registered criterion) and fit score, separately
    worth_diffs, fit_diffs = [], []
    for d in payload.get("determinism", []):
        if not d.get("ok"):
            continue
        worths = [a["worth"]["noul"] for a in d["answers"] if a and "worth" in a]
        scores = [a["fit"]["score"] for a in d["answers"] if a and "fit" in a]
        if len(worths) > 1:
            worth_diffs.append(max(worths) - min(worths))
        if len(scores) > 1:
            fit_diffs.append(max(scores) - min(scores))

    metrics = {
        "n_pairs_answered": len(pairs),
        "n_pairs_failed": len(failed),
        "n_pairs_with_stored_verdict": len(judged),
        "verdict_exact": exact,
        "verdict_within_one": within_one,
        "tau_mean": _mean(taus),
        "tau_min": min(taus) if taus else None,
        "tau_max": max(taus) if taus else None,
        "distinct_fit_per_theme_mean": _mean([t["distinct_fit_scores"] for t in per_theme.values()]),
        "confidence_mean": _mean([p["ts_fit_conf"] for p in pairs]),
        "worth_mean": _mean([p["ts_worth"] for p in pairs]),
        "determinism_max_abs_diff_worth": round(max(worth_diffs), 4) if worth_diffs else None,
        "determinism_max_abs_diff_fit_score": round(max(fit_diffs), 4) if fit_diffs else None,
        "determinism_pairs": len(worth_diffs),
        "input_tokens_determinism_extra": payload["totals"].get("input_tokens_determinism_extra", 0),
        "calls_total": payload["totals"]["calls"],
        "cost_usd_total": round(
            (input_tokens + payload["totals"].get("input_tokens_determinism_extra", 0)) / 1e6 * price, 5
        ),
        "input_tokens_total": input_tokens,
        "output_tokens_total": output_tokens,
        "input_tokens_per_pair_mean": _mean([p["typesafe"]["usage"]["input_tokens"] for p in pairs]),
        "cost_usd_main_pass": round(input_tokens / 1e6 * price, 5),
        "latency_ms_median": statistics.median(latencies) if latencies else None,
        "latency_ms_p95": percentile(latencies, 0.95),
        "wall_seconds": payload["totals"]["wall_seconds"],
        "per_theme": per_theme,
    }
    data_dir = EXP_DIR / "data"
    (data_dir / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (data_dir / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in metrics.items():
            if key != "per_theme":
                writer.writerow([key, value])
        for theme, values in per_theme.items():
            for key, value in values.items():
                writer.writerow([f"{theme}::{key}", value])

    # -- tables ------------------------------------------------------------
    tables = EXP_DIR / "tables"
    tables.mkdir(exist_ok=True)
    for area, filename in (("grant", "grants.md"), ("conference", "conferences.md")):
        lines = [f"# {area.title()}s — fused order vs TypeSafe, per theme", ""]
        lines.append(
            "Columns: fused = the slate position the daily run produced; TS = the "
            "position by `worth` (ties broken by fused); LLM = the stored verdict "
            "from the prose model; TS verdict = argmax of the four-level fit; "
            "p(read) = probability mass on the top level; conf = fit confidence; "
            f"{AREA_QUESTION[area]} = the area question's probability."
        )
        for (a, label), rows in sorted(themes.items()):
            if a != area:
                continue
            lines += ["", f"## {label}", ""]
            lines.append(f"| fused | TS | title | deadline | LLM | TS verdict | fit | p(read) | worth | {AREA_QUESTION[area]} | conf |")
            lines.append("|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|")
            for r in sorted(rows, key=lambda r: r["rank"]):
                lines.append(
                    f"| {r['rank']} | {r.get('ts_rank', '')} | {r['title'][:90]} | {r.get('deadline_date') or ''} "
                    f"| {r.get('stored_verdict') or ''} | {r.get('ts_verdict') or ''} | {_fmt(r['ts_fit_score'])} "
                    f"| {_fmt(r['ts_p_read'])} | {_fmt(r['ts_worth'])} | {_fmt(r['ts_area_q'])} | {_fmt(r['ts_fit_conf'])} |"
                )
        (tables / filename).write_text("\n".join(lines) + "\n")

    # Where the two judges are two or more steps apart — the rows worth a human read.
    dis = [
        p for p in judged
        if abs(LEVELS.index(p["ts_verdict"]) - LEVELS.index(p["stored_verdict"])) >= 2
    ]
    lines = [
        "# Disagreements — two or more verdict steps apart",
        "",
        "The stored LLM verdict and TypeSafe's argmax fit level, on skip < file < skim < read. "
        "These are the rows a reader can settle by looking; neither judge is the truth.",
        "",
        "| area | theme | fused | title | LLM | TS verdict | fit | worth | conf |",
        "|---|---|---:|---|---|---|---:|---:|---:|",
    ]
    for r in sorted(dis, key=lambda r: (r["area"], r["cluster_label"], r["rank"])):
        lines.append(
            f"| {r['area']} | {r['cluster_label']} | {r['rank']} | {r['title'][:80]} | {r['stored_verdict']} "
            f"| {r['ts_verdict']} | {_fmt(r['ts_fit_score'])} | {_fmt(r['ts_worth'])} | {_fmt(r['ts_fit_conf'])} |"
        )
    (tables / "disagreements.md").write_text("\n".join(lines) + "\n")
    metrics["n_disagreements_two_steps"] = len(dis)

    summary = ["# Summary", "", "| metric | value |", "|---|---:|"]
    for key, value in metrics.items():
        if key != "per_theme":
            summary.append(f"| {key} | {_fmt(value)} |")
    summary += ["", "## Per theme", "", "| theme | n | tau | distinct fit | verdict exact | mean worth | mean area q |", "|---|---:|---:|---:|---:|---:|---:|"]
    for theme, v in per_theme.items():
        summary.append(
            f"| {theme} | {v['n']} | {_fmt(v['tau_fused_vs_worth'])} | {v['distinct_fit_scores']} "
            f"| {_fmt(v['verdict_exact'])} | {_fmt(v['mean_worth'])} | {_fmt(v['mean_area_question'])} |"
        )
    (tables / "summary.md").write_text("\n".join(summary) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "per_theme"}, indent=1))
    return 0


def _share(rows, predicate) -> float | None:
    return round(sum(1 for r in rows if predicate(r)) / len(rows), 4) if rows else None


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 4) if values else None


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}" if abs(value) < 100 else f"{value:.0f}"
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
