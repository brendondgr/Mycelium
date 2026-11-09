"""What delivery gives the Mylo agent: the ``announcement`` reference kind.

A question asked in an announcement's Discord thread is about that
announcement; the agent holds it as reference ``#1`` (the thread's anchor).
Written with ``tools._framework.agentspec`` only; the resolver is imported
lazily, so the agent never has to import this tool and the reverse.
"""

from __future__ import annotations

from tools._framework.agentspec import RefKind

FUNCTIONS = ()

REFS = (
    RefKind(
        "announcement",
        "tools.delivery.agent_refs:resolve_announcement",
        None,
        "An opportunity Mylo announced to a lab or department, as posted.",
    ),
)
