"""EXP-2026-08-006 — how long does the extraction backfill actually take?

Measures *verified records per second* for the Phase 8 structured-extraction
loop against Mycelium's own LLM endpoint, across reasoning arms and worker
counts. Verified, not raw calls: a cheap setting that fails validation and costs
two repair attempts is not cheap, and calls/sec would hide that.

Run from the repository root:

    DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium \
    uv run --directory web/backend python \
      ../../docs/research/experiments/EXP-2026-08-006-extraction-throughput/code/run.py

Writes ``data/metrics.json`` and ``data/metrics.csv`` next to this file's parent.
Nothing here is imported by application code.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = EXP_DIR / "data"
#: The collector's SQLite stores. Set COLLECT_DIR to the store the run read
#: (at the time, the standalone collector's ``data/collect``); the default is
#: the repository's own ``data/collect``.
COLLECT = Path(
    os.environ.get("COLLECT_DIR") or EXP_DIR.parents[3] / "data" / "collect"
)

#: Fixed so the sample is reproducible. The keys drawn are written to
#: data/sample.json — the seed alone is not a reproducibility guarantee once the
#: upstream store changes.
SEED = 20260816

#: Bounded so a record can never spin. Matches plan Phase 8.
MAX_ATTEMPTS = 3

#: The corpus this projects to: 2,190 grants + 2,234 conference instances.
BACKFILL_RECORDS = 4_424


# --------------------------------------------------------------------------- #
# The structured-output contract (plan §8.2)
# --------------------------------------------------------------------------- #

GRANT_KEYS = {
    "summary": str,
    "purpose": str,
    "audience": str,
    "research_areas": list,
    "eligibility": str,
    "award_summary": str,
    "confidence": str,
}

CONFERENCE_KEYS = {
    "summary": str,
    "purpose": str,
    "audience": str,
    "topics": list,
    "field": str,
    "confidence": str,
}

GRANT_PROMPT = """You are extracting a structured description of a funding opportunity.

Return ONLY a JSON object with exactly these keys:
  "summary"        2-3 sentences: what this funds and why it exists
  "purpose"        one sentence: the funder's stated goal
  "audience"       one sentence: who this is for
  "research_areas" array of 2-6 short topic strings
  "eligibility"    one paragraph, or "" if the source does not state it
  "award_summary"  plain-language money line, or ""
  "confidence"     "high", "medium" or "low"

Every claim must be supported by the source text below. Do not add a number, a
date or an amount that does not appear in it. If the source does not say
something, use "".

SOURCE:
{source}
"""

CONFERENCE_PROMPT = """You are extracting a structured description of an academic conference.

Return ONLY a JSON object with exactly these keys:
  "summary"    2-3 sentences: what this venue is about
  "purpose"    one sentence
  "audience"   one sentence
  "topics"     array of 2-6 short topic strings
  "field"      the discipline in plain words
  "confidence" "high", "medium" or "low"

Every claim must be supported by the source text below. Do not invent dates,
locations or statistics. If the source is thin, say so via "confidence": "low"
rather than filling gaps from general knowledge.

