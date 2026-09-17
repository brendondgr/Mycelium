"""EXP-2026-09-003 — one reader's grant and conference slates through TypeSafe.

    uv run --project eval python .../code/run.py --user brendondgr --dry-run
    uv run --project eval python .../code/run.py --user brendondgr

Reads the reader's current per-theme slates out of the production store, builds
one state per (theme, item) pair from the *production* profile and brief text,
asks TypeSafe three typed questions per pair in one call, and writes
``data/pairs.json``. Analysis is a separate script so it never re-bills.

The reader's profile text is sent and never written here: ``pairs.json`` keeps
its SHA-256 and length only. Opportunity text is public.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
if os.environ.get("MYCELIUM_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["MYCELIUM_DATABASE_URL"]

import django

django.setup()

from apps.content.clustering import cluster_interests
from apps.content.models import ContentItem, RelevanceScore
from apps.content.opportunity_llm import (
    _candidate_brief,
    _clean,
    _profile_text,
)
from apps.content.targets import target_for_user
from apps.content.verdicts import FILE, READ, SKIM, SKIP, VERDICT_BLURBS
from apps.core.systemone import (
    build_systemone_client,
    is_pinned,
    noul,
    score,
)
from django.contrib.auth.models import User

AREAS = {"grant": ContentItem.Type.GRANT, "conference": ContentItem.Type.CONFERENCE}
#: Low to high. The Score's level index is therefore 0 = skip … 3 = read.
LEVELS = (SKIP, FILE, SKIM, READ)
PRICE_PER_MILLION_INPUT_USD = 0.042
PRICE_READ_ON = "2026-09-17"
DETERMINISM_PAIRS = 5
DETERMINISM_REPEATS = 3


def log(message: str) -> None:
    print(f"[exp-003] {message}", flush=True)


# -- questions ---------------------------------------------------------------


def questions_for(area: str) -> dict:
    fit = score(
        "Where does this opportunity sit for THIS strand of the researcher's "
        "work? Judge fit to the strand's listed interests and the researcher's "
        "stated methods, not to the researcher in general.",
        [
            (
                f"Skip. {VERDICT_BLURBS[SKIP]} Off-topic for this strand, or only "
                "superficially related."
            ),
            f"File. {VERDICT_BLURBS[FILE]} On-topic but not something to act on now.",
            (
                f"Skim. {VERDICT_BLURBS[SKIM]} Clearly relevant; worth reading the "
                "summary to decide."
            ),
            (
                f"Read. {VERDICT_BLURBS[READ]} A strong, specific match to this strand "
                "that the researcher should act on."
            ),
        ],
    )
    worth = noul(
        "Is this opportunity worth this researcher's attention today, for this "
        "strand of their work?",
        true=(
            "The opportunity's scope matches this strand's listed interests "
            "specifically enough that the researcher could realistically pursue it."
        ),
        false=(
            "The opportunity is generic, aimed at a different field or method, or "
            "matches only a shared word rather than the strand's actual work."
        ),
    )
    out = {"fit": fit, "worth": worth}
    if area == "grant":
        out["eligible"] = noul(
            "Can this researcher, at their stated career stage and institution, "
            "plausibly apply to this grant as a principal or co-investigator?",
            true="The stated eligibility and applicant types include someone in "
            "the researcher's position, or place no restriction that excludes them.",
            false="The eligibility text names a category (career stage, "
            "institution type, nationality, organisation) that excludes the "
            "researcher.",
        )
    else:
        out["venue_fit"] = noul(
            "Would a paper from this strand be in scope for this conference's "
            "call, as the call describes its topics and tracks?",
            true="The call's scope or tracks name the strand's topics or methods.",
            false="The call is for a different community; the strand would be "
            "out of scope or a poor fit for the tracks listed.",
        )
    return out


# -- data --------------------------------------------------------------------


def opportunity_block(area: str, item: ContentItem) -> dict:
    meta = item.metadata or {}
    block: dict = {"brief": _candidate_brief(AREAS[area], 1, item)}
    if area == "grant":
        eligibility = meta.get("eligibility")
        if isinstance(eligibility, list):
            eligibility = "; ".join(_clean(e) for e in eligibility if _clean(e))
        block["eligibility"] = _clean(eligibility)[:900]
        applicants = meta.get("applicant_types")
        if isinstance(applicants, list):
            block["applicant_types"] = [_clean(a) for a in applicants if _clean(a)][:12]
    return block


def stored_verdict(signals: dict, cluster_id: str) -> str | None:
    writeup = ((signals.get("writeups") or {}).get(cluster_id)) or {}
    return writeup.get("verdict") or signals.get("verdict")


def load_pairs(username: str) -> tuple[dict, list[dict]]:
    user = User.objects.get(username=username)
    target = target_for_user(user)
    profile_text = _profile_text(target.interests, target.profile_meta)
    clusters = {c.id: c for c in cluster_interests(target.interests)}
    researcher = {
        "sha256": hashlib.sha256(profile_text.encode()).hexdigest(),
        "chars": len(profile_text),
        "n_clusters": len(clusters),
    }
    pairs: list[dict] = []
    skipped = 0
    for area, content_type in AREAS.items():
        rows = (
            RelevanceScore.objects.filter(target_user=user, content__type=content_type)
            .select_related("content")
            .order_by("id")
        )
        for row in rows:
            signals = row.signals or {}
            slates = signals.get("cluster_slates") or {}
            for cluster_id, entry in slates.items():
                cluster = clusters.get(cluster_id)
                if cluster is None:
                    skipped += 1
                    continue
                meta = row.content.metadata or {}
                pairs.append(
                    {
                        "area": area,
                        "content_id": str(row.content_id),
                        "title": _clean(meta.get("title") or meta.get("name")) or "(untitled)",
                        "deadline_date": meta.get("deadline_date"),
                        "cluster_id": cluster_id,
                        "cluster_label": cluster.label,
                        "rank": int(entry.get("rank") or 0),
                        "of": int(entry.get("of") or 0),
                        "is_new": bool(entry.get("is_new")),
                        "entered_on": entry.get("entered_on"),
                        "stored_verdict": stored_verdict(signals, cluster_id),
                        "combined_score": signals.get("combined_score"),
                        "embedding_match": signals.get("embedding_match"),
                        "_state": {
                            "researcher": profile_text,
                            "strand": {"label": cluster.label, "interests": list(cluster.areas)},
                            "opportunity": opportunity_block(area, row.content),
                        },
                    }
                )
    if skipped:
        log(f"skipped {skipped} slate entries whose theme is no longer declared")
    pairs.sort(key=lambda p: (p["area"], p["cluster_id"], p["rank"]))
    return researcher, pairs


# -- the run -----------------------------------------------------------------


def ask_one(client, model: str, pair: dict) -> dict:
    started = time.perf_counter()
    try:
        result = client.ask(pair["_state"], questions_for(pair["area"]), model=model)
    except Exception as exc:  # noqa: BLE001 — a failed pair is a recorded pair
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "latency_ms": (time.perf_counter() - started) * 1000,
        }
    return {
        "ok": True,
        "model": result.model,
        "request_id": result.request_id,
        "answers": result.answers_as_dicts(),
        "usage": dict(result.usage),
        "latency_ms": (time.perf_counter() - started) * 1000,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--model", default=None, help="defaults to TYPESAFE_MODEL")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true", help="build states, send nothing")
    args = parser.parse_args()

    from django.conf import settings

    model = args.model or settings.TYPESAFE_MODEL
    if not is_pinned(model):
        log(f"refusing to run against alias {model!r}; pin a version")
        return 2

    researcher, pairs = load_pairs(args.user)
    by_area = {a: sum(1 for p in pairs if p["area"] == a) for a in AREAS}
    log(f"{len(pairs)} (theme, item) pairs: {by_area}; researcher block {researcher['chars']} chars")

    data_dir = EXP_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    if args.dry_run:
        est_tokens = sum(len(json.dumps(p["_state"])) for p in pairs) / 4
        dry = {
            "user": args.user,
            "model": model,
            "pairs": len(pairs),
            "by_area": by_area,
            "by_theme": _count_by(pairs, "cluster_label"),
            "estimated_input_tokens": int(est_tokens),
            "estimated_cost_usd": round(est_tokens / 1e6 * PRICE_PER_MILLION_INPUT_USD, 4),
            "sample_state_chars": len(json.dumps(pairs[0]["_state"])) if pairs else 0,
        }
        (data_dir / "dry_run.json").write_text(json.dumps(dry, indent=1))
        log(f"dry run written: {dry}")
        return 0

    client = build_systemone_client(component="exp_2026_09_003")
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda p: ask_one(client, model, p), pairs))
    for pair, result in zip(pairs, results, strict=True):
        pair["typesafe"] = result
    failures = sum(1 for r in results if not r["ok"])
    log(f"{len(pairs) - failures}/{len(pairs)} pairs answered; {failures} failed")

    # Determinism: the first N answered pairs, asked again, twice more.
    repeat_pairs = [p for p in pairs if p["typesafe"]["ok"]][:DETERMINISM_PAIRS]
    determinism = []
    for pair in repeat_pairs:
        repeats = [pair["typesafe"]] + [
            ask_one(client, model, pair) for _ in range(DETERMINISM_REPEATS - 1)
        ]
        determinism.append(
            {
                "content_id": pair["content_id"],
                "cluster_id": pair["cluster_id"],
                "answers": [r.get("answers") for r in repeats],
                "usage": [r.get("usage") or {"input_tokens": 0, "output_tokens": 0} for r in repeats],
                "ok": all(r["ok"] for r in repeats),
            }
        )
    wall = time.time() - started

    answered = [p["typesafe"] for p in pairs if p["typesafe"]["ok"]]
    input_tokens = sum(r["usage"]["input_tokens"] for r in answered)
    output_tokens = sum(r["usage"]["output_tokens"] for r in answered)
    # The determinism repeats cost tokens too; the first entry of each is the
    # main call, already counted above.
    extra_calls = sum(len(d["usage"]) - 1 for d in determinism)
    extra_input = sum(sum(u["input_tokens"] for u in d["usage"][1:]) for d in determinism)
    for pair in pairs:
        pair.pop("_state", None)
    payload = {
        "meta": {
            "experiment": "EXP-2026-09-003",
            "user": args.user,
            "model": model,
            "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "researcher": researcher,
            "price_per_million_input_usd": PRICE_PER_MILLION_INPUT_USD,
            "price_read_on": PRICE_READ_ON,
            "concurrency": args.concurrency,
        },
        "totals": {
            "calls": len(pairs) + extra_calls,
            "failures": failures,
            "input_tokens_main": input_tokens,
            "output_tokens_main": output_tokens,
            "input_tokens_determinism_extra": extra_input,
            "wall_seconds": round(wall, 2),
        },
        "pairs": pairs,
        "determinism": determinism,
    }
    out = data_dir / "pairs.json"
    out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    log(f"written {out} — {input_tokens} input tokens on the main pass, {wall:.1f}s wall")
    return 0 if failures <= len(pairs) * 0.1 else 1


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row[key]] = out.get(row[key], 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
