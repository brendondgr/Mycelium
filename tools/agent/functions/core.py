"""The ``agent`` group: functions about the conversation itself. Loaded in
every thread. ``ask_user`` is handled by the loop (it pauses the turn)."""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common


def ask_user(caller, **_):
    raise FunctionError(
        "handled_by_loop", "ask_user pauses the turn; it has no handler."
    )


def update_todos(caller, items):
    from .. import store
    from ..models import AgentThread

    thread = common.need_thread(caller)
    clean = [
        {"text": common.clip(i.get("text", ""), 200), "done": bool(i.get("done"))}
        for i in (items or [])
        if isinstance(i, dict) and i.get("text")
    ][:20]
    data = dict(thread.settings or {})
    data["todos"] = clean
    AgentThread.objects.filter(pk=thread.pk).update(settings=data)
    store.append(thread, "todos", {"items": clean})
    left = sum(1 for i in clean if not i["done"])
    return Result(content=f"Plan saved: {len(clean)} steps, {left} left.")


def find_functions(caller, query):
    from .. import permissions

    words = {w for w in str(query).lower().split() if len(w) > 2}
    thread = common.need_thread(caller)
    loaded = set((thread.settings or {}).get("loaded", []))
    hits = []
    for fn in permissions.allowed_functions(caller, mode=thread.mode):
        text = f"{fn.name} {fn.group} {fn.summary} {fn.description}".lower()
        score = sum(1 for w in words if w in text)
        if score:
            hits.append((score, fn))
    hits.sort(key=lambda pair: (-pair[0], pair[1].name))
    if not hits:
        return Result(
            content="No function matches. The deferred index in your "
            "instructions lists every group."
        )
    lines = [
        f"- {fn.name}{' (loaded)' if fn.name in loaded or fn.core else ''}: "
        f"{fn.summary}"
        for _, fn in hits[:12]
    ]
    return Result(
        content="Matching functions (load_functions(names=[...]) to use them):\n"
        + "\n".join(lines)
    )


def load_functions(caller, names):
    from .. import permissions
    from ..models import AgentThread

    thread = common.need_thread(caller)
    allowed = {
        fn.name: fn for fn in permissions.allowed_functions(caller, mode=thread.mode)
    }
    data = dict(thread.settings or {})
    loaded = list(data.get("loaded", []))
    added, refused = [], []
    # A function comes with the rest of its group (projects_*, feeds_*, …):
    # EXP-2026-11-013 saw one answer spend 16 of its 25 steps loading one
    # function at a time. Groups are small (at most six functions).
    wanted = []
    for name in names or []:
        if name not in allowed:
            refused.append(name)
            continue
        group = allowed[name].group
        wanted += [name] + [
            n for n, fn in allowed.items() if group and fn.group == group and n != name
        ]
    for name in dict.fromkeys(wanted):
        if name not in loaded:
            loaded.append(name)
        added.append(name)
    data["loaded"] = loaded
    AgentThread.objects.filter(pk=thread.pk).update(settings=data)
    thread.settings = data
    out = []
    if added:
        out.append(
            "Loaded: " + ", ".join(added) + ". They are available from your next step."
        )
    if refused:
        out.append("Not available here: " + ", ".join(refused) + ".")
    return Result(content=" ".join(out) or "Nothing to load.")


def read_skill(caller, name):
    from .. import skills

    text = skills.read(str(name))
    if text is None:
        names = ", ".join(s.name for s in skills.available()) or "none"
        raise FunctionError(
            "no_skill", f"There is no skill {name!r}.", f"Skills: {names}."
        )
    return Result(content=text)


def read_result(caller, call_id, offset=0):
    from .. import rebuild
    from ..models import AgentEvent

    thread = common.need_thread(caller)
    event = AgentEvent.objects.filter(
        thread=thread, type="tool_result", payload__call_id=str(call_id)
    ).first()
    if event is None:
        raise FunctionError(
            "no_result",
            f"No result {call_id} in this conversation.",
            "Use a call_id from this conversation.",
        )
    content = event.payload.get("content", "")
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    return Result(
        content=rebuild.capped(content, str(call_id), offset=offset),
        untrusted=bool(event.payload.get("untrusted")),
    )


def thread_search(caller, query, limit=5):
    from ..models import AgentThread

    thread = common.need_thread(caller)
    words = [w for w in str(query).lower().split() if len(w) > 2]
    rows = (
        AgentThread.objects.filter(user=caller.user)
        .exclude(pk=thread.pk)
        .select_related("digest")
        .order_by("-last_activity_at")[:200]
    )
    scored = []
    for t in rows:
        digest = getattr(t, "digest", None)
        hay = f"{t.title} {t.purpose} {digest.text if digest else ''}".lower()
        score = sum(hay.count(w) for w in words)
        if score:
            scored.append((score, t))
    scored.sort(key=lambda p: -p[0])
    if not scored:
        return Result(content="No earlier conversation matches.")
    lines = [
        f"- {t.last_activity_at:%Y-%m-%d} “{t.title or 'untitled'}”"
        + (f": {t.purpose}" if t.purpose else "")
        for _, t in scored[: max(1, min(int(limit or 5), 10))]
    ]
    return Result(content="Earlier conversations:\n" + "\n".join(lines))
