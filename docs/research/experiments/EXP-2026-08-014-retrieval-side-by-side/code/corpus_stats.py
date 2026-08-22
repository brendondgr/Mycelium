"""Corpus hygiene facts the side-by-side lists made visible (`EXP-2026-08-014`).

    uv run --project eval python .../code/corpus_stats.py

Reading the actual top-tens turned up something no aggregate metric in this
record would have surfaced: the same document appears several times in one list,
because it appears several times in the store. That is a property of the corpus,
not of any arm, and it costs a reader top-ten slots regardless of which retrieval
process wins.

This counts it, so the booklet can state it with a number instead of an anecdote.
Writes `data/corpus_stats.json`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)


def main() -> int:
    import django

    django.setup()
    from django.db import connection

    out: dict = {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select type,
                   count(*) as rows,
                   count(*) filter (
                     where coalesce(metadata->>'title', metadata->>'name', '') = ''
                   ) as untitled,
                   count(*) - count(distinct lower(
                     coalesce(metadata->>'title', metadata->>'name', '')
                   )) as duplicate_rows
            from content_contentitem
            group by type order by type
            """
        )
        for content_type, rows, untitled, duplicate_rows in cursor.fetchall():
            # Every untitled row past the first collapses into one "duplicate" of
            # the empty string, which is a different defect; separate them so the
            # duplicate count means what it says.
            titled_dupes = duplicate_rows - max(untitled - 1, 0)
            out[content_type] = {
                "rows": rows,
                "untitled": untitled,
                "duplicate_title_rows": titled_dupes,
                "duplicate_share": titled_dupes / rows if rows else 0.0,
            }

        cursor.execute(
            """
            select lower(coalesce(metadata->>'title', metadata->>'name', '')) as t,
                   count(*) as n
            from content_contentitem
            where coalesce(metadata->>'title', metadata->>'name', '') <> ''
            group by 1 having count(*) > 1
            order by n desc limit 10
            """
        )
        out["worst_offenders"] = [
            {"title": title[:90], "copies": n} for title, n in cursor.fetchall()
        ]

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "corpus_stats.json").write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n"
    )
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
