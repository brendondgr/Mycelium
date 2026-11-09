"""The activity view: what a surface may show of a turn (S-9).

A person sees what Mylo is doing ("Reading “Cell segmentation at scale”",
"Looking at your projects"), never its reasoning, a function's arguments
beyond its label, or a function's result. This module is the only place that
decides that, so web and Discord render the same thing and neither can leak
more by accident. ``stream.follow(view="activity")`` and the HTTP routes use
it; the raw view is for the CLI, export, and staff.

Message shapes (the envelope is the stream's: ``id`` and ``ts`` on anything
derived from a stored event, so ``Last-Event-ID`` keeps working):

* ``thinking`` events and ``delta{kind:"thinking"}`` →
  ``{"type": "activity", "payload": {"state": "thinking"}}`` (once per run of
  thinking, no text);
* ``tool_call`` → ``{"type": "activity", "payload": {"state": "running",
  "label", "call_id", "name"}}``; its ``tool_result`` →
  ``{"state": "ok" | "failed", "label", "call_id", "name"}``;
* ``assistant`` keeps only ``text``, ``final``, ``partial``, ``removed`` and
  ``model`` (an intermediate step with no text is dropped);
* ``user`` loses inlined file text; ``note`` meant for the model is dropped;
* ``usage``, ``recall``, ``verdict``, ``compact`` and transient ``progress``
  are dropped; everything else passes through.
"""

from __future__ import annotations

import re
import string

VIEWS = ("activity", "raw")

#: Stored or transient types a person never sees in the activity view.
DROPPED = frozenset({"usage", "recall", "verdict", "compact", "progress"})
#: Assistant payload keys a surface may show.
ASSISTANT_KEYS = ("text", "final", "partial", "removed", "model")
#: Shown for an object argument whose title is not known in the thread.
GENERIC = {
    "item": "an item",
    "paper": "a paper",
    "project": "a project",
    "lab": "a lab",
    "department": "a department",
    "person": "someone",
    "file": "a file",
    "doc": "a paper",
    "thread": "an earlier result",
}
FALLBACK_LABEL = "Working"
_NUM = re.compile(r"^#(\d+)$")
_SLOT_CHARS = 80


def _short(value, limit: int = _SLOT_CHARS) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _ref_title(value: str, kind: str, refs: list[dict]) -> str:
    value = str(value or "").strip()
    num = _NUM.match(value)
    for entry in refs:
        if (num and entry.get("n") == int(num.group(1))) or entry.get("ref") == value:
            return f"“{_short(entry.get('title') or '')}”"
    return GENERIC.get(kind, "something")


def label(name: str, args, refs: list[dict] | None = None) -> str:
    """The display label for one call of ``name`` with ``args``."""
    from .registry import registry

    fn = registry().get(name or "")
    if fn is None or not fn.activity:
        return FALLBACK_LABEL
    args = args if isinstance(args, dict) else {}
    ref_args = fn.ref_args()
    values = {}
    for _, slot, _, _ in string.Formatter().parse(fn.activity):
        if not slot:
            continue
        raw = args.get(slot)
        if slot in ref_args:
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            values[slot] = _ref_title(raw, ref_args[slot], refs or [])
        elif raw in (None, "", [], {}):
            values[slot] = "…"
        else:
            values[slot] = _short(raw)
    try:
        return fn.activity.format(**values)
    except (KeyError, IndexError, ValueError):
        return FALLBACK_LABEL


class Projector:
    """Turns raw stream messages into their activity form, one thread at a
    time. Stateful only to remember each call's label for its result and to
    collapse a run of thinking deltas into one message."""

    def __init__(self, thread=None) -> None:
        self.thread = thread
        self.labels: dict[str, tuple[str, str]] = {}
        self.thinking = False

    def _refs(self) -> list[dict]:
        if self.thread is None:
            return []
        from .models import AgentThread

        data = (
            AgentThread.objects.filter(pk=self.thread.pk)
            .values_list("settings", flat=True)
            .first()
        )
        return list((data or {}).get("refs", []))

    def project(self, message: dict) -> dict | None:
        kind = message.get("type")
        if kind == "heartbeat":
            return message
        if kind == "thinking" or (
            kind == "delta" and message.get("kind") == "thinking"
        ):
            if self.thinking:
                return None
            self.thinking = True
            return _activity(message, {"state": "thinking"})
        if kind != "delta":
            self.thinking = False
        if kind in DROPPED:
            return None
        payload = message.get("payload") or {}
        if kind == "tool_call":
            call_id = payload.get("call_id", "")
            name = payload.get("name", "")
            text = label(name, payload.get("args"), self._refs())
            self.labels[call_id] = (name, text)
            return _activity(
                message,
                {"state": "running", "label": text, "call_id": call_id, "name": name},
            )
        if kind == "tool_result":
            call_id = payload.get("call_id", "")
            name, text = self.labels.get(call_id, (payload.get("name", ""), None))
            if text is None:
                text = label(name, None)
            ok = payload.get("status", "ok") == "ok"
            return _activity(
                message,
                {
                    "state": "ok" if ok else "failed",
                    "label": text,
                    "call_id": call_id,
                    "name": name,
                },
            )
        if kind == "assistant":
            kept = {k: payload[k] for k in ASSISTANT_KEYS if k in payload}
            if not (kept.get("text") or "").strip() and not kept.get("final"):
                return None
            return {**message, "payload": kept}
        if kind == "user" and "inline" in payload:
            return {
                **message,
                "payload": {k: v for k, v in payload.items() if k != "inline"},
            }
        if kind == "note" and payload.get("to_model"):
            return None
        return message


def _activity(message: dict, data: dict) -> dict:
    out = {"type": "activity", "payload": data}
    for key in ("id", "thread", "ts"):
        if message.get(key) is not None:
            out[key] = message[key]
    return out


def project(message: dict, *, thread=None) -> dict | None:
    """One message in its activity form, or ``None`` when a surface must not
    show it. Stateless: a ``tool_result`` gets its function's label without
    argument values. Streams use :class:`Projector`."""
    return Projector(thread).project(message)


def check_view(view: str) -> str:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; one of {VIEWS}")
    return view
