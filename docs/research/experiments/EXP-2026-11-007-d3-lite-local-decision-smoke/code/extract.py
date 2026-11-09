"""EXP-2026-11-007 — build the production TypeSafe states for one reader.

Runs inside the backend container (it needs Django and the production store)::

    docker compose exec -T backend sh -c \
      'cd web/backend && uv run --no-sync python \
       /app/docs/research/experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/code/extract.py \
       --user brendondgr --per-theme 8' > <scratch>/states.json

Writes JSON to stdout: one record per (theme, item) pair from the reader's
current per-theme slates, with the *exact* state
``tools.recommendation.typesafe_rerank`` would send (``build_state`` over
``profile_block`` and ``candidate_block``), the fused slate rank, and the prose
model's stored verdict for that theme. It also emits an off-theme control: each
item paired with a theme whose slate does NOT contain it.

The reader's profile text is in the output, so the output goes to a scratch
directory and is never committed; ``decide.py`` keeps only its hash.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, "/app/web/backend")
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from tools.recommendation import typesafe_rerank as ts  # noqa: E402
from tools.recommendation.clustering import cluster_interests  # noqa: E402
from tools.recommendation.models import RelevanceScore  # noqa: E402
from tools.recommendation.targets import target_for_user  # noqa: E402

TYPES = ("paper", "grant", "conference")


def stored_verdict(signals: dict, cluster_id: str) -> str | None:
    writeup = ((signals.get("writeups") or {}).get(cluster_id)) or {}
    return writeup.get("verdict") or signals.get("verdict")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--per-theme", type=int, default=8)
    args = parser.parse_args()

    user = User.objects.get(username=args.user)
    target = target_for_user(user)
    clusters = {c.id: c for c in cluster_interests(target.interests)}
    profile_text = ts.profile_block(target.interests, target.profile_meta)

    pairs: list[dict] = []
    for content_type in TYPES:
        rows = RelevanceScore.objects.filter(
            target_user=user, content__type=content_type
        ).select_related("content")
        by_theme: dict[str, list[tuple[int, object, dict]]] = {}
        for row in rows:
            slates = (row.signals or {}).get("cluster_slates") or {}
            for cluster_id, entry in slates.items():
                if cluster_id in clusters and entry.get("rank"):
                    by_theme.setdefault(cluster_id, []).append(
                        (int(entry["rank"]), row, row.signals or {})
                    )
        for cluster_id, members in by_theme.items():
            members.sort(key=lambda m: m[0])
            for rank, row, signals in members[: args.per_theme]:
                cluster = clusters[cluster_id]
                candidate = ts.candidate_block(content_type, row.content)
                pairs.append(
                    {
                        "content_type": content_type,
                        "content_id": str(row.content_id),
                        "cluster_id": cluster_id,
                        "cluster_label": cluster.label,
                        "rank": rank,
                        "stored_verdict": stored_verdict(signals, cluster_id),
                        "control": False,
                        "state": ts.build_state(profile_text, cluster, candidate),
                    }
                )

    # Off-theme control: the same item judged against a theme whose slate does
    # not hold it. A decision model that reads the strand should score these low.
    on = {(p["content_id"], p["cluster_id"]) for p in pairs}
    ids = list(clusters)
    controls = []
    for p in pairs:
        if p["rank"] > 3:  # the top 3 of each theme only — keep the run small
            continue
        for other in ids:
            if other != p["cluster_id"] and (p["content_id"], other) not in on:
                cluster = clusters[other]
                state = dict(p["state"])
                state["strand"] = {"label": cluster.label, "interests": list(cluster.areas)}
                controls.append(
                    {
                        **{k: v for k, v in p.items() if k != "state"},
                        "cluster_id": other,
                        "cluster_label": cluster.label,
                        "home_cluster_id": p["cluster_id"],
                        "stored_verdict": None,
                        "control": True,
                        "state": state,
                    }
                )
                break
    json.dump(
        {
            "user": args.user,
            "n_clusters": len(clusters),
            "question_version": ts.QUESTION_VERSION,
            "pairs": pairs + controls,
        },
        sys.stdout,
        default=str,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