SOURCE:
{source}
"""


# --------------------------------------------------------------------------- #
# Deterministic validators — the same checks Phase 8 will use. No model, no I/O.
# --------------------------------------------------------------------------- #

_WORD = re.compile(r"[a-z0-9]+")

#: Words too common to count as evidence that a claim came from the source.
_STOP = frozenset(
    "the a an and or of for to in on at by with from is are be this that it as "
    "we our their its will can may all any more most other than which who".split()
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def overlap_ratio(claim: str, source: str) -> float:
    """Fraction of the claim's content words that appear in the source.

    The collector checks summary+purpose+audience as one atomic block, and its
    docstring records why: checking only the summary let a placeholder page's
    purpose and audience — written from the same priors in the same breath —
    through unchecked. We keep that.
    """
    claim_words = _words(claim)
    if not claim_words:
        return 0.0
    return len(claim_words & _words(source)) / len(claim_words)


PROSE_FLOOR = 0.45


def validate(payload: object, source: str, kind: str) -> list[str]:
    """Return a list of failure reasons. Empty list means verified."""
    schema = GRANT_KEYS if kind == "grant" else CONFERENCE_KEYS
    fails: list[str] = []

    if not isinstance(payload, dict):
        return ["malformed: reply is not a JSON object"]

    for key, typ in schema.items():
        if key not in payload:
            fails.append(f"malformed: missing key {key!r}")
        elif not isinstance(payload[key], typ):
            fails.append(
                f"malformed: {key!r} should be {typ.__name__}, "
                f"got {type(payload[key]).__name__}"
            )
    if fails:
        return fails

    if payload["confidence"] not in {"high", "medium", "low"}:
        fails.append(
            f"out_of_bounds: confidence {payload['confidence']!r} "
            "is not high/medium/low"
        )
    if not 40 <= len(payload["summary"]) <= 900:
        fails.append(
            f"out_of_bounds: summary is {len(payload['summary'])} chars, want 40-900"
        )

    listkey = "research_areas" if kind == "grant" else "topics"
    items = payload[listkey]
    if not 2 <= len(items) <= 6:
        fails.append(f"out_of_bounds: {listkey} has {len(items)} entries, want 2-6")
    if len({str(i).strip().lower() for i in items}) != len(items):
        fails.append(f"out_of_bounds: {listkey} contains duplicates")

    # Prose grounding, as one atomic block.
    prose = " ".join(
        str(payload[k]) for k in ("summary", "purpose", "audience")
    )
    ratio = overlap_ratio(prose, source)
    if ratio < PROSE_FLOOR:
        fails.append(
            f"ungrounded_prose: summary+purpose+audience overlap the source at "
            f"{ratio:.2f}, floor is {PROSE_FLOOR}"
        )

    # Topic grounding: every entry shares a word with the source.
    source_words = _words(source)
    for item in items:
        if not (_words(str(item)) & source_words):
            fails.append(f"ungrounded_topic: {str(item)!r} shares no word with the source")

    return fails


def parse_reply(text: str) -> object:
    """Take the first {...} block. Models wrap JSON in prose more often than not."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Sampling — real records, because prompt length drives latency
# --------------------------------------------------------------------------- #


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def sample_records() -> list[dict]:
    """16 grants stratified across the four sources with rows, + 16 conferences.

    32 total: a round number that divides evenly by every worker count in the
    sweep (4, 8, 16) except 12, so no cell is decided by a ragged final batch.
    """
    import random

    rng = random.Random(SEED)
    out: list[dict] = []

    con = _ro(COLLECT / "opportunities.db")
    for source, n in (("nsf", 4), ("eu_portal", 4), ("grants_gov", 4), ("nih_guide", 4)):
        rows = con.execute(
            "select stable_key, title, funder, description, eligibility, categories "
            "from opportunities where source = ? and length(description) > 200",
            (source,),
        ).fetchall()
        for key, title, funder, desc, elig, cats in rng.sample(rows, min(n, len(rows))):
            out.append(
                {
                    "key": key,
                    "kind": "grant",
                    "source": source,
                    "text": f"Title: {title}\nFunder: {funder}\n"
                    f"Categories: {cats}\n\n{desc}\n\nEligibility: {elig}"[:12000],
                }
            )
    con.close()

    con = _ro(COLLECT / "conferences.db")
    rows = con.execute(
        "select i.instance_key, i.title, i.acronym, i.year_label, i.topics, "
        "       s.full_name, s.field_codes "
        "from instances i left join series s on s.series_key = i.series_key "
        "where i.title != ''"
    ).fetchall()
    for key, title, acronym, year, topics, full, codes in rng.sample(rows, 16):
        out.append(
            {
                "key": key,
                "kind": "conference",
                "source": "conferences",
                # Deliberately thin: cfp_text is "" on all 2,234 rows. This is
                # the hard case and understating it would flatter the result.
                "text": f"Conference: {title}\nAcronym: {acronym} {year}\n"
                f"Series: {full}\nCCF areas: {codes}\nTopics: {topics}",
            }
        )
    con.close()
    return out


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


