"""EXP-2026-11-009 — metrics, and the paired comparison with d3-lite.

    python3 code/analyse.py

Reads data/pairs.json (this run), data/throughput_c{1,4,8}.json and
EXP-2026-11-007's data/pairs.json (d3-lite on identical states). Writes
data/metrics.json, data/metrics.csv and tables/summary.md. Never calls a model.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
D3 = EXP.parent / "EXP-2026-11-007-d3-lite-local-decision-smoke" / "data" / "pairs.json"
LEVELS = ("skip", "file", "skim", "read")
TYPES = ("paper", "grant", "conference")
BOOT, SEED = 2000, 0


def auc(pos, neg):
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def ranks(xs):
    order = sorted(range(len(xs)), key=xs.__getitem__)
    out, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))]


def key(p):
    # An item in two themes' top 3 can draw the same control theme twice, so a
    # control is named by its home theme too.
    return (p["content_id"], p["cluster_id"], p["control"], p.get("home_cluster_id"))


def qwen_view(p):
    a = p["port"]["answers"]
    probs = a["fit"]["probabilities"]
    best = max(probs, key=probs.get)
    return {
        "worth": a["worth"]["noul"],
        "fit": a["fit"]["score"],
        "argmax": LEVELS[int(best)],
        "eligible": a.get("eligible", {}).get("noul"),
        "venue_fit": a.get("venue_fit", {}).get("noul"),
    }


def d3_view(p):
    a = p["d3"]
    return {
        "worth": a["worth"]["yes"],
        "fit": a["fit"]["value"],
        "argmax": a["fit"]["argmax"],
        "eligible": a.get("eligible", {}).get("yes"),
        "venue_fit": a.get("venue_fit", {}).get("yes"),
    }


def control_pairs(pairs, view):
    """[(content_type, home view, control view)] for every control."""
    home = {(p["content_id"], p["cluster_id"]): p for p in pairs if not p["control"]}
    out = []
    for c in (p for p in pairs if p["control"]):
        h = home[(c["content_id"], c["home_cluster_id"])]
        out.append((c["content_type"], view(h), view(c)))
    return out


def worth_auc(cp, field="worth"):
    return auc([h[field] for _t, h, _c in cp], [c[field] for _t, _h, c in cp])


def main() -> int:
    run = json.loads((EXP / "data" / "pairs.json").read_text())
    pairs = run["pairs"]
    failed = [p for p in pairs if not p["port"]["ok"]]
    if failed:
        raise SystemExit(f"{len(failed)} failed pairs; analyse only a clean run")
    d3_pairs = {key(p): p for p in json.loads(D3.read_text())["pairs"]}
    assert len(d3_pairs) == len(pairs), "duplicate pair keys"
    assert set(d3_pairs) == {key(p) for p in pairs}, "not the same pairs as EXP-007"

    on = [p for p in pairs if not p["control"]]
    q_cp = control_pairs(pairs, qwen_view)
    d_cp = control_pairs(list(d3_pairs.values()), d3_view)
    # Align d3's controls with ours, pair for pair.
    order = {
        (c["content_id"], c["home_cluster_id"]): i
        for i, c in enumerate(p for p in d3_pairs.values() if p["control"])
    }
    ours = [(c["content_id"], c["home_cluster_id"]) for c in pairs if c["control"]]
    d_cp = [d_cp[order[k]] for k in ours]

    m = {
        "n_pairs": len(pairs),
        "availability": 1.0,
        "model": run["meta"]["model"],
        "worth_auc": round(worth_auc(q_cp), 4),
        "worth_auc_d3": round(worth_auc(d_cp), 4),
        "fit_auc": round(worth_auc(q_cp, "fit"), 4),
        "paired_win_rate": round(
            sum(h["worth"] > c["worth"] for _t, h, c in q_cp) / len(q_cp), 4
        ),
        "worth_mean_on_top3": round(statistics.mean(h["worth"] for _t, h, _c in q_cp), 4),
        "worth_mean_off": round(statistics.mean(c["worth"] for _t, _h, c in q_cp), 4),
    }
    for t in TYPES:
        qt = [x for x in q_cp if x[0] == t]
        dt = [x for x in d_cp if x[0] == t]
        m[f"worth_auc_{t}"] = round(worth_auc(qt), 4)
        m[f"worth_auc_{t}_d3"] = round(worth_auc(dt), 4)

    # Paired bootstrap of the AUC difference over control pairs.
    rng = random.Random(SEED)
    diffs = []
    idx = list(range(len(q_cp)))
    for _ in range(BOOT):
        sample = [rng.choice(idx) for _ in idx]
        diffs.append(
            worth_auc([q_cp[i] for i in sample]) - worth_auc([d_cp[i] for i in sample])
        )
    diffs.sort()
    m["worth_auc_diff"] = round(m["worth_auc"] - m["worth_auc_d3"], 4)
    m["worth_auc_diff_ci_low"] = round(diffs[int(0.025 * BOOT)], 4)
    m["worth_auc_diff_ci_high"] = round(diffs[int(0.975 * BOOT) - 1], 4)

    judged = [p for p in on if p["stored_verdict"] in LEVELS]
    views = [qwen_view(p) for p in judged]
    m["verdict_exact"] = round(
        sum(v["argmax"] == p["stored_verdict"] for v, p in zip(views, judged, strict=True))
        / len(judged),
        4,
    )
    m["verdict_spearman_fit"] = round(
        spearman([v["fit"] for v in views], [LEVELS.index(p["stored_verdict"]) for p in judged]),
        4,
    )
    on_views = [qwen_view(p) for p in on]
    m["argmax_distribution"] = {lv: sum(v["argmax"] == lv for v in on_views) for lv in LEVELS}
    w = [v["worth"] for v in on_views]
    m["worth_saturated_share"] = round(sum(x > 0.95 or x < 0.05 for x in w) / len(w), 4)
    m["worth_distinct_2dp"] = len({round(x, 2) for x in w})
    m["grant_eligible_mean"] = round(
        statistics.mean(v["eligible"] for v, p in zip(on_views, on, strict=True)
                        if p["content_type"] == "grant"), 4
    )
    det = [max(r) - min(r) for r in (d["worth"] for d in run["determinism"])]
    m["determinism_max_abs_diff_worth"] = round(max(det), 6)

    lat = [p["port"]["wall_ms"] for p in pairs]
    m["real_state_latency_ms_p50"] = round(pct(lat, 0.5), 1)
    m["real_state_latency_ms_p95"] = round(pct(lat, 0.95), 1)
    m["real_state_pairs_per_s_sequential"] = round(
        len(pairs) / run["totals"]["wall_seconds_main"], 3
    )
    m["input_tokens_main"] = run["totals"]["input_tokens_main"]
    for c in (1, 4, 8):
        t = json.loads((EXP / "data" / f"throughput_c{c}.json").read_text())
        m[f"throughput_c{c}"] = t["throughput_calls_per_s"]
        m[f"latency_p50_ms_c{c}"] = t["latency_ms_p50"]
        m[f"throughput_failures_c{c}"] = t["failures"]

    (EXP / "data" / "metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    flat = {k: v for k, v in m.items() if not isinstance(v, dict)}
    with (EXP / "data" / "metrics.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["metric", "value"])
        for k in sorted(flat):
            wr.writerow([k, flat[k]])
    lines = [
        "| Worth AUC (on- vs off-theme) | Qwen3-4B (llama.cpp) | d3-lite (decide) |",
        "| --- | ---: | ---: |",
        f"| All (n=45 pairs) | {m['worth_auc']} | {m['worth_auc_d3']} |",
    ]
    for t in TYPES:
        lines.append(f"| {t} (n=15) | {m[f'worth_auc_{t}']} | {m[f'worth_auc_{t}_d3']} |")
    lines += [
        "",
        f"Difference {m['worth_auc_diff']}, 95% paired bootstrap "
        f"[{m['worth_auc_diff_ci_low']}, {m['worth_auc_diff_ci_high']}] "
        f"({BOOT} resamples, seed {SEED}).",
        "",
        "| Throughput (synthetic state) | Calls/s | p50 ms |",
        "| ---: | ---: | ---: |",
    ]
    for c in (1, 4, 8):
        lines.append(f"| {c} in flight | {m[f'throughput_c{c}']} | {m[f'latency_p50_ms_c{c}']} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(m, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
