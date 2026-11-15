"""EXP-2026-11-020 5b: does the ``unread`` check flag a detail about a reference
the thread surfaced but never read?

    docker compose run … python docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/unread.py

Fully scripted: no model call. Twenty topics, each run as three two-turn
threads (``data/unread_runs.jsonl``):

- ``surfaced`` (the plan's test): turn one runs the real ``corpus_search``
  for the topic and answers with the listing; turn two's forced draft cites
  the search's paper ``#k`` (the first result after the top one with
  authors stored) and states its first author in a sentence. Pass: ``k`` is
  in the first verdict's ``unread``.
- ``read`` (control): as ``surfaced``, but turn one also runs the real
  ``corpus_item`` on ``#k``. Pass: ``k`` is not in ``unread``.
- ``cleared`` (exploratory, not in any claim): as ``surfaced``, then turn
  one's search result is marked cleared the way compaction marks it
  (``settings["cleared"]``) before turn two — the one situation the code's
  definition of "seen" leaves for ``unread`` to fire.

Every later model call in turn two (the repair) is answered by the same draft
again, so the loop's own final pass runs without a model.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402

TOPICS = [
    "marine heatwave prediction", "ocean data assimilation", "marine litter tracking",
    "satellite ocean remote sensing", "Lagrangian particle tracking", "coastal water quality",
    "physics-informed machine learning for the ocean", "ocean turbulence parameterization",
    "sea surface temperature forecasting", "harmful algal bloom detection",
    "SWOT sea surface height", "eddy-resolving ocean forecasting", "chlorophyll-a retrieval from satellites",
    "plastic debris beaching", "ocean observing systems", "machine learning data assimilation",
    "ocean data dashboards", "compound extreme events in the ocean", "submesoscale ocean currents",
    "Argo float observations",
]
ARMS = ("surfaced", "read", "cleared")


def main() -> int:
    H.setup()
    from django.db import connection

    from tools.agent import loop, store
    from tools.agent.models import AgentThread
    from tools.retrieval.read import ContentItem

    ctx = H.mylo_turn.demo_context()
    out = EXP / "data" / "unread_runs.jsonl"
    done = set()
    if out.exists():
        done = {(r["arm"], r["topic"]) for r in map(json.loads, out.read_text().splitlines())}

    def search_refs(thread):
        for e in store.events(thread):
            if e.type == "tool_result" and e.payload.get("call_id") == "t1-search":
                return list(e.payload.get("refs") or [])
        return []

    def pick(thread):
        table = {e["n"]: e for e in (thread.settings or {}).get("refs", [])}
        thread.refresh_from_db()
        table = {e["n"]: e for e in (thread.settings or {}).get("refs", [])}
        for n in search_refs(thread)[1:]:
            e = table.get(n)
            if not e or e.get("kind") != "item":
                continue
            meta = ContentItem.objects.get(pk=e["key"]).metadata or {}
            authors = meta.get("authors") or []
            if isinstance(authors, str):
                authors = [authors]
            if authors:
                return n, str(authors[0]), str(meta.get("title") or "")[:80]
        return None, "", ""

    for topic in TOPICS:
        for arm in ARMS:
            if (arm, topic) in done:
                continue
            t0 = time.monotonic()
            row = {"arm": arm, "topic": topic}
            try:
                thread, caller = H.new_thread(ctx, {"scope": "lab"})
                H.ask(caller, thread, f"Find recent papers on {topic}.")
                chosen = {}

                def read_call():
                    n, author, title = pick(thread)
                    chosen.update(n=n, author=author, title=title)
                    return H.response(calls=[{"id": "t1-read", "name": "corpus_item", "args": {"item": f"#{n}"}}])

                def listing():
                    if "n" not in chosen:
                        n, author, title = pick(thread)
                        chosen.update(n=n, author=author, title=title)
                    ns = search_refs(thread)
                    return H.response(text="Here are papers I found: " + "; ".join(f"#{n}" for n in ns[:5]) + ".")

                script = [H.response(calls=[{"id": "t1-search", "name": "corpus_search",
                                             "args": {"query": topic, "types": ["paper"], "limit": 5}}])]
                if arm == "read":
                    script.append(read_call)
                script.append(listing)
                loop.run_turn(thread.pk, port=H.ScriptedPort(script), caller=caller)
                t1 = H.outcome(thread)
                k = chosen.get("n")
                if k is None:
                    raise RuntimeError("no surfaced paper with authors")
                if arm == "cleared":
                    thread.refresh_from_db()
                    settings = dict(thread.settings or {})
                    settings["cleared"] = sorted(set(settings.get("cleared", [])) | {"t1-search"})
                    AgentThread.objects.filter(pk=thread.pk).update(settings=settings)
                H.ask(caller, thread, "Tell me more about the second paper you listed. Who wrote it?")
                draft = (f"That paper, \"{chosen['title']}\" (#{k}), is by {chosen['author']} and colleagues.")
                loop.run_turn(thread.pk, port=H.ScriptedPort([H.response(text=draft)] * 4), caller=caller)
                t2 = H.outcome(thread, since_seq=t1["last_seq"])
                first = t2["verdicts"][0] if t2["verdicts"] else {}
                row.update({"k": k, "author": chosen["author"], "draft": draft, "thread": str(thread.pk),
                            "turn1_functions": t1["functions"], "first_verdict": first,
                            "verdicts": t2["verdicts"], "final_text": t2["final_text"], "errors": t2["errors"],
                            "flag_unread": k in (first.get("unread") or []),
                            "flag_any": bool(first) and not first.get("ok", True)})
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"[:400]
            finally:
                connection.close()
            row["elapsed_s"] = round(time.monotonic() - t0, 3)
            with out.open("a") as fh:
                fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            print(arm, topic, row.get("k"), row.get("flag_unread"), row.get("error", ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
