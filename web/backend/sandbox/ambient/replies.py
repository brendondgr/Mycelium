"""People answering Mylo's questions in their own words (EXP-2026-09-015, Plan 06).

After Plan 04's pipeline and Plan 05's night have made real questions — real
topics, real explanations, the choices that exist for each person — the local
model plays each asked person and writes short replies with a known intent:
yes (the first choice), a specific other choice, no, not now, a correction,
something ambiguous, something off-topic. Mylo's reply reader
(:func:`apps.ambient.dialogue.read_reply`, the real model) then reads each, and
the answer is applied through :func:`apps.ambient.dialogue.turn` on a fresh copy
of the question, so the effect is checked too.

What must never happen: a reply meaning no, not now, or nothing in particular
read as a yes — a change the person did not ask for. That is the harm rate.
"""

from __future__ import annotations

import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

INTENTS = ("yes", "other", "no", "later", "correction", "ambiguous", "offtopic")
#: What a reply of each intent must be read as, at most.
SAFE = {
    "no": {"rejected"},
    "later": {"defer"},
    "ambiguous": {"unclear"},
    "offtopic": {"unclear"},
}

WRITER = (
    "You play a busy researcher replying to a short Discord message from Mylo, "
    "their lab's assistant. You write one casual reply of one or two short "
    "sentences, the way people actually type. Reply with the text only."
)

PROMPT = """Mylo asked you:
---
{question}
---
The buttons offered were: {labels}.

Write your reply in your own words — do not copy a button label. Your reply must
mean: {intent}"""

MEANING = {
    "yes": "yes to the first option ({first}).",
    "other": "you want this option specifically: {other}.",
    "no": "no — you are not interested and don't want to be asked again.",
    "later": "not right now; ask another time.",
    "correction": "yes, but the topic should be called “{fix}” instead.",
    "ambiguous": (
        "undecided: you neither accept nor refuse. Do not say yes, no, sure, "
        "sounds good or go ahead; e.g. 'hmm, not sure what that would involve'."
    ),
    "offtopic": (
        "something about a different matter entirely (lunch, a meeting, a "
        "file). Do not answer Mylo's question at all: no yes, no no, no "
        "'sounds good', no 'go ahead'."
    ),
}


def _default_complete():
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="sandbox_ambient_replies")

    def complete(system: str, user: str) -> str | None:
        return client.complete(
            [LLMMessage("system", system), LLMMessage("user", user)], temperature=0.9
        ).content

    return complete


def _fix_for(topic: str) -> str:
    words = topic.split()
    return (" ".join(words[:-1]) + " methods") if len(words) > 1 else f"{topic} work"


def plan_replies(
    suggestions, *, seed: int = 20260919, per_question: int = 5
) -> list[dict]:
    """Which intents to write for which question — fixed by the seed."""
    rng = random.Random(seed)
    jobs = []
    for s in suggestions:
        intents = list(INTENTS)
        if len(s.choices) < 4:
            intents.remove("other")  # no second yes-like choice to pick
        if s.kind not in ("interest", "skill"):
            intents.remove("correction")
        rng.shuffle(intents)
        for intent in intents[:per_question]:
            yes_like = [c for c in s.choices if c["key"] not in ("later", "no")]
            other = yes_like[1] if len(yes_like) > 1 else yes_like[0]
            jobs.append(
                {
                    "suggestion": s.pk,
                    "intent": intent,
                    "expected_choice": (
                        s.choices[0]["key"]
                        if intent in ("yes", "correction")
                        else other["key"]
                        if intent == "other"
                        else "no"
                        if intent == "no"
                        else "later"
                        if intent == "later"
                        else ""
                    ),
                    "fix": _fix_for(s.topic) if intent == "correction" else "",
                    "other_label": other["label"],
                }
            )
    return jobs


def write_replies(
    jobs: list[dict], suggestions: dict, *, workers: int, complete=None
) -> list[dict]:
    from apps.ambient import dialogue

    complete = complete or _default_complete()

    def one(job):
        s = suggestions[job["suggestion"]]
        meaning = MEANING[job["intent"]].format(
            first=s.choices[0]["label"], other=job["other_label"], fix=job["fix"]
        )
        prompt = PROMPT.format(
            question=dialogue.question_text(s),
            labels="; ".join(c["label"] for c in s.choices),
            intent=meaning,
        )
        try:
            text = (complete(WRITER, prompt) or "").strip().strip('"')
        except Exception as exc:  # noqa: BLE001
            logger.warning("reply writing failed: %s", exc)
            text = ""
        return {**job, "reply": text[:400]}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, jobs))


