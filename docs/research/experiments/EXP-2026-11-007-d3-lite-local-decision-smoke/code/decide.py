"""EXP-2026-11-007 — ask the local Decisions server the production questions.

    python3 code/decide.py --states <scratch>/states.json --url http://127.0.0.1:5107

Stdlib only; runs on the host (the backend container cannot reach the host's
127.0.0.1). Reads the states ``extract.py`` built, translates the production
``typesafe_rerank.questions_for`` into the server's ``yesno``/``score`` schema,
asks one call per pair, then repeats a few pairs for determinism. Writes
``data/pairs.json`` with every answer and the reader's profile reduced to its
SHA-256 and length.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent

# The production wording, from tools/recommendation/typesafe_rerank.py
# (QUESTION_VERSION 2026-09-17.1) and tools/recommendation/verdicts.py.
BLURBS = {
    "skip": "Probably not worth your time.",
    "file": "Relevant, but not urgent. Keep it for later.",
    "skim": "Worth a look — the abstract may be enough.",
    "read": "Worth your attention today.",
}
LEVELS = ("skip", "file", "skim", "read")


def yesno(qid: str, instructions: str, true: str, false: str) -> dict:
    return {
        "id": qid,
        "type": "yesno",
        "question": f"{instructions} Answer yes if: {true} Answer no if: {false}",
    }


def questions_for(content_type: str) -> list[dict]:
    out = [
        yesno(
            "worth",
            "Is this item worth this researcher's attention today, for this "
            "strand of their work?",
            "The item's subject matches this strand's listed interests "
            "specifically enough that the researcher could realistically act on "
            "it — read it, apply, submit, or build on it.",
            "The item is generic, aimed at a different field or method, or "
            "matches only a shared word rather than the strand's actual work.",
        ),
        {
            "id": "fit",
            "type": "score",
            "question": (
                "Where does this item sit for THIS strand of the researcher's "
                "work? Judge fit to the strand's listed interests and the "
                "researcher's stated methods, not to the researcher in general."
            ),
            "scale": [
                f"Skip. {BLURBS['skip']} Off-topic for this strand, or only "
                "superficially related.",
                f"File. {BLURBS['file']} On-topic but not something to act on now.",
                f"Skim. {BLURBS['skim']} Clearly relevant; worth reading the "
                "summary to decide.",
                f"Read. {BLURBS['read']} A strong, specific match to this strand "
                "that the researcher should act on.",
            ],
        },
    ]
    if content_type == "grant":
        out.append(
            yesno(
                "eligible",
                "Can this researcher, at their stated career stage and "
                "institution, plausibly apply to this grant as a principal or "
                "co-investigator?",
                "The stated eligibility and applicant types include someone in "
                "the researcher's position, or place no restriction that "
                "excludes them.",
                "The eligibility text names a category (career stage, "
                "institution type, nationality, organisation) that excludes the "
                "researcher.",
            )
        )
    elif content_type == "conference":
        out.append(
            yesno(
                "venue_fit",
                "Would a paper from this strand be in scope for this "
                "conference's call, as the call describes its topics and tracks?",
                "The call's scope or tracks name the strand's topics or methods.",
                "The call is for a different community; the strand would be out "
                "of scope or a poor fit for the tracks listed.",
            )
        )
    return out


def ask(url: str, state: dict, questions: list[dict]) -> dict:
    body = json.dumps({"input": state, "questions": questions}).encode()
    req = urllib.request.Request(
        f"{url}/v1/decide", data=body, headers={"content-type": "application/json"}
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 — a failed pair is a recorded pair
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    wall = (time.perf_counter() - started) * 1000
    answers = raw.get("answers") or {}
    out: dict = {
        "ok": not any("error" in a for a in answers.values()),
        "model": raw.get("model"),
        "revision": raw.get("revision"),
        "server_ms": raw.get("ms"),
        "model_ms": raw.get("model_ms"),
        "wall_ms": round(wall, 1),
    }
    for qid, a in answers.items():
        if "error" in a:
            out[qid] = {"error": a.get("error"), "message": a.get("message")}
        elif "value" in a:  # score: probabilities in scale order -> level index
            probs = list(a["probs"].values())
            out[qid] = {
                "value": a["value"],
                "probs": [round(p, 6) for p in probs],
                "argmax": LEVELS[max(range(len(probs)), key=probs.__getitem__)],
            }
        else:
            out[qid] = {"yes": a["probs"]["yes"]}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:5107")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    src = json.loads(Path(args.states).read_text())
    pairs = src["pairs"]
    profile = pairs[0]["state"]["researcher"] if pairs else ""

    with urllib.request.urlopen(f"{args.url}/v1/models", timeout=10) as resp:
        models = json.loads(resp.read())

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(
            pool.map(
                lambda p: ask(args.url, p["state"], questions_for(p["content_type"])),
                pairs,
            )
        )
    wall = time.time() - started

    determinism = []
    for p in [p for p in pairs if not p["control"]][:: max(1, len(pairs) // 5)][:5]:
        reps = [ask(args.url, p["state"], questions_for(p["content_type"])) for _ in range(3)]
        determinism.append(
            {
                "content_id": p["content_id"],
                "cluster_id": p["cluster_id"],
                "worth": [r.get("worth", {}).get("yes") for r in reps],
            }
        )

    records = []
    for p, r in zip(pairs, results, strict=True):
        rec = {k: v for k, v in p.items() if k != "state"}
        rec["state_chars"] = len(json.dumps(p["state"]))
        rec["d3"] = r
        records.append(rec)

    payload = {
        "meta": {
            "experiment": "EXP-2026-11-007",
            "user": src["user"],
            "n_clusters": src["n_clusters"],
            "question_version": src["question_version"],
            "server": args.url,
            "models": models.get("models"),
            "concurrency": args.concurrency,
            "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "researcher": {
                "sha256": hashlib.sha256(profile.encode()).hexdigest(),
                "chars": len(profile),
            },
        },
        "totals": {
            "calls": len(pairs) + 3 * len(determinism),
            "failures": sum(1 for r in results if not r["ok"]),
            "wall_seconds_main": round(wall, 2),
        },
        "pairs": records,
        "determinism": determinism,
    }
    out = EXP_DIR / "data" / "pairs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"{len(pairs)} pairs, {payload['totals']['failures']} failed, {wall:.1f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
