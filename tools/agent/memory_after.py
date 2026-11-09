"""Work after a turn ends: the thread's title and purpose, its recall digest,
and the one-time notice that Mylo learns from chats (D-3)."""

from __future__ import annotations

import json
import logging

from django.utils import timezone

from . import store

logger = logging.getLogger(__name__)

TITLE_PROMPT = (
    "Give this conversation a short title (at most 8 words) and one line on why "
    "the person is asking (their purpose, at most 25 words). Answer only with "
    'JSON: {"title": "...", "purpose": "..."}'
)
NOTICE = (
    "Mylo learns from your chats to keep your profile and recommendations "
    "current: it may notice things you say and ask you before anything changes. "
    "You can turn this off in your account settings (Mylo & you)."
)


def _user_texts(events) -> list[str]:
    return [e.payload.get("text", "") for e in events if e.type == "user"]


def title_and_purpose(thread, events, port) -> None:
    if thread.title:
        return
    texts = _user_texts(events)
    if not texts:
        return
    title, purpose = texts[0].strip().split("\n")[0][:60], ""
    try:
        reply = port(
            messages=[
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user", "content": "\n\n".join(texts)[:4000]},
            ],
            tools=None,
            tool_choice=None,
            on_delta=None,
            should_stop=None,
        )
        raw = (reply.content or "").strip().strip("`")
        raw = raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else raw
        data = json.loads(raw)
        title = str(data.get("title") or title)[:200]
        purpose = str(data.get("purpose") or "")[:300]
    except Exception:  # the fallback title is fine
        pass
    type(thread).objects.filter(pk=thread.pk).update(title=title, purpose=purpose)
    thread.title, thread.purpose = title, purpose


def update_digest(thread, events) -> None:
    from .models import AgentThreadDigest

    words = " \n".join(_user_texts(events))
    text = f"{thread.title}\n{thread.purpose}\n{words}"[-4000:]
    vector = None
    try:
        from tools.retrieval.read import embed_text

        vector = embed_text(f"{thread.purpose or thread.title}\n{words[-1500:]}")
    except Exception:
        vector = None
    AgentThreadDigest.objects.update_or_create(
        thread=thread,
        defaults={
            "user": thread.user,
            "text": text,
            "embedding": vector,
            "upto_seq": events[-1].seq if events else 0,
        },
    )


def learning_on_for(user) -> bool:
    """The instance switch and the person's own (ambient's consent row for
    Mylo chat, on unless they turned it off)."""
    from apps.ambient.read import listening_enabled

    from . import config

    return bool(config.get("learning")) and listening_enabled(user, "agent_chat")


def maybe_notice(thread) -> None:
    from .models import AgentPreference

    if not learning_on_for(thread.user):
        return
    pref, _ = AgentPreference.objects.get_or_create(user=thread.user)
    if pref.learning_notice_at:
        return
    store.append(thread, "note", {"text": NOTICE, "kind": "learning_notice"})
    pref.learning_notice_at = timezone.now()
    pref.save(update_fields=["learning_notice_at", "updated_at"])


def after_turn(caller, thread, port) -> None:
    events = store.events(thread)
    title_and_purpose(thread, events, port)
    if thread.shared:
        # No owner: no recall digest and no learning notice (plan D).
        return
    update_digest(thread, events)
    maybe_notice(thread)