@dataclass
class CallRecord:
    key: str
    kind: str
    attempts: int = 0
    verified: bool = False
    latencies: list[float] = field(default_factory=list)
    first_attempt_valid: bool = False
    failures: list[str] = field(default_factory=list)
    input_chars: int = 0
    output_chars: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def extract_one(client, rec: dict, *, reasoning: str) -> CallRecord:
    """The bounded agent loop: extract -> validate -> repair -> apply | refuse."""
    out = CallRecord(key=rec["key"], kind=rec["kind"])
    template = GRANT_PROMPT if rec["kind"] == "grant" else CONFERENCE_PROMPT
    prompt = template.format(source=rec["text"])
    out.input_chars = len(prompt)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        out.attempts = attempt
        started = time.monotonic()
        try:
            answer = client.complete(prompt, reasoning=reasoning)
            reply = answer.content or ""
        # Broad on purpose. The client raises LLMConfigurationError, but transport
        # and API errors propagate straight from the OpenAI SDK. Every failure is
        # a retryable `model_failed`, counted — never fatal, and never silently a
        # settled answer: the collector once wrote 321 model_failed rows in one
        # over-concurrent run, and treating those as answers would have excluded
        # 321 records from enrichment permanently.
        except Exception as exc:  # noqa: BLE001
            out.latencies.append(time.monotonic() - started)
            out.failures.append(f"model_failed: {exc}")
            continue
        out.latencies.append(time.monotonic() - started)
        out.output_chars += len(reply)
        usage = answer.usage or {}
        out.input_tokens += int(usage.get("prompt_tokens") or 0)
        out.output_tokens += int(usage.get("completion_tokens") or 0)

        payload = parse_reply(reply)
        fails = (
            ["malformed: no JSON object in reply"]
            if payload is None
            else validate(payload, rec["text"], rec["kind"])
        )
        if not fails:
            out.verified = True
            out.first_attempt_valid = attempt == 1
            return out

        out.failures.extend(fails)
        # Repair: hand the model its specific failures, not a generic retry.
        prompt = (
            f"{template.format(source=rec['text'])}\n\n"
            f"Your previous reply was rejected for these reasons:\n"
            + "\n".join(f"- {f}" for f in fails)
            + "\n\nReturn a corrected JSON object addressing every one."
        )
    return out


def run_cell(records: list[dict], *, style: str, reasoning: str, workers: int) -> dict:
    from apps.core.llm import LLMClient, LLMConfig, ReasoningLevel, ReasoningStyle
    from django.conf import settings

    client = LLMClient(
        LLMConfig(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            timeout=float(settings.LLM_TIMEOUT),
            temperature=0.0,
            max_tokens=int(settings.LLM_MAX_TOKENS),
            reasoning=ReasoningLevel.coerce(reasoning),
            reasoning_style=ReasoningStyle.coerce(style),
        )
    )

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(lambda r: extract_one(client, r, reasoning=reasoning), records)
        )
    wall = time.monotonic() - started

    every_latency = [lat for r in results for lat in r.latencies]
    verified = [r for r in results if r.verified]
    rate = len(verified) / wall if wall else 0.0

    return {
        "arm": f"{style}-{reasoning}",
        "style": style,
        "reasoning": reasoning,
        "workers": workers,
        "n_records": len(records),
        "n_verified": len(verified),
        "wall_clock_s": round(wall, 2),
        "verified_records_per_second": round(rate, 4),
        "median_latency_s": round(statistics.median(every_latency), 2)
        if every_latency
        else None,
        "p95_latency_s": round(
            sorted(every_latency)[int(len(every_latency) * 0.95) - 1], 2
        )
        if len(every_latency) >= 20
        else None,
        "total_calls": len(every_latency),
        "first_attempt_valid_rate": round(
            sum(r.first_attempt_valid for r in results) / len(results), 3
        ),
        "mean_attempts_per_verified_record": round(
            statistics.mean([r.attempts for r in verified]), 2
        )
        if verified
        else None,
        "refusal_rate": round(1 - len(verified) / len(results), 3),
        "projected_backfill_hours": round(BACKFILL_RECORDS / rate / 3600, 2)
        if rate
        else None,
        "failure_reasons": _tally(r.failures for r in results),
        "input_chars_total": sum(r.input_chars for r in results),
        "output_chars_total": sum(r.output_chars for r in results),
        "input_tokens_total": sum(r.input_tokens for r in results),
        "output_tokens_total": sum(r.output_tokens for r in results),
    }


