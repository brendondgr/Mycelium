"""How Mylo's chat answers look in Discord (plan D). Pure functions: no Django,
no Discord I/O, so every rule here is tested without either.

* The status line comes from the agent's activity view (S-9): what Mylo is
  doing, never what it is thinking.
* Answers are split under 2,000 characters on paragraph boundaries and never
  inside a code fence (a fence cut in two is closed and reopened).
* Nothing Mylo writes can ping anyone: ``<@…>``, ``<@&…>``, ``@everyone`` and
  ``@here`` in model output are neutralised here, and every send also carries
  ``AllowedMentions.none()`` (the cog's job).
* Discord unfurls a link in a bot message without anyone clicking it, so a
  prompt-injected ``https://evil/?d=<private data>`` would leak through the
  preview. Every URL the model writes is wrapped in ``<…>`` (no preview) by
  :func:`defang_urls`, and the cog also sends with ``suppress_embeds=True``.
* A citation (``#3``) is a masked link where it stands in the answer, with
  its embed suppressed (``<url>``). Only a source with nowhere to link to
  is listed under the answer, by title.
* A list of links is posted after the answer only when Mylo asks for one
  by ending the answer with ``[[links]]`` (the person asked for links, or
  for things to open). The marker itself is never shown.
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


def _linkable(source: dict) -> bool:
    url = str(source.get("url") or "")
    return url.startswith(("http://", "https://")) and ">" not in url


_CODE = re.compile(r"(```.*?(?:```|\Z)|`[^`\n]*`)", re.S)
#: ``#3`` that is not already a link's text, part of a word, or a URL fragment.
_CITE = re.compile(r"(?<![\w\[/#])#(\d+)\b(?!\]\()")


#: A URL the model wrote, already wrapped (``<https://…>``) or bare.
_URL = re.compile(r"<?\b[a-z][a-z0-9+.-]*://[^\s<>]+>?", re.I)
_TRAILING = ".,;:!?'\"*_~"


def _wrap(match: re.Match) -> str:
    url = match.group(0)
    if url.startswith("<") and url.endswith(">"):
        return url  # already embed-free
    url = url.lstrip("<").rstrip(">")
    tail = ""
    # punctuation (and an unbalanced ``)`` closing a masked link or a
    # parenthesis) belongs to the sentence, not the URL
    while url and (
        url[-1] in _TRAILING or (url[-1] == ")" and url.count(")") > url.count("("))
    ):
        url, tail = url[:-1], url[-1] + tail
    if "://" not in url or url.endswith("://"):
        return match.group(0)
    return f"<{url}>{tail}"


def defang_urls(text: str) -> str:
    """Every URL in model output wrapped in ``<…>``, so Discord shows it
    without fetching a preview. A bare URL and a masked link's target
    (``[t](https://…)``) are both wrapped; code is left as written (Discord
    never previews a link inside code)."""
    parts = _CODE.split(text or "")
    return "".join(p if i % 2 else _URL.sub(_wrap, p) for i, p in enumerate(parts))


def link_citations(text: str, sources: list[dict]) -> str:
    """Each ``#n`` the answer cites becomes a masked link to that source, in
    place, with its embed suppressed. Code is left as written."""
    urls = {int(s["n"]): str(s["url"]) for s in sources or [] if _linkable(s)}
    if not urls:
        return text

    def cite(match: re.Match) -> str:
        url = urls.get(int(match.group(1)))
        return f"[#{match.group(1)}](<{url}>)" if url else match.group(0)

    parts = _CODE.split(text or "")
    return "".join(p if i % 2 else _CITE.sub(cite, p) for i, p in enumerate(parts))


#: Mylo's request for a list of links after the answer (see the prompt).
_LINKS_MARK = re.compile(r"[ \t]*\[\[links\]\][ \t]*", re.I)


def take_links_mark(text: str) -> tuple[str, bool]:
    """The answer without the ``[[links]]`` marker, and whether it was there."""
    out, found = _LINKS_MARK.subn("", text or "")
    return out.strip(), bool(found)


def _short_title(source: dict, width: int = 90) -> str:
    title = neutralise(str(source.get("title") or ""))
    title = re.sub(r"^\[\w+\]\s*", "", title).replace("[", "(").replace("]", ")")
    return title if len(title) <= width else title[: width - 1].rstrip() + "…"


def links_block(sources: list[dict]) -> str:
    """The cited items as a list of links, for the message after an answer."""
    lines = [
        f"- [{_short_title(s)}](<{s['url']}>)" for s in sources or [] if _linkable(s)
    ]
    return "**Links**\n" + "\n".join(lines) if lines else ""


def sources_block(sources: list[dict]) -> str:
    """The sources a citation cannot link to (a lab, a project, an item with
    no page), by title, in small text. Linked ones are not listed again: the
    answer already names them and its ``#n`` opens them."""
    lines = []
    for s in sources or []:
        if _linkable(s):
            continue
        title = (
            neutralise(str(s.get("title") or "")).replace("[", "(").replace("]", ")")
        )
        if len(title) > 90:
            title = title[:89].rstrip() + "…"
        lines.append(f"-# #{s.get('n')} {title}")
    return "\n".join(lines)


def model_line(model: dict | None, *, first: bool) -> str:
    """Which model answered, said only when it does not run on this machine
    (S-3, S-21). ``first`` is kept for callers; a local model is never named."""
    if not model:
        return ""
    label = str(model.get("label") or model.get("name") or "")
    if not label:
        return ""
    where = model.get("location") or "local"
    if where == "local":
        return ""
    place = "in the cloud" if where == "cloud" else "on another server"
    return f"-# {neutralise(label)} · runs {place}"


def answer_chunks(
    text: str, sources: list[dict], model: dict | None, *, first: bool
) -> list[str]:
    """The whole answer as messages: text split safely with its citations
    as links, then unlinked sources and the model line on the last chunk (or
    a chunk of their own)."""
    text, wants_links = take_links_mark(text)
    body = split(link_citations(defang_urls(neutralise(text)), sources)) or [
        "(Mylo had nothing to say.)"
    ]
    tail = "\n".join(
        p for p in (sources_block(sources), model_line(model, first=first)) if p
    )
    if tail:
        if len(body[-1]) + len(tail) + 2 <= LIMIT:
            body[-1] = f"{body[-1]}\n\n{tail}"
        else:
            body.extend(split(tail))
    if wants_links:
        # a message of its own, after the answer
        body.extend(split(links_block(sources)))
    return body


def question_text(question: dict) -> str:
    """An ``ask_user`` question in a DM, with its options as a list."""
    text = defang_urls(neutralise(str(question.get("question") or "")))
    options = [defang_urls(neutralise(str(o))) for o in question.get("options") or []]
    if options:
        text += "\n" + "\n".join(f"- {o}" for o in options[:5])
    return text[:LIMIT]


def slow_answer_prefix(discord_user_id: str) -> str:
    """The only ping Mylo's chat ever sends: the asker's own, on a slow answer."""
    return f"<@{int(discord_user_id)}> "
