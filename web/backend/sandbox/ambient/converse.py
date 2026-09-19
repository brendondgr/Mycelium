"""The conversations around the plants, written by the local model.

Each conversation is handed its plants — who says what, about which topic —
and the model writes 6–12 realistic messages in which each plant is said once,
by its speaker, using the topic phrase, among ordinary filler. A plant the
model left out (wrong speaker, no topic phrase) is dropped from the truth and
counted, never silently kept. Output is cached, so a rerun of the pipeline
reads the same conversations.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from .world import GIST, World

logger = logging.getLogger(__name__)

SYSTEM = (
    "You write realistic, informal chat conversations between members of a "
    "university research lab on Discord. Everyone is fictional. Reply with one "
    "JSON object and nothing else."
)

PROMPT = """Write one conversation {where}, {when}.

People who may speak: {people}.
{mylo}
These things must each be said exactly once, by the person named, in a single
message that uses the exact phrase in quotes (the rest of the message is up to
you, casual and natural, one or two sentences):
{plants}

Add {filler} other short messages of ordinary lab chat (logistics, reactions,
questions about unrelated things) so it reads like a real conversation. Do not
mention the quoted phrases anywhere else.

Reply as {{"messages": [{{"speaker": name, "text": message, "plant": id or null}}]}}
in the order they were sent. Every plant id above must appear exactly once."""

REPAIR = """Your previous answer had these problems:
{problems}
Write the whole conversation again in the same shape."""


def _parse(raw: str | None) -> dict | None:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _check(payload: dict | None, plants: dict, names: set[str]) -> tuple[list, list[str]]:
    if not payload or not isinstance(payload.get("messages"), list):
        return [], ["the reply was not {\"messages\": [...]}"]
    messages = []
    problems = []
    seen: dict[str, int] = {}
    for index, row in enumerate(payload["messages"]):
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker") or "").strip()
        text = " ".join(str(row.get("text") or "").split())
        plant = row.get("plant") or None
        if speaker not in names or not text:
            continue
        if plant is not None:
            plant = str(plant)
            spec = plants.get(plant)
            if spec is None:
                plant = None
            elif speaker != spec["speaker"]:
                problems.append(f"plant {plant} must be said by {spec['speaker']}")
                plant = None
            elif spec["topic"].casefold() not in text.casefold():
                problems.append(f"plant {plant} must use the phrase \"{spec['topic']}\"")
                plant = None
            elif plant in seen:
                plant = None
        if plant:
            seen[plant] = index
        messages.append({"speaker": speaker, "text": text, "plant": plant})
    for plant in plants:
        if plant not in seen:
            problems.append(f"plant {plant} is missing")
    return messages, problems


def _default_complete():
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="sandbox_ambient")

    def complete(system: str, user: str) -> str | None:
        return client.complete(
            [LLMMessage("system", system), LLMMessage("user", user)],
            temperature=0.8,
        ).content

    return complete


def write_one(conversation: dict, world: World, complete) -> dict:
    """One conversation's messages, and which plants made it in."""
    plants = {p.id: p for p in world.plants if p.id in conversation["plants"]}
    lab = next(lab for lab in world.labs if lab.slug == conversation["lab"])
    by_user = {p.username: p for p in lab.people}
    speakers = {by_user[p.person].name for p in plants.values()}
    if conversation["place"] == "dm":
        where = "in a direct message between one person and Mylo, the lab's assistant bot"
        people = next(iter(speakers))
        mylo = "Mylo may answer briefly; its speaker name is Mylo."
        names = {people, "Mylo"}
        filler = "1 or 2"
    else:
        where = f"in the #{conversation['place']} channel of {lab.name}"
        extra = [p.name for p in lab.people if p.name not in speakers]
        extra = extra[: max(1, 4 - len(speakers))]
        people = ", ".join(sorted(speakers) + extra)
        mylo = ""
        names = set(sorted(speakers) + extra)
        filler = "4 to 8"
    specs = {
        pid: {
            "speaker": by_user[p.person].name,
            "topic": p.topic,
        }
        for pid, p in plants.items()
    }
    listed = "\n".join(
        f"- {pid}: {specs[pid]['speaker']} "
        + GIST[p.gist_key].format(t=p.topic, c=p.colleague, p=p.project)
        + f" — phrase \"{p.topic}\""
        for pid, p in plants.items()
    )
    prompt = PROMPT.format(
        where=where,
        when=f"{conversation['day']} days ago",
        people=people,
        mylo=mylo,
        plants=listed,
        filler=filler,
    )
    base = prompt
    best: tuple[list, list[str]] = ([], ["not attempted"])
    for _ in range(2):
        try:
            raw = complete(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("generation failed: %s", exc)
            continue
        messages, problems = _check(_parse(raw), specs, names)
        if not best[0] or len(problems) < len(best[1]):
            best = (messages, problems)
        if not problems:
            break
        prompt = base + "\n\n" + REPAIR.format(problems="\n".join(problems))
    messages, problems = best
    present = [m["plant"] for m in messages if m.get("plant")]
    return {
        **conversation,
        "messages": messages,
        "planted": present,
        "dropped": [pid for pid in plants if pid not in present],
    }


def write_all(world: World, conversations: list[dict], *, workers: int = 16,
              complete=None) -> list[dict]:
    complete = complete or _default_complete()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda c: write_one(c, world, complete), conversations))
