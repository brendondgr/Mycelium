"""The operator's CLI surface (``manage.py agent chat``). Never refused, but
every call is marked ``surface=cli`` and audited."""

from __future__ import annotations

from ..caller import Audience, Caller, Scope, for_thread


def caller(user, thread=None, *, scope: Scope | None = None) -> Caller:
    from apps.accounts.services import record_audit_event

    record_audit_event(
        actor=user,
        action="agent.cli",
        target_type="agent_thread",
        target_id=str(getattr(thread, "pk", "") or ""),
        metadata={},
    )
    if thread is not None:
        return for_thread(thread, surface="cli", audience=Audience("person"))
    return Caller(
        user=user, surface="cli", scope=scope or Scope(), audience=Audience("person")
    )
