"""EXP-2026-11-007 — metrics from data/pairs.json (never calls the model).

    python3 code/analyse.py

Writes data/metrics.json, data/metrics.csv and tables/summary.md.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
LEVELS = ("skip", "file", "skim", "read")


def auc(pos: list[float], neg: list[float]) -> float:
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=xs.__getitem__)
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def kendall(a: list[float], b: list[float]) -> float:
    n, s = len(a), 0
    for i in range(n):
        for j in range(i + 1, n):
            x, y = a[i] - a[j], b[i] - b[j]
            s += (x * y > 0) - (x * y < 0)
    return s / (n * (n - 1) / 2) if n > 1 else float("nan")


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main() -> int:
    data = json.loads((EXP_DIR / "data" / "pairs.json").read_text())
    pairs = data["pairs"]
    ok = [p for p in pairs if p["d3"]["ok"]]
    on = [p for p in ok if not p["control"]]
    ctl = [p for p in ok if p["control"]]

    m: dict = {
        "n_pairs": len(pairs),
        "n_on_theme": len(on),
        "n_control": len(ctl),
        "availability": round(len(ok) / len(pairs), 4),
        "latency_server_ms_p50": round(pct([p["d3"]["server_ms"] for p in ok], 0.5), 1),
        "latency_server_ms_p95": round(pct([p["d3"]["server_ms"] for p in ok], 0.95), 1),
        "wall_seconds_main": data["totals"]["wall_seconds_main"],
    }

    # Discrimination: each control vs the same item on its home theme.
    home = {(p["content_id"], p["cluster_id"]): p for p in on}
    pos, neg, paired_wins = [], [], 0
    for c in ctl:
        h = home.get((c["content_id"], c["home_cluster_id"]))
        if h is None:
            continue
        pos.append(h["d3"]["worth"]["yes"])
        neg.append(c["d3"]["worth"]["yes"])
        paired_wins += h["d3"]["worth"]["yes"] > c["d3"]["worth"]["yes"]
    m["discrimination_auc_worth"] = round(auc(pos, neg), 4)
    m["discrimination_paired_win_rate"] = round(paired_wins / len(pos), 4)
    m["worth_mean_on_theme_top3"] = round(statistics.mean(pos), 4)
    m["worth_mean_off_theme"] = round(statistics.mean(neg), 4)
    pos_fit = [home[(c["content_id"], c["home_cluster_id"])]["d3"]["fit"]["value"] for c in ctl]
    neg_fit = [c["d3"]["fit"]["value"] for c in ctl]
    m["discrimination_auc_fit"] = round(auc(pos_fit, neg_fit), 4)

    # Agreement with the stored verdict (a system output, not a judgement).
    judged = [p for p in on if p["stored_verdict"] in LEVELS]
    exact = sum(p["d3"]["fit"]["argmax"] == p["stored_verdict"] for p in judged)
    within = sum(
        abs(LEVELS.index(p["d3"]["fit"]["argmax"]) - LEVELS.index(p["stored_verdict"])) <= 1
        for p in judged
    )
    m["verdict_n"] = len(judged)
    m["verdict_exact"] = round(exact / len(judged), 4)
    m["verdict_within_one"] = round(within / len(judged), 4)
    m["verdict_spearman_fit"] = round(
        spearman(
            [p["d3"]["fit"]["value"] for p in judged],
            [LEVELS.index(p["stored_verdict"]) for p in judged],
        ),
        4,
    )
    m["d3_argmax_distribution"] = {
        lv: sum(p["d3"]["fit"]["argmax"] == lv for p in on) for lv in LEVELS
    }
    m["stored_verdict_distribution"] = {
        lv: sum(p["stored_verdict"] == lv for p in judged) for lv in LEVELS
    }

    # Saturation of the sort key.
    w = [p["d3"]["worth"]["yes"] for p in on]
    m["worth_saturated_share"] = round(sum(x > 0.95 or x < 0.05 for x in w) / len(w), 4)
    m["worth_distinct_2dp"] = len({round(x, 2) for x in w})

    # Reorder movement within each theme head (by content type).
    taus, moved = [], 0
    groups: dict = {}
    for p in on:
        groups.setdefault((p["content_type"], p["cluster_id"]), []).append(p)
    for g in groups.values():
        g.sort(key=lambda p: p["rank"])
        taus.append(kendall([-p["rank"] for p in g], [p["d3"]["worth"]["yes"] for p in g]))
        order = sorted(range(len(g)), key=lambda i: (-g[i]["d3"]["worth"]["yes"], i))
        moved += sum(i != j for i, j in enumerate(order))
    m["fused_vs_worth_kendall_mean"] = round(statistics.mean(taus), 4)
    m["moved_share"] = round(moved / len(on), 4)

    # Per content type: discrimination and agreement.
    per_type = {}
    for ct in ("paper", "grant", "conference"):
        cp = [c for c in ctl if c["content_type"] == ct]
        hp = [home[(c["content_id"], c["home_cluster_id"])]["d3"]["worth"]["yes"] for c in cp]
        np_ = [c["d3"]["worth"]["yes"] for c in cp]
        jt = [p for p in judged if p["content_type"] == ct]
        per_type[ct] = {
            "auc_worth": round(auc(hp, np_), 4),
            "verdict_exact": round(
                sum(p["d3"]["fit"]["argmax"] == p["stored_verdict"] for p in jt) / len(jt), 4
            ),
            "worth_mean_on": round(statistics.mean(p["d3"]["worth"]["yes"] for p in on if p["content_type"] == ct), 4),
        }
    m["per_type"] = per_type
    area = {
        "eligible_mean": statistics.mean(p["d3"]["eligible"]["yes"] for p in on if p["content_type"] == "grant"),
        "venue_fit_mean_on": statistics.mean(p["d3"]["venue_fit"]["yes"] for p in on if p["content_type"] == "conference"),
        "venue_fit_mean_off": statistics.mean(p["d3"]["venue_fit"]["yes"] for p in ctl if p["content_type"] == "conference"),
    }
    m["area"] = {k: round(v, 4) for k, v in area.items()}

    det = [max(r) - min(r) for r in (d["worth"] for d in data["determinism"])]
    m["determinism_max_abs_diff_worth"] = round(max(det), 6)

    (EXP_DIR / "data" / "metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    flat = {k: v for k, v in m.items() if not isinstance(v, dict)}
    for ct, vals in per_type.items():
        for k, v in vals.items():
            flat[f"{ct}_{k}"] = v
    for k, v in m["area"].items():
        flat[f"area_{k}"] = v
    with (EXP_DIR / "data" / "metrics.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["metric", "value"])
        for k in sorted(flat):
            wr.writerow([k, flat[k]])

    lines = ["| Metric | Value |", "| --- | --- |"]
    lines += [f"| {k} | {flat[k]} |" for k in sorted(flat)]
    tables = EXP_DIR / "tables"
    tables.mkdir(exist_ok=True)
    (tables / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(m, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
