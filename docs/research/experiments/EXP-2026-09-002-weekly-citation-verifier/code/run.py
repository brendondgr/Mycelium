"""EXP-2026-09-002: the weekly citation verifier, on the live instance's weeklies.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-09-002-weekly-citation-verifier/code/run.py census
    ... run.py rebuild     # packets for the model-written weeklies + faithfulness test
    ... run.py sheet       # 50-sentence labelling sheet (only if the rebuild is faithful)
    ... run.py inject      # injected-error recall of the deterministic checks

Read-only against the live database (``DailyBriefing`` rows); nothing is
persisted. Packet text and weekly bodies hold real people's project prose, so
everything except counts and the labelling sheet goes to ``/scratch``
(``--scratch``), never into this folder.

``census``: counts per origin and week, claims, removals (data/census.json).
``rebuild``: for every model-written weekly, rebuild its packet with the
production builder for the same owner and week (``today`` = the weekly's
``generated_on``), render the references block, and compare it with the
references block stored in the body; re-run ``verify_body`` on the stored
model-written part against the rebuilt packet. A weekly counts as faithfully
rebuilt only if its references block is byte-identical *and* re-verification
removes nothing (data/rebuild.json).
``sheet``: 50 kept sentences that carry a citation, stratified across the
faithfully rebuilt weeklies, each with the packet items it cites; verdict
hidden (data/sheets/labels_template.csv; evidence under data/sheets/evidence/).
``inject``: on kept cited sentences of faithfully rebuilt weeklies, one error
per copy — an unresolvable ``[P#]``, a changed number or date, and a
model-written unsupported paraphrase with no new numbers — run through
``verify_line`` with the rebuilt packet; recall per class (data/inject.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
SEED = 20261112
CITE = re.compile(r"\[P(\d+)\]")
PARAPHRASE_PROMPT = (
    "Rewrite the sentence below so that it makes one specific claim that the cited "
    "evidence would not support (overstate it, reverse it, or attribute something "
    "else to it). Keep every [P#] marker exactly as it is. Do not add any number, "
    "date, name or amount. Return only the rewritten sentence.\n\nSentence: {sentence}"
)


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def weeklies(llm_only=True):
    from tools.delivery.models import DailyBriefing

    qs = DailyBriefing.objects.filter(kind=DailyBriefing.Kind.WEEKLY)
    if llm_only:
        qs = qs.filter(origin=DailyBriefing.Origin.LLM)
    return list(qs.select_related("user", "lab", "department").order_by("generated_on", "pk"))


def written_part(body):
    """The model-written half: everything before the code-rendered frame."""
    stop = re.compile(r"^## (What changed|Deadlines|Coming up|References|Mylo)", re.M)
    m = stop.search(body)
    return body[:m.start()] if m else body


def references_text(body):
    m = re.search(r"^## References.*?(?=^## |\Z)", body, re.M | re.S)
    return m.group(0).strip() if m else ""


def rebuild_packet(row):
    from tools.delivery.weekly_build import SURFACE_CHANNEL, SURFACE_DM, build_weekly_packet

    if row.user_id:
        from tools.delivery.briefing import report_projects_for_user

        return build_weekly_packet(target_filter={"target_user": row.user},
                                   projects=report_projects_for_user(row.user), reader=row.user,
                                   surface=SURFACE_DM, label=str(row.user_id), today=row.generated_on)
    from tools.delivery.org_scope import org

    scope = org(row.lab or row.department)
    return build_weekly_packet(target_filter=scope.target_filter,
                               projects=scope.shared_projects(scope.post_width()), reader=scope.obj,
                               surface=SURFACE_CHANNEL, label=scope.key, today=row.generated_on)


def census(args):
    from collections import Counter

    rows = weeklies(llm_only=False)
    out = {"weeklies": len(rows), "by_origin": dict(Counter(r.origin for r in rows)), "weeks": {}}
    for r in rows:
        v = r.verification or {}
        w = out["weeks"].setdefault(str(r.generated_on), {"weeklies": 0, "llm": 0, "claims": 0, "removed": 0,
                                                           "llm_claims": 0, "project_sections": 0})
        w["weeklies"] += 1
        w["claims"] += int(v.get("claims") or 0)
        w["removed"] += int(v.get("removed") or 0)
        if r.origin == "llm":
            w["llm"] += 1
            w["llm_claims"] += int(v.get("claims") or 0)
            w["project_sections"] += r.body.count("## Project · ")
    out["llm_weeklies"] = sum(1 for r in rows if r.origin == "llm")
    out["llm_project_sections"] = sum(r.body.count("## Project · ") for r in rows if r.origin == "llm")
    out["claims_total"] = sum(int((r.verification or {}).get("claims") or 0) for r in rows)
    out["removed_total"] = sum(int((r.verification or {}).get("removed") or 0) for r in rows)
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "census.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "weeks"}, indent=1))


def rebuild(args):
    from tools.delivery.report_grammar import references_block
    from tools.delivery.weekly_verify import verify_body

    results = []
    scratch = Path(args.scratch)
    for row in weeklies():
        entry = {"weekly": hashlib.sha256(str(row.pk).encode()).hexdigest()[:10],
                 "generated_on": str(row.generated_on), "owner": "user" if row.user_id else "org"}
        try:
            packet = rebuild_packet(row)
            stored_refs = references_text(row.body)
            rebuilt_refs = references_block(packet.references()).strip()
            written = written_part(row.body)
            _, record = verify_body(written, packet)
            entry.update({
                "references_identical": stored_refs == rebuilt_refs,
                "stored_refs_lines": stored_refs.count("\n"), "rebuilt_refs_lines": rebuilt_refs.count("\n"),
                "context_version_match": getattr(packet, "context_version", None) == row.context_version,
                "reverify_claims": record.claims, "reverify_removed": record.removed,
                "stored_claims": (row.verification or {}).get("claims"),
            })
            entry["faithful"] = bool(entry["references_identical"] and record.removed == 0)
            (scratch / f"weekly_{entry['weekly']}.json").write_text(json.dumps({
                "written": written, "packet_items": packet_items(packet),
                "numbers": sorted(packet.numbers()) if hasattr(packet, "numbers") else []}, default=str))
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["faithful"] = False
        results.append(entry)
        print(json.dumps(entry), flush=True)
    (HERE / "data" / "rebuild.json").write_text(json.dumps(results, indent=1))


def packet_items(packet):
    out = {}
    for ref in packet.references():
        out[str(ref["n"])] = ref
    for attr in ("projects",):
        for project in getattr(packet, attr, []) or []:
            for item in getattr(project, "items", []) or []:
                n = getattr(item, "n", None) or (item.get("n") if isinstance(item, dict) else None)
                if n is not None:
                    out[str(n)] = {**out.get(str(n), {}), "packet_text": str(getattr(item, "__dict__", item))[:3000]}
    return out


def kept_cited_sentences(written):
    from tools.delivery.weekly_verify import _split_marker, sentences

    out = []
    for raw in written.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("|"):
            continue
        _, prose = _split_marker(raw)
        for sent in sentences(prose):
            if CITE.search(sent):
                out.append(sent.strip())
    return out


def load_faithful(args):
    reb = json.loads((HERE / "data" / "rebuild.json").read_text())
    scratch = Path(args.scratch)
    out = []
    for e in reb:
        if e.get("faithful") or (getattr(args, "use_rebuilt", False) and "error" not in e):
            out.append((e, json.loads((scratch / f"weekly_{e['weekly']}.json").read_text())))
    return out


def sheet(args):
    import csv

    faithful = load_faithful(args)
    if not faithful:
        print("no faithfully rebuilt weekly: no sheet")
        return
    rng = random.Random(SEED)
    pools = [(e, w, kept_cited_sentences(w["written"])) for e, w in faithful]
    picked = []
    while len(picked) < 50 and any(p[2] for p in pools):
        for e, w, sents in pools:
            if sents and len(picked) < 50:
                picked.append((e, w, sents.pop(rng.randrange(len(sents)))))
    sheets = HERE / "data" / "sheets"
    (sheets / "evidence").mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (e, w, sent) in enumerate(picked, 1):
        sid = f"S{i:02d}"
        cited = sorted({int(n) for n in CITE.findall(sent)})
        ev = "\n\n".join(f"### [P{n}]\n{json.dumps(w['packet_items'].get(str(n), {}), indent=1)}" for n in cited)
        (sheets / "evidence" / f"{sid}.md").write_text(f"# {sid}\n\n## Sentence\n\n{sent}\n\n## Packet items it cites\n\n{ev}\n")
        rows.append({"sentence_id": sid, "sentence": sent, "evidence_file": f"evidence/{sid}.md",
                     "supported": "", "notes": ""})
    with (sheets / "labels_template.csv").open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(json.dumps({"sentences": len(rows), "weeklies": len(faithful)}))


def inject(args):
    from tools.agent.llmcall import default_port
    from tools.delivery.weekly_verify import verify_line

    faithful = load_faithful(args)
    rng = random.Random(SEED)
    port = None if args.no_paraphrase else default_port()
    rows = []
    paraphrases = 0
    for e, w in faithful:
        allowed = {int(n) for n in w["packet_items"]}
        numbers = set(w["numbers"])
        sents = kept_cited_sentences(w["written"])
        rng.shuffle(sents)
        for sent in sents[:20]:
            _, base_removed = verify_line(sent, allowed=allowed, numbers=numbers)
            if base_removed:
                continue
            copies = [("unresolved_citation", CITE.sub(f"[P{max(allowed or {0}) + 9}]", sent, count=1))]
            m = re.search(r"\b\d[\d,.]*\b", sent)
            if m:
                digits = re.sub(r"\D", "", m.group(0))[:6] or "0"
                copies.append(("number_inplace", sent[:m.start()] + str(int(digits) + rng.choice([3, 11, 29]))
                               + sent[m.end():]))
            copies.append(("number_added", sent.rstrip(". ") + f", about {rng.choice([17, 42, 63])}% of the total."))
            if port is not None and paraphrases < args.paraphrase_n:
                reply = port(messages=[{"role": "user", "content": PARAPHRASE_PROMPT.format(sentence=sent)}],
                             tools=None, tool_choice=None, on_delta=None, should_stop=None)
                new = (getattr(reply, "content", None) or "").strip().strip('"')
                if new and new != sent and len(re.findall(r"\d", new)) <= len(re.findall(r"\d", sent)):
                    copies.append(("paraphrase", new))
                    paraphrases += 1
            for cls, text in copies:
                _, removed = verify_line(text, allowed=allowed, numbers=numbers)
                rows.append({"weekly": e["weekly"], "class": cls, "caught": bool(removed),
                             "check": removed[0].check if removed else ""})
    summary = {}
    for cls in ("unresolved_citation", "number_inplace", "number_added", "paraphrase"):
        rs = [r for r in rows if r["class"] == cls]
        k = sum(r["caught"] for r in rs)
        summary[cls] = {"n": len(rs), "caught": k, "recall": round(k / len(rs), 4) if rs else None,
                        "ci95": wilson(k, len(rs))}
    (HERE / "data" / "inject.json").write_text(json.dumps({"classes": summary, "weeklies": len(faithful),
                                                           "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["census", "rebuild", "sheet", "inject"])
    ap.add_argument("--scratch", default="/scratch/d")
    ap.add_argument("--no-paraphrase", action="store_true")
    ap.add_argument("--use-rebuilt", action="store_true",
                    help="inject: use every rebuilt packet, faithful or not (amendment 1)")
    ap.add_argument("--paraphrase-n", type=int, default=40)
    args = ap.parse_args()
    Path(args.scratch).mkdir(parents=True, exist_ok=True)
    import django

    django.setup()
    {"census": census, "rebuild": rebuild, "sheet": sheet, "inject": inject}[args.mode](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
