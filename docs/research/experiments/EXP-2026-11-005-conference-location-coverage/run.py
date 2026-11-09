"""EXP-2026-11-005: conference location and continent coverage, before vs after.

Read-only. Writes data/metrics.json, data/metrics.csv and data/sample.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())  # run from web/backend
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from tools.retrieval.geography import continent_for, place_for  # noqa: E402
from tools.retrieval.models import ContentItem  # noqa: E402


def before(meta: dict) -> tuple[str, str]:
    """The shipped logic: item_host for conferences, continent from structure."""
    place = ", ".join(str(x) for x in (meta.get("city"), meta.get("country")) if x)
    line = place or str(meta.get("place_text") or "")
    return line, continent_for(
        str(meta.get("country_code") or ""), str(meta.get("country") or "")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=20261108)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = list(
        ContentItem.objects.filter(type=ContentItem.Type.CONFERENCE).values_list(
            "id", "metadata"
        )
    )
    n = len(rows)
    counts = dict.fromkeys(
        ["continent_before", "continent_after", "country_before", "country_after",
         "venue_only_before", "venue_only_after", "online_after"], 0)
    by_continent: dict[str, int] = {}
    pairs = []
    for item_id, meta in rows:
        meta = meta or {}
        text = " ".join(str(meta.get("place_text") or "").split()).strip(" .")
        city = str(meta.get("city") or "").strip()
        line_b, cont_b = before(meta)
        place = place_for(meta)
        counts["continent_before"] += bool(cont_b)
        counts["continent_after"] += bool(place.continent)
        counts["country_before"] += bool(meta.get("country"))
        counts["country_after"] += bool(place.country)
        counts["online_after"] += place.continent == "Online"
        venue = bool(city) and len(text) > len(city) and not meta.get("country")
        counts["venue_only_before"] += venue and line_b == city
        counts["venue_only_after"] += venue and place.display == city
        by_continent[place.continent or "(none)"] = (
            by_continent.get(place.continent or "(none)", 0) + 1
        )
        pairs.append({"id": str(item_id), "place_text": text, "city": city,
                      "before": line_b, "after": place.display,
                      "continent": place.continent})

    metrics = {
        "n_conferences": n,
        "continent_rate_before": round(counts["continent_before"] / n, 4),
        "continent_rate": round(counts["continent_after"] / n, 4),
        "country_rate_before": round(counts["country_before"] / n, 4),
        "country_rate": round(counts["country_after"] / n, 4),
        "venue_only_before": counts["venue_only_before"],
        "venue_only_after": counts["venue_only_after"],
        "online_after": counts["online_after"],
        "by_continent": dict(sorted(by_continent.items())),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    with (out / "metrics.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for key, value in metrics.items():
            if not isinstance(value, dict):
                writer.writerow([key, value])
        for key, value in by_continent.items():
            writer.writerow([f"by_continent.{key}", value])
    placed = [p for p in pairs if p["continent"]]
    sample = random.Random(args.seed).sample(placed, min(40, len(placed)))
    (out / "sample.json").write_text(json.dumps(sample, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
