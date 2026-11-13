"""EXP-2026-11-013: the injected-error set — verifier recall per error class.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/inject.py \
        [--arm-file data/arm_a_main.jsonl] [--tag main] [--no-paraphrase]

Base answers: arm (a) answers whose final verdict was clean (no flag, nothing
removed). Each corrupted copy carries exactly one error, made by rule (seed
fixed). The verifier is run exactly as the loop runs it — ``unmatched``,
``unread`` against what the turn had in view, ``unsupported`` against the
folded source text — on the stored thread references and the stored function
results, so no thread is needed. A copy counts as caught if any of the three
flags it (that is what sends the loop into its repair).

Classes: bad_cite, unread_cite, date, author, venue, amount, paraphrase. For
the four detail classes the error is placed three ways, reported separately:
``inplace`` (a detail already in the answer is changed where it stands),
``prose`` (a sentence stating the wrong detail is added in running text),
``factline`` (the wrong detail is added as a ``- Label: value`` line, the form
the verifier parses). The paraphrase class is written by the instance model
with a fixed prompt (below) and is expected to be missed.

Writes data/inject_<tag>.jsonl (every copy, its class, placement and flags)
and data/inject_<tag>_summary.json.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mylo_turn  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
SEED = 20261112
FAKE_SURNAMES = ["Whitcombe", "Okonkwo", "Lindqvist", "Marchetti", "Tanabe", "Ferreira",
                 "Abernathy", "Kowalczyk"]
FAKE_VENUES = ["Journal of Applied Oceanic Systems", "Marine Forecasting Letters",
               "Proceedings of the Coastal Data Symposium"]
PARAPHRASE_PROMPT = (
    "Rewrite the sentence below so that it makes one specific claim that the evidence "
    "does not support (for example, overstate a result, reverse a conclusion, or "
    "attribute a finding the evidence does not mention). Keep any #n citation markers "
    "exactly as they are. Do not add any new number, date, name, venue or amount. "
    "Return only the rewritten sentence.\n\nSentence: {sentence}"
)
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
MONEY = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|[kKmM]))?)|"
                   r"\b\d[\d,]*(?:\.\d+)?\s?(?:%|million|billion|USD|EUR|GBP)")
SENT = re.compile(r"[^.!?\n]+[.!?]")


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def check(verify, row, text):
    thread = SimpleNamespace(settings={"refs": row["refs"]})
    results, extra = row["results"], row["extra"]
    missing = verify.unmatched(thread, text)
    seen = verify.seen_refs(results, extra)
    unread = [n for n in verify.unread(thread, text, seen) if n not in missing]
    claims = verify.unsupported(text, verify.source_text(results, extra))
    return {"unmatched": missing, "unread": unread, "unsupported": claims,
            "caught": bool(missing or unread or claims)}


def is_factline(verify, text, pos):
    for m in verify._FACT_LINE.finditer(text):
        if m.start() <= pos < m.end():
            return True
    return False


def first_cite(text):
    m = re.search(r"#(\d+)", text)
    return int(m.group(1)) if m else None


def add_sentence(text, sentence):
    return text.rstrip() + "\n\n" + sentence


def source_names(row):
    src = "\n".join(str(p.get("content") or "") for p in row["results"])
    names = []
    for m in re.finditer(r"^Authors?:\s*(.+)$", src, re.M):
        for part in re.split(r",|;|\band\b", m.group(1)):
            words = re.findall(r"[^\W\d_]{3,}", part)
            if words:
                names.append(words[-1])
    venues = [m.group(1).strip() for m in re.finditer(r"^(?:Venue|Journal):\s*(.+)$", src, re.M)]
    return list(dict.fromkeys(names)), list(dict.fromkeys(venues))


def corruptions(verify, row, rng):
    """Yield (cls, placement, text, note) — one error per copy."""
    text = row["final_text"]
    refs_n = sorted(e["n"] for e in row["refs"])
    seen = verify.seen_refs(row["results"], row["extra"])
    cites = [int(m.group(1)) for m in re.finditer(r"#(\d+)", text)]
    n0 = first_cite(text) or (refs_n[0] if refs_n else 1)
    # 1. a citation number no reference in the thread has
    bad = (max(refs_n) if refs_n else 0) + 7
    if cites:
        for m in list(re.finditer(r"#(\d+)", text))[:3]:
            yield "bad_cite", "inplace", text[:m.start()] + f"#{bad}" + text[m.end():], m.group(0)
    else:
        yield "bad_cite", "prose", add_sentence(text, f"This is discussed further in #{bad}."), "added"
    # 2. a citation moved to a reference the thread surfaced but the agent never read
    unread_ns = [n for n in refs_n if n not in seen]
    if cites and unread_ns:
        for m in list(re.finditer(r"#(\d+)", text))[:3]:
            target = rng.choice(unread_ns)
            yield "unread_cite", "inplace", text[:m.start()] + f"#{target}" + text[m.end():], f"{m.group(0)}->#{target}"
    # 3. date / year
    for m in list(YEAR.finditer(text))[:3]:
        new = str(int(m.group(0)) - rng.choice([1, 2, 3]))
        place = "factline" if is_factline(verify, text, m.start()) else "inplace"
        yield "date", place, text[:m.start()] + new + text[m.end():], f"{m.group(0)}->{new}"
    yr = str(2011 + rng.randrange(8))
    yield "date", "prose", add_sentence(text, f"The work behind #{n0} dates from {yr}."), yr
    yield "date", "factline", add_sentence(text, f"- Year: {yr}"), yr
    # 4. author surname
    names, venues = source_names(row)
    fake = rng.choice(FAKE_SURNAMES)
    for name in names:
        m = re.search(rf"\b{re.escape(name)}\b", text)
        if m:
            place = "factline" if is_factline(verify, text, m.start()) else "inplace"
            yield "author", place, text[:m.start()] + fake + text[m.end():], f"{name}->{fake}"
            break
    yield "author", "prose", add_sentence(text, f"The lead author of #{n0} is {fake}."), fake
    yield "author", "factline", add_sentence(text, f"- Authors: J. {fake}"), fake
    # 5. venue
    venue_fake = rng.choice(FAKE_VENUES)
    for venue in venues:
        if venue and venue in text:
            i = text.index(venue)
            place = "factline" if is_factline(verify, text, i) else "inplace"
            yield "venue", place, text.replace(venue, venue_fake, 1), f"{venue}->{venue_fake}"
            break
    yield "venue", "prose", add_sentence(text, f"#{n0} appeared in {venue_fake}."), venue_fake
    yield "venue", "factline", add_sentence(text, f"- Venue: {venue_fake}"), venue_fake
    # 6. amount or figure
    for m in list(MONEY.finditer(text))[:2]:
        digits = re.search(r"\d+", m.group(0))
        new_num = str(int(digits.group(0)) + rng.choice([3, 7, 15]))
        new = m.group(0)[:digits.start()] + new_num + m.group(0)[digits.end():]
        place = "factline" if is_factline(verify, text, m.start()) else "inplace"
        yield "amount", place, text[:m.start()] + new + text[m.end():], f"{m.group(0)}->{new}"
    amt = f"${rng.choice([1.2, 2.5, 3.8])} million"
    yield "amount", "prose", add_sentence(text, f"The award behind #{n0} is worth {amt}."), amt
    yield "amount", "factline", add_sentence(text, f"- Amount: {amt}"), amt


def paraphrase(port, row, rng):
    sents = [m for m in SENT.finditer(row["final_text"]) if "#" in m.group(0) and len(m.group(0)) > 40]
    if not sents:
        return None
    m = rng.choice(sents)
    reply = port(messages=[{"role": "user", "content": PARAPHRASE_PROMPT.format(sentence=m.group(0).strip())}],
                 tools=None, tool_choice=None, on_delta=None, should_stop=None)
    new = (getattr(reply, "content", None) or "").strip().strip('"')
    if not new or new == m.group(0).strip():
        return None
    text = row["final_text"]
    return text[:m.start()] + " " + new + text[m.end():], f"{m.group(0).strip()[:200]} => {new[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-file", default="data/arm_a_main.jsonl")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--no-paraphrase", action="store_true")
    ap.add_argument("--paraphrase-n", type=int, default=60)
    args = ap.parse_args()
    mylo_turn.setup()
    from tools.agent import verify
    from tools.agent.llmcall import default_port

    rng = random.Random(SEED)
    rows = [json.loads(x) for x in (HERE / args.arm_file).read_text().splitlines() if x.strip()]
    base = [r for r in rows if "error" not in r and r.get("final_text")
            and r["verdicts"] and r["verdicts"][-1].get("action") == "none"]
    out = HERE / "data" / f"inject_{args.tag}.jsonl"
    copies = []
    originals_flagged = 0
    for r in base:
        flags = check(verify, r, r["final_text"])
        originals_flagged += flags["caught"]
        for cls, place, text, note in corruptions(verify, r, rng):
            copies.append({"answer": r["id"], "class": cls, "placement": place, "note": note,
                           **check(verify, r, text), "text": text})
    if not args.no_paraphrase:
        port = default_port()
        pool = [r for r in base if "#" in r["final_text"]]
        made = 0
        tries = 0
        while made < args.paraphrase_n and tries < args.paraphrase_n * 3 and pool:
            tries += 1
            r = pool[tries % len(pool)]
            got = paraphrase(port, r, rng)
            if got is None:
                continue
            text, note = got
            if len(re.findall(r"\d", text)) > len(re.findall(r"\d", r["final_text"])):
                continue  # the rule: no new number
            copies.append({"answer": r["id"], "class": "paraphrase", "placement": "inplace",
                           "note": note, **check(verify, r, text), "text": text})
            made += 1
    with out.open("w") as fh:
        for c in copies:
            fh.write(json.dumps(c) + "\n")
    summary = {"base_answers": len(base), "originals_flagged": originals_flagged, "classes": {}}
    for cls in ("bad_cite", "unread_cite", "date", "author", "venue", "amount", "paraphrase"):
        cs = [c for c in copies if c["class"] == cls]
        entry = {"n": len(cs), "caught": sum(c["caught"] for c in cs)}
        entry["recall"] = round(entry["caught"] / len(cs), 4) if cs else None
        entry["recall_ci95"] = wilson(entry["caught"], len(cs))
        for place in ("inplace", "prose", "factline"):
            ps = [c for c in cs if c["placement"] == place]
            if ps:
                k = sum(c["caught"] for c in ps)
                entry[place] = {"n": len(ps), "caught": k, "recall": round(k / len(ps), 4),
                                "ci95": wilson(k, len(ps))}
        summary["classes"][cls] = entry
    (HERE / "data" / f"inject_{args.tag}_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
