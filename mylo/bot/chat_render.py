"""How Mylo's chat answers look in Discord (plan D). Pure functions: no Django,
no Discord I/O, so every rule here is tested without either.

* The status line comes from the agent's activity view (S-9): what Mylo is
  doing, never what it is thinking.
* Answers are split under 2,000 characters on paragraph boundaries and never
  inside a code fence (a fence cut in two is closed and reopened).
* Nothing Mylo writes can ping anyone: ``<@…>``, ``<@&…>``, ``@everyone`` and
  ``@here`` in model output are neutralised here, and every send also carries
  ``AllowedMentions.none()`` (the cog's job).
* Citations become a short *Sources* list of masked links with embeds
  suppressed (``<url>``).
"""

from __future__ import annotations

import re
import time

LIMIT = 2000
#: Room kept for the sources list and model line on the last chunk.
SAFE = 1900
EDIT_EVERY = 1.5

THINKING = "*Mylo is thinking…*"
QUEUED = "*Waiting for my turn…*"
STARTING = "*Reading your question…*"
STOPPED = "Stopped."
LOST = "I lost track of this one. Ask again."
ANSWERED_BELOW = "Answered below."
FAILED = "I couldn't answer that just now. Ask again in a moment."

_USER = re.compile(r"<@!?(\d+)>")
_ROLE = re.compile(r"<@&(\d+)>")
_CHANNEL_PING = re.compile(r"@(everyone|here)\b", re.I)
_ZWSP = "​"


def neutralise(text: str) -> str:
    """Model output that cannot ping or pose as a mention."""
    text = _USER.sub("@someone", text or "")
    text = _ROLE.sub("@a role", text)
    return _CHANNEL_PING.sub(lambda m: "@" + _ZWSP + m.group(1), text)


def strip_mention(text: str, *, bot_id, role_ids=()) -> str:
    """The question without the ``@Mylo`` that addressed it."""
    out = re.sub(rf"<@!?{bot_id}>", " ", text or "")
    for rid in role_ids:
        out = out.replace(f"<@&{rid}>", " ")
    return " ".join(out.split()) if "\n" not in out else out.strip()


def status_line(message: dict | None) -> str:
    """One activity-view message → the status line, or ``""`` to keep the
    current one."""
    if not message:
        return ""
    kind = message.get("type")
    if kind == "queued":
        return QUEUED
    if kind != "activity":
        return ""
    payload = message.get("payload") or {}
    state = payload.get("state")
    if state == "thinking":
        return THINKING
    if state == "running":
        label = neutralise(str(payload.get("label") or "Working")).rstrip(".…")
        return f"*{label}…*"
    return ""


class Throttle:
    """At most one status edit every ``every`` seconds."""

    def __init__(self, every: float = EDIT_EVERY, clock=time.monotonic) -> None:
        self.every = every
        self.clock = clock
        self.last: float | None = None

    def ready(self) -> bool:
        now = self.clock()
        if self.last is None or now - self.last >= self.every:
            self.last = now
            return True
        return False


def _fence_state(text: str) -> str | None:
    """The opening fence (with its language) left open at the end of
    ``text``, or ``None``."""
    open_fence = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            open_fence = None if open_fence is not None else stripped
    return open_fence


def split(text: str, limit: int = SAFE) -> list[str]:
    """Chunks under ``limit``: paragraph boundaries first, then lines, then
    hard cuts. A code fence cut across chunks is closed and reopened."""
    text = (text or "").strip()
    if not text:
        return []
    # (piece, the separator that joins it to the one before)
    pieces: list[tuple[str, str]] = []
    for para in text.split("\n\n"):
        if len(para) <= limit:
            pieces.append((para, "\n\n"))
            continue
        sep = "\n\n"
        for line in para.split("\n"):
            while len(line) > limit:
                pieces.append((line[:limit], sep))
                line, sep = line[limit:], ""
            pieces.append((line, sep))
            sep = "\n"
    chunks: list[str] = []
    current = ""
    for piece, sep in pieces:
        joined = f"{current}{sep}{piece}" if current else piece
        # 8 characters kept for a fence closed at the end of the chunk
        if len(joined) + 8 <= limit:
            current = joined
            continue
        if current:
            chunks.append(current)
        current = piece
    if current:
        chunks.append(current)
    out: list[str] = []
    carry = None
    for chunk in chunks:
        if carry:
            chunk = f"{carry}\n{chunk}"
        carry = _fence_state(chunk)
        if carry:
            chunk = f"{chunk}\n```"
        out.append(chunk)
    return out


def sources_block(sources: list[dict]) -> str:
    """``**Sources**`` with masked links whose embeds are suppressed."""
    lines = []
    for s in sources or []:
        title = neutralise(str(s.get("title") or "")).replace("[", "(").replace(
            "]", ")"
        )[:120]
        url = str(s.get("url") or "")
        n = s.get("n")
        if url.startswith(("http://", "https://")):
            lines.append(f"`#{n}` [{title}](<{url}>)")
        else:
            lines.append(f"`#{n}` {title}")
    if not lines:
        return ""
    return "**Sources**\n" + "\n".join(lines)


def model_line(model: dict | None, *, first: bool) -> str:
    """Which model answered and where it runs (S-3): on every answer when it
    runs elsewhere, on a conversation's first answer when it runs here."""
    if not model:
        return ""
    label = str(model.get("label") or model.get("name") or "")
    if not label:
        return ""
    where = model.get("location") or "local"
    if where == "local":
        if not first:
            return ""
        return f"-# {neutralise(label)} · runs on this Mycelium's own computer"
    place = "in the cloud" if where == "cloud" else "on another server"
    return f"-# {neutralise(label)} · runs {place}"


def answer_chunks(
    text: str, sources: list[dict], model: dict | None, *, first: bool
) -> list[str]:
    """The whole answer as messages: text split safely, then sources and the
    model line on the last chunk (or a chunk of their own)."""
    body = split(neutralise(text)) or ["(Mylo had nothing to say.)"]
    tail = "\n".join(
        p for p in (sources_block(sources), model_line(model, first=first)) if p
    )
    if tail:
        if len(body[-1]) + len(tail) + 2 <= LIMIT:
            body[-1] = f"{body[-1]}\n\n{tail}"
        else:
            body.extend(split(tail))
    return body


def question_text(question: dict) -> str:
    """An ``ask_user`` question in a DM, with its options as a list."""
    text = neutralise(str(question.get("question") or ""))
    options = [neutralise(str(o)) for o in question.get("options") or []]
    if options:
        text += "\n" + "\n".join(f"- {o}" for o in options[:5])
    return text[:LIMIT]


def slow_answer_prefix(discord_user_id: str) -> str:
    """The only ping Mylo's chat ever sends: the asker's own, on a slow answer."""
    return f"<@{int(discord_user_id)}> "