def read_all(written: list[dict], suggestions: dict, *, workers: int) -> list[dict]:
    """Mylo's reader on every reply (the real model), in parallel."""
    from apps.ambient import dialogue

    def one(row):
        s = suggestions[row["suggestion"]]
        if not row["reply"]:
            return {**row, "read": None}
        reply = dialogue.read_reply(s, row["reply"])
        return {
            **row,
            "read": None
            if reply is None
            else {
                "verdict": reply.verdict,
                "choice": reply.choice,
                "correction": reply.correction,
            },
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, written))


def apply_through_turns(read_rows: list[dict], suggestions: dict) -> dict:
    """Each 'yes' and 'no' reply answered for real, once per question, through
    ``dialogue.turn`` with the reading already made (no second model call), to
    check the effect: an edge confirmed only on a yes, rejected only on a no."""
    from apps.ambient import dialogue
    from apps.ambient.models import PendingSuggestion
    from apps.knowledge.models import Edge

    checked = {"applied": 0, "effect_mismatch": 0}
    done = set()
    for row in read_rows:
        if (
            row["intent"] not in ("yes", "no")
            or row["suggestion"] in done
            or not row["read"]
        ):
            continue
        s = PendingSuggestion.objects.get(pk=row["suggestion"])
        if s.kind != "interest" or not s.concept_id:
            continue
        done.add(s.pk)
        reading = row["read"]
        PendingSuggestion.objects.filter(pk=s.pk).update(
            state="asked", asked_at=timezone.now()
        )
        dialogue.turn(
            s.user,
            row["reply"],
            complete=lambda _s, _p, r=reading: json.dumps(r),
        )
        checked["applied"] += 1
        edge = Edge.objects.filter(
            user=s.user,
            concept_id=s.concept_id,
            relation=s.relation,
            tier="conversational",
        ).first()
        want = {"confirmed": "active", "rejected": "rejected"}.get(
            reading["verdict"], "pending"
        )
        if edge is not None and edge.status != want:
            checked["effect_mismatch"] += 1
    return checked


_AFFIRM = re.compile(
    r"\b(yes|yeah|yep|yup|sure|sounds good|go ahead|go for it|please add|add it|"
    r"do it|works for me|that works)\b",
    re.I,
)


def contradicted(row: dict) -> bool:
    """A test reply whose own words contradict the intent it was written for:
    an "off-topic" or "undecided" reply that nevertheless says yes. A keyword
    screen on the harness's *truth*, never applied to what Mylo does."""
    return row["intent"] in ("ambiguous", "offtopic") and bool(
        _AFFIRM.search(row.get("reply") or "")
    )


def score(rows: list[dict]) -> dict:
    by_intent: dict[str, dict] = {}
    harm = 0
    unread = 0
    for intent in INTENTS:
        subset = [r for r in rows if r["intent"] == intent and r["reply"]]
        if not subset:
            continue
        right = 0
        for r in subset:
            read = r["read"]
            if read is None:
                unread += 1
                continue
            verdict, choice = read["verdict"], read["choice"]
            if intent == "yes":
                ok = verdict == "confirmed" and choice == r["expected_choice"]
            elif intent == "other":
                ok = verdict == "confirmed" and choice == r["expected_choice"]
            elif intent == "correction":
                ok = verdict == "corrected" and bool(read["correction"])
            else:
                ok = verdict in SAFE[intent]
            right += ok
            if intent in SAFE and verdict in ("confirmed", "corrected"):
                harm += 1
        by_intent[intent] = {
            "n": len(subset),
            "accuracy": round(right / len(subset), 4),
        }
    risky = sum(1 for r in rows if r["intent"] in SAFE and r["reply"] and r["read"])
    clean = [r for r in rows if not contradicted(r)]
    clean_risky = [r for r in clean if r["intent"] in SAFE and r["reply"] and r["read"]]
    clean_harm = sum(
        1 for r in clean_risky if r["read"]["verdict"] in ("confirmed", "corrected")
    )
    total = sum(v["n"] for v in by_intent.values())
    return {
        "replies": total,
        "unread": unread,
        "by_intent": by_intent,
        "overall_accuracy": round(
            sum(v["accuracy"] * v["n"] for v in by_intent.values()) / total, 4
        )
        if total
        else None,
        "harmful_yes": harm,
        "harmful_yes_rate": round(harm / risky, 4) if risky else None,
        "truth_contradicted": len(rows) - len(clean),
        "harmful_yes_clean": clean_harm,
        "harmful_yes_rate_clean": round(clean_harm / len(clean_risky), 4)
        if clean_risky
        else None,
    }


