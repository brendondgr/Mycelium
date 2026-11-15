"""EXP-2026-11-020 5a: draw the forced drafts (standard library only).

    python3 docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/sample_drafts.py

From EXP-2026-11-013's injected copies of repetitions ``rep2`` and ``rep3``
(``main`` is left out: it was written before that experiment's id rename and
needs a text join), takes the copies round one's checker flagged in three
classes the checker can flag:

- ``cite``: an invented citation number (class ``bad_cite``);
- ``figure``: an invented figure in running text (class ``amount``, placed
  ``prose`` or ``inplace``);
- ``factline``: a wrong value on a ``Label: value`` line (placement
  ``factline``, classes ``date``, ``author``, ``venue``, ``amount``).

A copy is eligible only when its error token (the invented ``#k``, the
invented figure, the wrong value) appears neither in the clean answer it was
made from nor in that answer's evidence, so finding the token in a final
answer means the injected error survived. Thirty per class are drawn with
``random.Random("20261115:<class>")``. Writes ``data/forced_sample.jsonl``.
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R1 = EXP.parent / "EXP-2026-11-013-agent-answers-human-judged"
TAGS = ("rep2", "rep3")
PER_CLASS = 30


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold())


def token_of(copy: dict) -> tuple[str, str] | None:
    cls, place, note = copy["class"], copy["placement"], copy["note"]
    if cls == "bad_cite" and copy["unmatched"]:
        return "cite", f"#{copy['unmatched'][0]}"
    if cls == "amount" and place in ("prose", "inplace") and copy["unsupported"]:
        return "figure", note.split("->", 1)[1].strip() if "->" in note else note.strip()
    if place == "factline" and cls in ("date", "author", "venue", "amount") and copy["unsupported"]:
        return "factline", note.strip()
    return None


def main() -> int:
    pools: dict[str, list] = {"cite": [], "figure": [], "factline": []}
    seen = set()
    for tag in TAGS:
        originals = {r["id"]: r for r in map(json.loads, (R1 / "data" / f"arm_a_{tag}.jsonl").read_text().splitlines())}
        for i, line in enumerate((R1 / "data" / f"inject_{tag}.jsonl").read_text().splitlines()):
            c = json.loads(line)
            if not c.get("caught"):
                continue
            got = token_of(c)
            if got is None:
                continue
            cls, token = got
            orig = originals.get(c["answer"])
            if orig is None or c["text"] in seen:
                continue
            evidence = "\n".join(str(r.get("content") or "") for r in orig.get("results") or [])
            evidence += "\n" + "\n".join(map(str, orig.get("extra") or []))
            if cls == "cite":
                if re.search(rf"{re.escape(token)}\b", orig["final_text"]):
                    continue
            elif fold(token) in fold(orig["final_text"]) or fold(token) in fold(evidence):
                continue
            seen.add(c["text"])
            pools[cls].append({"tag": tag, "line": i, "answer": c["answer"], "cls": cls,
                               "inject_class": c["class"], "placement": c["placement"],
                               "token": token, "note": c["note"], "draft": c["text"],
                               "r1_flags": {k: c[k] for k in ("unmatched", "unread", "unsupported")}})
    out = []
    sizes = {}
    for cls, pool in pools.items():
        rng = random.Random(f"20261115:{cls}")
        pick = rng.sample(pool, min(PER_CLASS, len(pool)))
        sizes[cls] = {"eligible": len(pool), "drawn": len(pick)}
        for j, p in enumerate(pick):
            p["draft_id"] = f"{cls}-{j + 1:02d}"
            out.append(p)
    (EXP / "data").mkdir(exist_ok=True)
    (EXP / "data" / "forced_sample.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n")
    print(json.dumps(sizes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
