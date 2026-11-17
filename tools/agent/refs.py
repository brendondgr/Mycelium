"""References: ``@``-tags in messages and ``#n`` numbers in a thread.

A reference is ``kind:key`` (``paper:123``, ``project:<uuid>``, ``file:<uuid>``)
or a thread number ``#n``. Each kind is contributed by a tool through
``Tool.agent`` (``REFS``); its resolver answers for one caller and returns
``None`` both when the object does not exist and when the caller may not see
it, so a guess learns nothing. Every use re-resolves, so a reference that
stopped being visible stops working.
"""

from __future__ import annotations

import re

from django.db import transaction

from tools._framework.agentspec import RefInfo

from .registry import registry

#: Item kinds people type that all resolve through the corpus item resolver.
ALIASES = {
    "paper": "item",
    "grant": "item",
    "fellowship": "item",
    "conference": "item",
    "opportunity": "item",
    "user": "person",
}
_NUM = re.compile(r"^#(\d+)$")
#: ``#7 12th International Conference on …``: the number as a result line
#: shows it, with the title copied after it. Models pass this where ``#7``
#: belongs; it names #7 as long as it names no second number.
_NUM_WITH_TITLE = re.compile(r"^\[?#(\d+)\]?(?:[\s:,.)\]—–-]+[^#]*)?$")
_TAG = re.compile(r"^@?([a-z_]+):(.+)$")
#: Kept in the system prompt; older ones remain usable by number.
PROMPT_REFS = 40


def canonical_kind(kind: str) -> str:
    return ALIASES.get(kind, kind)


def thread_refs(thread) -> list[dict]:
    return list((thread.settings or {}).get("refs", []))


def lookup(thread, n: int) -> dict | None:
    for entry in thread_refs(thread):
        if entry["n"] == n:
            return entry
    return None


def number(thread, info: RefInfo) -> int:
    """The thread's number for ``info``, assigning the next one if new."""
    from .models import AgentThread

    with transaction.atomic():
        row = AgentThread.objects.select_for_update().get(pk=thread.pk)
        data = dict(row.settings or {})
        entries = list(data.get("refs", []))
        for entry in entries:
            if entry["ref"] == info.ref:
                thread.settings = data
                return entry["n"]
        n = (max((e["n"] for e in entries), default=0)) + 1
        entries.append(
            {
                "n": n,
                "ref": info.ref,
                "kind": info.kind,
                "key": info.key,
                "title": info.title[:200],
                "output": info.output,
            }
        )
        data["refs"] = entries
        row.settings = data
        row.save(update_fields=["settings", "updated_at"])
        thread.settings = data
        return n


def split(token: str) -> tuple[str, str] | None:
    """``("paper", "123")`` from ``paper:123`` or ``@paper:123``."""
    match = _TAG.match(token.strip())
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def resolve(caller, token: str, *, expect_kind: str | None = None) -> RefInfo | None:
    """Resolve ``#n``, ``kind:key`` or (with ``expect_kind``) a bare key."""
    token = (token or "").strip()
    kind = key = None
    num = _NUM.match(token) or _NUM_WITH_TITLE.match(token)
    if num:
        thread = caller.thread
        entry = lookup(thread, int(num.group(1))) if thread is not None else None
        if entry is None:
            return None
        kind, key = entry["kind"], entry["key"]
    else:
        parts = split(token)
        if parts:
            kind, key = parts
        elif expect_kind:
            kind, key = expect_kind, token
        else:
            return None
    kind = canonical_kind(kind)
    if expect_kind and canonical_kind(expect_kind) != kind:
        return None
    ref_kind = registry().refs.get(kind)
    if ref_kind is None:
        return None
    from tools._framework.host import resolve_ref

    try:
        info = resolve_ref(ref_kind.resolve)(caller, key)
    except Exception:  # a malformed key is just "not something you can open"
        info = None
    if info is None and not num:
        info = by_name(caller, kind, key)
    return info


def _plain(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", " ", str(text).casefold()).strip()


def by_name(caller, kind: str, name: str) -> RefInfo | None:
    """The one visible object of ``kind`` whose title is ``name`` (Q-069,
    Q-075): a model often passes a project's name, or a slug of it, where a
    reference belongs. Case, spaces and punctuation are ignored; two or more
    matches resolve nothing, so a name never picks between objects."""
    from tools._framework.host import resolve_ref

    ref_kind = registry().refs.get(kind)
    wanted = _plain(name)
    if ref_kind is None or not ref_kind.search or not wanted or kind == "item":
        return None
    try:
        found = resolve_ref(ref_kind.search)(caller, wanted, 20)
        if not found and " " in wanted:  # a slug: search its first word
            found = resolve_ref(ref_kind.search)(caller, wanted.split()[0], 50)
    except Exception:  # a failing search is just "not found"
        return None
    exact = {f.key: f for f in found if _plain(f.title) == wanted}
    return next(iter(exact.values())) if len(exact) == 1 else None


def search(caller, q: str, *, kinds=None, limit: int = 10) -> list[RefInfo]:
    """Candidates for the web ``@`` picker, each already visible to the caller."""
    from tools._framework.host import resolve_ref

    out: list[RefInfo] = []
    for kind, ref_kind in registry().refs.items():
        if kinds and kind not in kinds:
            continue
        if not ref_kind.search:
            continue
        try:
            out.extend(resolve_ref(ref_kind.search)(caller, q, limit))
        except Exception:  # one kind's search failing must not empty the picker
            continue
    return out[:limit]


def parse_anchor(value) -> dict | None:
    """``{"kind", "key"}`` from ``{"kind": .., "key": ..}`` or ``"kind:key"``,
    with the kind made canonical; ``None`` when it is not a registered kind."""
    if isinstance(value, dict):
        kind, key = str(value.get("kind") or ""), str(value.get("key") or "")
    else:
        parts = split(str(value or ""))
        if parts is None:
            return None
        kind, key = parts
    kind, key = canonical_kind(kind.strip()), key.strip()
    if not key or kind not in registry().refs:
        return None
    return {"kind": kind, "key": key}


def anchor_of(thread) -> dict | None:
    """What the thread is about (S2), set when it was created; or ``None``."""
    return (thread.settings or {}).get("anchor") or None


def resolve_anchor(caller, thread) -> tuple[int, RefInfo] | None:
    """The anchor, resolved for this caller and audience, with its thread
    number (``#1`` for a thread created with it). ``None`` when there is no
    anchor or this caller may not see it here: the turn runs without it."""
    from tools._framework.agentspec import width_rank

    anchor = anchor_of(thread)
    if not anchor:
        return None
    info = resolve(caller, f"{anchor['kind']}:{anchor['key']}")
    if info is None or width_rank(info.output) < width_rank(caller.audience.width):
        return None
    return number(thread, info), info


def visible_here(caller, ref: str) -> bool:
    """Whether ``kind:key`` resolves for this caller and fits the audience."""
    from tools._framework.agentspec import width_rank

    from .permissions import within_audience

    info = resolve(caller, ref)
    return (
        info is not None
        and width_rank(info.output) >= width_rank(caller.audience.width)
        and within_audience(info, caller.audience)
    )


def card(n: int, info: RefInfo) -> str:
    """The short card the model sees for a tagged or surfaced object."""
    lines = [f"#{n} {info.kind}: {info.title}"]
    if info.card:
        lines.append(f"   {info.card}")
    if info.read_with:
        lines.append(f"   read more: {info.read_with.replace('{ref}', f'#{n}')}")
    return "\n".join(lines)
