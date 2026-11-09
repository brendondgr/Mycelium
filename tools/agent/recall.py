"""Recall, per message: what Mylo remembers that bears on what was just said.

Searched, for the person and only what they may see:

* their earlier threads (``AgentThreadDigest``: purpose, title, their own
  words — never the agent's);
* active observations about them (ambient), marked as not confirmed;
* developments in effect for the projects the message names.

Three ranked lists fused by reciprocal rank (k=60), as GAIFA's memory search:
names found in the message (project names and aliases, lab names, concept
aliases; whole words, longest first), keyword overlap, and vector similarity
over thread digests (cosine ≥ 0.55, given up after 2.5 s). At most 8 facts and
800 characters; facts already in the profile block are dropped.

The result is stored as a ``recall`` event tied to the message, so the rebuilt
message is byte-identical every time it is sent. In a reply others will read
(a lab channel), nothing personal is recalled.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

from tools._framework.agentspec import width_rank

from . import store

RRF_K = 60
MAX_FACTS = 8
MAX_CHARS = 800
MIN_COSINE = 0.55
VECTOR_SECONDS = 2.5
_WORD = re.compile(r"[a-z0-9][a-z0-9\-]+")
_STOP = set(
    "the a an and or of to in on for with is are was were be been it this that what "
    "which who how why when where do does did can could should would i we you my our "
    "your me us about from by at as any some more most just than then there "
    "their".split()
)


@dataclass
class Fact:
    key: str
    text: str
    haystack: str
    vector: list | None = None
    personal: bool = True


def _words(text: str) -> set[str]:
    return {
        w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 2
    }


def _names_in(text: str, names: dict[str, str]) -> list[str]:
    """Keys of ``names`` (name → key) found as whole words, longest first."""
    low = f" {(text or '').lower()} "
    found = []
    for name in sorted(names, key=len, reverse=True):
        if len(name) < 3:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", low):
            found.append(names[name])
            low = low.replace(name, " ")
    return found


def _candidates(caller, thread) -> tuple[list[Fact], dict[str, list[str]]]:
    """All facts recall may use, and name → fact keys for the name channel."""
    from apps.ambient.read import developments_in_effect, observations_for
    from apps.research.models import Project

    from .models import AgentThreadDigest

    user = caller.user
    personal_ok = width_rank(caller.audience.width) <= width_rank("person")
    facts: list[Fact] = []
    names: dict[str, list[str]] = {}

    def add_name(name: str, key: str) -> None:
        name = " ".join(str(name).lower().split())
        if name:
            names.setdefault(name, []).append(key)

    if personal_ok:
        for d in (
            AgentThreadDigest.objects.filter(user=user)
            .exclude(thread_id=thread.pk)
            .select_related("thread")[:200]
        ):
            t = d.thread
            label = t.purpose or t.title or "an earlier conversation"
            facts.append(
                Fact(
                    key=f"thread:{t.pk}",
                    text=(
                        f"Earlier conversation ({t.last_activity_at:%Y-%m-%d}): {label}"
                    ),
                    haystack=f"{t.title} {t.purpose} {d.text}",
                    vector=list(d.embedding) if d.embedding is not None else None,
                )
            )
        for o in observations_for(user).select_related("project")[:100]:
            when = f"{o.observed_at:%Y-%m-%d}" if o.observed_at else ""
            facts.append(
                Fact(
                    key=f"obs:{o.pk}",
                    text=f"Noticed {when}, not confirmed: {o.text}",
                    haystack=" ".join(
                        [o.text, o.topic, o.project.name if o.project_id else ""]
                    ),
                )
            )
            if o.concept_id:
                for alias in o.concept.aliases.all()[:5]:
                    add_name(alias.text, f"obs:{o.pk}")
            if o.topic:
                add_name(o.topic, f"obs:{o.pk}")
    projects = Project.objects.visible_to(user).filter(is_archived=False)
    for p in projects[:100]:
        for name in [p.name, *(p.aliases or [])]:
            add_name(name, f"project:{p.pk}")
        for d in developments_in_effect(p, reader=user if personal_ok else None)[:10]:
            key = f"dev:{d.pk}"
            facts.append(
                Fact(
                    key=key,
                    text=f"{p.name}: {d.change} {d.topic} ({d.status})",
                    haystack=f"{p.name} {d.topic} {d.text}",
                    personal=getattr(d, "visibility", "lab") == "personal",
                )
            )
            add_name(p.name, key)
            for alias in p.aliases or []:
                add_name(alias, key)
    if not personal_ok:
        facts = [f for f in facts if not f.personal]
    return facts, names


def _vector_rank(text: str, facts: list[Fact]) -> list[str]:
    with_vec = [f for f in facts if f.vector]
    if not with_vec:
        return []

    def embed():
        from tools.retrieval.read import embed_query

        return embed_query(text)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        query = pool.submit(embed).result(timeout=VECTOR_SECONDS)
    except (FutureTimeout, Exception):
        return []
    finally:
        pool.shutdown(wait=False)
    if not query:
        return []
    from tools.recommendation.read import cosine

    scored = []
    for f in with_vec:
        try:
            score = cosine(query, f.vector)
        except Exception:
            continue
        if score >= MIN_COSINE:
            scored.append((score, f.key))
    return [k for _, k in sorted(scored, reverse=True)]


def search(caller, thread, text: str, *, profile_text: str = "") -> list[str]:
    facts, names = _candidates(caller, thread)
    if not facts:
        return []
    by_key = {f.key: f for f in facts}
    # 1. names
    name_hits = [k for n in _names_in(text, {n: n for n in names}) for k in names[n]]
    direct = [k for k in dict.fromkeys(name_hits) if k in by_key]
    # a named project brings its own facts, below direct hits
    project_keys = [k for k in dict.fromkeys(name_hits) if k.startswith("project:")]
    related = []
    for pk in project_keys:
        pid = pk.split(":", 1)[1]
        related += [
            f.key for f in facts if f.key.startswith("dev:") and pid in f.haystack
        ]
    name_rank = direct + [k for k in related if k not in direct]
    # 2. keywords
    q = _words(text)
    kw = sorted(
        (
            (len(q & _words(f.haystack)) / (1 + len(_words(f.haystack)) ** 0.5), f.key)
            for f in facts
        ),
        reverse=True,
    )
    kw_rank = [k for score, k in kw if score > 0]
    # 3. vectors
    vec_rank = _vector_rank(text, facts)
    scores: dict[str, float] = {}
    for ranking in (name_rank, kw_rank, vec_rank):
        for i, key in enumerate(ranking):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + i + 1)
    out, used = [], 0
    for key in sorted(scores, key=lambda k: -scores[k]):
        fact = by_key[key].text
        if profile_text and fact in profile_text:
            continue
        if used + len(fact) > MAX_CHARS or len(out) >= MAX_FACTS:
            break
        out.append(fact)
        used += len(fact)
    return out


def ensure(caller, thread) -> None:
    """Store a recall event for every user message that has none yet."""
    from . import memory

    if getattr(thread, "shared", False) or caller.user is None:
        # A shared place recalls nothing from anyone's other conversations.
        return
    events = store.events(thread)
    done = {e.payload.get("for_seq") for e in events if e.type == "recall"}
    pending = [e for e in events if e.type == "user" and e.seq not in done]
    if not pending:
        return
    profile = memory.profile_block(caller)
    for event in pending:
        try:
            facts = search(
                caller, thread, event.payload.get("text", ""), profile_text=profile
            )
        except Exception:  # recall helps; it never blocks a turn
            facts = []
        store.append(
            thread,
            "recall",
            {
                "for_seq": event.seq,
                "text": "\n".join(f"- {f}" for f in facts),
                "facts": len(facts),
            },
        )