def _tally(groups) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in groups:
        for f in group:
            head = f.split(":", 1)[0]
            counts[head] = counts.get(head, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "web" / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = sample_records()
    (DATA_DIR / "sample.json").write_text(
        json.dumps(
            [{"key": r["key"], "kind": r["kind"], "source": r["source"],
              "prompt_chars": len(r["text"])} for r in records],
            indent=2,
        )
    )
    print(f"sample: {len(records)} records "
          f"({sum(r['kind'] == 'grant' for r in records)} grants, "
          f"{sum(r['kind'] == 'conference' for r in records)} conferences)")

    cells: list[dict] = []

    # Stage A — arm comparison at the plan's concurrency of 12.
    for style, reasoning in (
        ("thinking", "none"),
        ("thinking", "medium"),
        ("effort", "low"),
        ("effort", "medium"),
    ):
        print(f"\n=== stage A: {style}-{reasoning} @ 12 workers ===", flush=True)
        cell = run_cell(records, style=style, reasoning=reasoning, workers=12)
        cell["stage"] = "A"
        cells.append(cell)
        print(
            f"    {cell['verified_records_per_second']} rec/s | "
            f"median {cell['median_latency_s']}s | "
            f"1st-attempt valid {cell['first_attempt_valid_rate']} | "
            f"projected {cell['projected_backfill_hours']}h",
            flush=True,
        )

    # Stage B — concurrency sweep on whichever arm projects fastest. 12 is
    # re-measured here rather than reused from stage A: the proxy is warm by
    # now, so a stage-A number would not be comparable with its neighbours.
    best = min(
        (c for c in cells if c["projected_backfill_hours"]),
        key=lambda c: c["projected_backfill_hours"],
        default=cells[0],
    )
    print(f"\n=== stage B: concurrency sweep on {best['arm']} ===", flush=True)
    for workers in (4, 8, 12, 16):
        cell = run_cell(
            records, style=best["style"], reasoning=best["reasoning"], workers=workers
        )
        cell["stage"] = "B"
        cells.append(cell)
        print(
            f"    {workers:>2} workers: {cell['verified_records_per_second']} rec/s | "
            f"median {cell['median_latency_s']}s | "
            f"p95 {cell['p95_latency_s']}s | "
            f"projected {cell['projected_backfill_hours']}h",
            flush=True,
        )

    (DATA_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "experiment": "EXP-2026-08-006",
                "backfill_records": BACKFILL_RECORDS,
                "max_attempts": MAX_ATTEMPTS,
                "prose_floor": PROSE_FLOOR,
                "seed": SEED,
                "cells": cells,
            },
            indent=2,
        )
    )

    columns = [
        "stage", "arm", "style", "reasoning", "workers", "n_records", "n_verified",
        "wall_clock_s", "verified_records_per_second", "median_latency_s",
        "p95_latency_s", "total_calls", "first_attempt_valid_rate",
        "mean_attempts_per_verified_record", "refusal_rate",
        "projected_backfill_hours",
    ]
    lines = [",".join(columns)]
    lines += [",".join(str(c.get(k, "")) for k in columns) for c in cells]
    (DATA_DIR / "metrics.csv").write_text("\n".join(lines) + "\n")

    print(f"\nwrote {DATA_DIR / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