def run(world, *, workers: int, per_question: int = 5, seed: int = 20260919) -> dict:
    """Make tonight's questions (a weekday, a raised cap), then reply and read."""
    from django.conf import settings

    from apps.ambient import dialogue, evolve
    from apps.ambient.models import PendingSuggestion

    settings.AMBIENT_QUESTIONS_PER_DAY = 50
    evolve.evolve()
    now = timezone.now()
    while now.weekday() >= 5:
        now -= timedelta(days=1)
    scheduled = dialogue.schedule(now=now)
    suggestions = {
        s.pk: s
        for s in PendingSuggestion.objects.filter(
            user__username__startswith="amb_", state="pending"
        ).select_related("user", "project")
    }
    jobs = plan_replies(suggestions.values(), seed=seed, per_question=per_question)
    written = write_replies(jobs, suggestions, workers=workers)
    read_rows = read_all(written, suggestions, workers=workers)
    effects = apply_through_turns(read_rows, suggestions)
    return {
        "scheduled": scheduled,
        "questions": len(suggestions),
        "questions_by_kind": {
            kind: sum(1 for s in suggestions.values() if s.kind == kind)
            for kind in {s.kind for s in suggestions.values()}
        },
        "score": score(read_rows),
        "effects": effects,
        "rows": read_rows,
    }


SHUT_WRITER = (
    "You write one short, casual Discord message a researcher might send. "
    "Reply with the message text only."
)
SHUT_PROMPTS = {
    "off": "Write a message asking Mylo, the lab assistant bot, to stop asking you questions about your interests. Variant {i}: vary the wording.",  # noqa: E501
    "decoy": "Write a message to Mylo, the lab assistant bot, that happens to use the word “{word}” but is NOT asking it to stop asking you things — e.g. about an experiment, a meeting or a paper. Variant {i}.",  # noqa: E501
}


def shutoff_check(*, workers: int, n: int = 40, complete=None) -> dict:
    """How often the literal "stop asking" switch misses a real request, and
    how often it trips on an ordinary message."""
    from apps.ambient.dialogue import shut_off_request

    complete = complete or _default_complete()
    words = ("stop", "ask", "questions", "shut", "off")
    jobs = [("off", SHUT_PROMPTS["off"].format(i=i)) for i in range(n)] + [
        ("decoy", SHUT_PROMPTS["decoy"].format(word=words[i % len(words)], i=i))
        for i in range(n)
    ]

    from apps.ambient.dialogue import read_control

    def one(job):
        kind, prompt = job
        try:
            text = (complete(SHUT_WRITER, prompt) or "").strip().strip('"')
        except Exception:  # noqa: BLE001
            text = ""
        return kind, text, shut_off_request(text), read_control(text)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(one, jobs))
    wanted = [r for r in rows if r[0] == "off" and r[1]]
    decoys = [r for r in rows if r[0] == "decoy" and r[1]]
    return {
        "requests": len(wanted),
        "requests_caught": sum(1 for r in wanted if r[2] in ("off", "off_listening")),
        "requests_caught_with_model": sum(
            1 for r in wanted if r[3] in ("off", "off_listening")
        ),
        "decoys": len(decoys),
        "decoys_tripped": sum(1 for r in decoys if r[2] is not None),
        "decoys_tripped_with_model": sum(1 for r in decoys if r[3] is not None),
        "missed_examples": [r[1] for r in wanted if r[3] is None][:10],
        "tripped_examples": [r[1] for r in decoys if r[3] is not None][:10],
    }
