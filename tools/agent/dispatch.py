"""Run one function call: decide, then the handler, then record.

``#n`` references in arguments are passed to handlers as the canonical
``kind:key`` they stand for, after the gate has cleared each one. Every
object a handler surfaces is numbered in the thread. A read of another
person's data also writes the platform ``AuditEvent``.
"""

from __future__ import annotations

import logging

from tools._framework.agentspec import FunctionError, Result
from tools._framework.host import resolve_ref

from . import permissions, refs
from .registry import registry

logger = logging.getLogger(__name__)


def _canonical_args(caller, fn, args: dict) -> dict:
    out = dict(args)
    for key, kind in fn.ref_args().items():
        value = out.get(key)
        if value in (None, "", []) or kind == "thread":
            continue
        values = value if isinstance(value, list) else [value]
        resolved = []
        for token in values:
            info = refs.resolve(caller, str(token), expect_kind=kind)
            resolved.append(info.ref if info else str(token))
        out[key] = resolved if isinstance(value, list) else resolved[0]
    return out


#: Error codes that mean the call itself was put together wrongly — an
#: argument the function does not take, one it needs left out, a value in the
#: wrong form — rather than that the function ran and failed. The loop counts
#: these apart from real failures (Q-075). ``need_*`` is a handler asking for an
#: argument that was left out (``need_project``, ``need_lab``).
MALFORMED_CODES = ("bad_arguments",)
MALFORMED_PREFIX = "need_"


def malformed(result: dict) -> bool:
    """True when a call's result says its arguments were malformed."""
    code = str((result.get("error") or {}).get("code") or "")
    return code in MALFORMED_CODES or code.startswith(MALFORMED_PREFIX)


def accepts(fn) -> str:
    """``projects_get accepts: project.`` — what a malformed call is told."""
    schema = fn.parameters or {}
    props = list(schema.get("properties") or {})
    if not props:
        return f"{fn.name} takes no arguments."
    required = set(schema.get("required") or [])
    names = [f"{k} (required)" if k in required else k for k in props]
    return f"{fn.name} accepts: {', '.join(names)}."


def accepts_by_name(name: str) -> str:
    fn = registry().get(name)
    return accepts(fn) if fn is not None else ""


def _shape_error(fn, args) -> str:
    """Why these arguments do not fit the function's schema, or ``""``."""
    if not isinstance(args, dict):
        return "The arguments must be a JSON object."
    schema = fn.parameters or {}
    props = schema.get("properties") or {}
    unknown = [k for k in args if k not in props]
    missing = [
        k for k in schema.get("required") or [] if k not in args or args[k] is None
    ]
    parts = []
    if unknown:
        parts.append(f"{fn.name} does not take: {', '.join(map(str, unknown))}.")
    if missing:
        parts.append(f"{fn.name} needs: {', '.join(missing)}.")
    return " ".join(parts)


def run(
    caller,
    thread,
    *,
    name: str,
    args: dict | None,
    call_id: str,
    arg_error: str = "",
    mode: str = "read",
) -> dict:
    """Return the ``tool_result`` payload for one call."""
    base = {"call_id": call_id, "name": name}
    fn = registry().get(name)
    if fn is None:
        return {
            **base,
            "status": "error",
            "error": {
                "code": "unknown_function",
                "detail": f"There is no function {name}.",
                "fix": "Use find_functions to see what exists.",
            },
        }
    if args is None:
        return {
            **base,
            "status": "error",
            "error": {
                "code": "bad_arguments",
                "detail": arg_error or "Arguments were not valid JSON.",
                "fix": "Send the arguments as a JSON object. " + accepts(fn),
            },
        }
    decision = permissions.decide(caller, fn, args, mode=mode)
    if decision.verdict != "allow":
        return {
            **base,
            "status": "denied",
            "decision": decision.as_dict(),
            "error": {
                "code": decision.code,
                "detail": decision.detail,
                "fix": decision.fix,
            },
        }
    # Checked after the gate, so a function the caller may not use never
    # describes itself; before the handler, so the model is told which
    # arguments exist instead of a Python error.
    shape = _shape_error(fn, args)
    if shape:
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": {"code": "bad_arguments", "detail": shape, "fix": accepts(fn)},
        }
    try:
        handler = resolve_ref(fn.handler)
        result = handler(caller, **_canonical_args(caller, fn, args))
    except FunctionError as exc:
        error = exc.as_dict()
        if malformed({"error": error}):
            error["fix"] = f"{error.get('fix') or ''} {accepts(fn)}".strip()
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": error,
        }
    except TypeError as exc:
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": {
                "code": "bad_arguments",
                "detail": str(exc),
                "fix": accepts(fn),
            },
        }
    except Exception:
        logger.exception("agent function %s failed", name)
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": {
                "code": "failed",
                "detail": f"{name} failed inside Mycelium.",
                "fix": "Try another way, or tell the person it did not work.",
            },
        }
    if not isinstance(result, Result):
        result = Result(content=str(result))
    numbers = []
    content = result.content
    for info in result.refs:
        n = refs.number(thread, info)
        numbers.append(n)
        content = content.replace(f"{{ref:{info.ref}}}", f"#{n}")
    if fn.audit:
        _audit(caller, fn, args)
    source = ",".join(f"#{n}" for n in numbers[:5]) or name
    return {
        **base,
        "status": "ok",
        "content": content,
        "refs": numbers,
        "untrusted": bool(result.untrusted),
        "source": source,
        "decision": decision.as_dict(),
        "chars": len(content),
    }


def _audit(caller, fn, args) -> None:
    from apps.accounts.services import record_audit_event

    record_audit_event(
        actor=caller.user,
        action=f"agent.{fn.name}",
        target_type="agent_call",
        target_id=str(caller.thread_id or ""),
        metadata={
            "args": args,
            "surface": caller.surface,
            **(
                {"guest_discord_user_id": caller.guest.discord_user_id}
                if caller.is_guest
                else {}
            ),
        },
    )
