"""EXP-2026-11-014: dump the production rerank questions (no profile text).

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/dump_questions.py
Writes data/questions.json: ``typesafe_rerank.questions_for`` per content type.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from tools.recommendation.typesafe_rerank import QUESTION_VERSION, questions_for  # noqa: E402

out = {"question_version": QUESTION_VERSION,
       "by_type": {t: questions_for(t) for t in ("paper", "grant", "conference", "fellowship")}}
(HERE / "data" / "questions.json").write_text(json.dumps(out, indent=1))
print({t: list(q) for t, q in out["by_type"].items()})
