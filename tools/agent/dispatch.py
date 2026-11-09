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
                "fix": "Send the arguments as a JSON object matching the schema.",
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
    try:
        handler = resolve_ref(fn.handler)
        result = handler(caller, **_canonical_args(caller, fn, args))
    except FunctionError as exc:
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": exc.as_dict(),
        }
    except TypeError as exc:
        return {
            **base,
            "status": "error",
            "decision": decision.as_dict(),
            "error": {
                "code": "bad_arguments",
                "detail": str(exc),
                "fix": "Check the parameter names against the schema.",
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
