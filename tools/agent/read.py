"""The agent read door: what other tools and the platform may read about the
agent. Return plain values, not querysets."""

from __future__ import annotations


def thread_count(user) -> int:
    from .models import AgentThread

    return AgentThread.objects.filter(user=user).count()


def learning_enabled_for(user) -> bool:
    """Whether Mylo learns from this person's chats (on unless they opted out)."""
    from .memory_after import learning_on_for

    return learning_on_for(user)
