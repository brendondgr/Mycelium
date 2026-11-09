"""EXP-2026-11-012 — the exact /v1/decide bodies Mycelium would send.

    uv run --no-sync --project web/backend python code/dump_bodies.py \
        --states <scratch>/states.json --out <scratch>/bodies.json

Builds each body with ``PortDecisionClient._ask_decide`` itself (its HTTP is
replaced by a recorder), so bench.py feeds d3-lite exactly what GAIFA's decide
server would receive. The output holds profile text: keep it in scratch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "web" / "backend"))
sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.core.decisions import PortConfig, PortDecisionClient  # noqa: E402
from apps.core.management.commands.decision_check import (  # noqa: E402
    SAMPLE_STATE,
    _questions,
)

from tools.recommendation.typesafe_rerank import questions_for  # noqa: E402


class _Captured(Exception):
    pass


class _Recorder:
    def __init__(self):
        self.body = None

    def post(self, path, body):
        assert path == "/v1/decide"
        self.body = body
        raise _Captured


def body_for(state, questions):
    rec = _Recorder()
    client = PortDecisionClient(
        PortConfig(url="http://recorder", protocol="decide"), http=rec
    )
    try:
        client._ask_decide(state, questions)
    except _Captured:
        return rec.body
    raise AssertionError("the client sent nothing")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--states", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    src = json.loads(Path(args.states).read_text())
    out = {
        "synthetic": body_for(SAMPLE_STATE, _questions()),
        "real": [
            {
                "content_type": pr["content_type"],
                "content_id": pr["content_id"],
                "cluster_id": pr["cluster_id"],
                "control": pr["control"],
                "body": body_for(pr["state"], questions_for(pr["content_type"])),
            }
            for pr in src["pairs"]
        ],
    }
    Path(args.out).write_text(json.dumps(out))
    print(f"synthetic + {len(out['real'])} real bodies -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
