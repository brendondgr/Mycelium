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
    num = _NUM.match(token)
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
        return resolve_ref(ref_kind.resolve)(caller, key)
    except Exception:  # a malformed key is just "not something you can open"
        return None


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


def card(n: int, info: RefInfo) -> str:
    """The short card the model sees for a tagged or surfaced object."""
    lines = [f"#{n} {info.kind}: {info.title}"]
    if info.card:
        lines.append(f"   {info.card}")
    if info.read_with:
        lines.append(f"   read more: {info.read_with.replace('{ref}', f'#{n}')}")
    return "\n".join(lines)
