"""Fake paper text for the synthetic world, written by the local model.

Each planted paper — a field, a problem, a method under one of its names, a
setting — becomes a title and an abstract. The model is told the method's name
and told not to name any other method, and the result is checked: an abstract
that never says its method, or says a different planted method's name, is
asked for again once and then kept with a flag, so the score can leave it out
rather than blame the extractor for the generator's slip.

Cached to disk by paper key and spec, so a re-run costs no calls and every run
of the same world reads the same text.
"""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import world as world_mod

logger = logging.getLogger(__name__)

SYSTEM = (
    "You write realistic but entirely fictional research paper titles and "
    "abstracts for a software test. Reply with one JSON object and nothing else."
)

PROMPT = """Write a fictional paper in {field_name}.

It addresses: {problem}
Its method, which you must name exactly as "{method_name}" at least once: {method_name}
Its data or setting: {setting}
Year: {year}

Rules:
- 120 to 180 words of abstract, in the style of a real abstract.
- Name the method only as "{method_name}". Do not name any other analysis
  method, model, or algorithm by name.
- Mention the data or setting.
- No real author names, no URLs, no citations.

Reply as {{"title": "...", "abstract": "..."}}"""


def _spec_key(paper: world_mod.Paper) -> str:
    raw = "|".join(
        (paper.key, paper.field, paper.problem, paper.method_name, paper.setting)
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _other_names(paper: world_mod.Paper) -> list[str]:
    own = world_mod.method(paper.method)
    return [
        name.lower()
        for m in world_mod.METHODS
        if m.key != own.key
        for name in m.names
        # A name that contains the paper's own ("Kalman filter" inside
        # "extended Kalman filter") is not a slip.
        if not any(
            name.lower() in n.lower() or n.lower() in name.lower() for n in own.names
        )
    ]


def check(paper: world_mod.Paper, text: str) -> list[str]:
    """What is wrong with a generated abstract, if anything."""
    lowered = text.lower()
    problems = []
    if paper.method_name.lower() not in lowered:
        problems.append("does not name its method")
    slips = [name for name in _other_names(paper) if name in lowered]
    if slips:
        problems.append(f"names other methods: {slips}")
    return problems


def _ask(complete, paper: world_mod.Paper) -> dict:
    field_name = dict((k, n) for k, _, n in world_mod.FIELDS)[paper.field]
    prompt = PROMPT.format(
        field_name=field_name,
        problem=paper.problem,
        method_name=paper.method_name,
        setting=paper.setting,
        year=paper.year,
    )
    last: dict = {}
    for _ in range(2):
        try:
            raw = complete(SYSTEM, prompt) or ""
        except Exception as exc:  # noqa: BLE001 - recorded, not fatal
            last = {"error": str(exc)}
            continue
        start, end = raw.find("{"), raw.rfind("}")
        try:
            data = json.loads(raw[start : end + 1])
        except ValueError:
            last = {"error": "not JSON"}
            continue
        title = " ".join(str(data.get("title") or "").split())
        abstract = " ".join(str(data.get("abstract") or "").split())
        problems = check(paper, f"{title} {abstract}")
        last = {"title": title, "abstract": abstract, "problems": problems}
        if title and abstract and not problems:
            break
    return last


def _default_complete():
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="sandbox_corpus")

    def complete(system: str, user: str) -> str | None:
        return client.complete(
            [LLMMessage("system", system), LLMMessage("user", user)]
        ).content

    return complete


def generate(
    world: world_mod.World,
    path: Path,
    *,
    complete=None,
    workers: int = 12,
) -> dict[str, dict]:
    """Title and abstract for every paper, from the cache where possible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
    todo = [
        paper
        for paper in world.papers
        if cache.get(paper.key, {}).get("spec") != _spec_key(paper)
        or not cache[paper.key].get("abstract")
    ]
    if todo:
        ask = complete or _default_complete()
        logger.info("writing %d abstracts (%d cached)", len(todo), len(cache))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for paper, result in zip(
                todo, pool.map(lambda p: _ask(ask, p), todo), strict=True
            ):
                cache[paper.key] = {**result, "spec": _spec_key(paper)}
        path.write_text(json.dumps(cache, indent=1, sort_keys=True))
    return {paper.key: cache[paper.key] for paper in world.papers}
