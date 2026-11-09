"""Files attached to a chat message. Stored by the ``files`` tool when it is
loaded (reached through ``services.get``, never imported), in the thread's
scope, then treated as ``file:`` mentions. Short files go into the message
whole; longer ones as a card saying how to read them."""

from __future__ import annotations

from tools._framework import services

from . import compaction, refs
from .rebuild import CHARS_PER_TOKEN

#: A file under this share of the context window goes into the message whole.
INLINE_SHARE = 0.25
#: How long the turn waits for a fresh upload's text.
WAIT_SECONDS = 30


def attach(caller, thread, attachments) -> tuple[list[str], list[dict]]:
    from .service import ServiceError

    files = services.get("files")
    if files is None:
        raise ServiceError(
            "files_off", "File storage isn't enabled on this instance.", status=400
        )
    cards, inline = [], []
    owner_kind, owner_id = _owner(thread)
    for item in attachments:
        if isinstance(item, str):
            file_id = item
        else:
            stored = files.store_upload(
                caller.user,
                item,
                owner_kind=owner_kind,
                owner_id=owner_id,
                origin="chat",
                thread_id=str(thread.pk),
            )
            file_id = str(stored.pk)
        info = refs.resolve(caller, f"file:{file_id}")
        if info is None:
            raise ServiceError(
                "mention_not_visible",
                f"file:{file_id} is not something you can open.",
                status=404,
            )
        n = refs.number(thread, info)
        text = files.wait_for_text(file_id, timeout=WAIT_SECONDS)
        budget = int(compaction.window() * INLINE_SHARE * CHARS_PER_TOKEN)
        if text is None:
            cards.append(
                refs.card(n, info) + "\n   (being read; try files_read in a moment)"
            )
        elif len(text) <= budget:
            numbered = "\n".join(
                f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1)
            )
            cards.append(refs.card(n, info))
            inline.append({"source": f"#{n}", "text": numbered})
        else:
            cards.append(refs.card(n, info))
    return cards, inline


def _owner(thread) -> tuple[str, str]:
    if thread.scope_kind == "project":
        return "project", str(thread.scope_project_id)
    if thread.scope_kind == "lab":
        return "lab", str(thread.scope_lab_id)
    if thread.scope_kind == "department":
        return "department", str(thread.scope_department_id)
    return "user", str(thread.user_id)
