"""What is worth keeping, decided before anything is kept.

Discord delivers far more than is useful. A server produces reaction spam,
"lol", bot embeds, and standup threads, and feeding all of it to an extractor
would cost money to learn nothing. These rules are the cheap pass that runs
first.

They are deliberately dull and entirely deterministic. Nothing here reads
meaning — that is Plan 04's, model-written, with no rule-based fallback. What
happens here is the opposite kind of decision: is this a bot, is this channel
excluded, is there enough here to be worth a person's privacy budget at all.

Every refusal names itself, so the daily counters can say *why* a quiet server
is quiet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings

from .models import Source

_LINK = re.compile(r"https?://\S+", re.IGNORECASE)
# A message that is only an emoji, a reaction word, or punctuation.
_CHATTER = re.compile(r"^[\W\d_]*$|^(lol|lmao|ok|okay|yes|no|ty|thanks|\+1)[.!]?$",
                      re.IGNORECASE)


@dataclass(frozen=True)
class Keep:
    """Whether a message is worth carrying, and the one reason it is not."""

    keep: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.keep


KEEP = Keep(True)


def min_chars() -> int:
    return int(getattr(settings, "AMBIENT_MIN_MESSAGE_CHARS", 24))


def max_chars() -> int:
    return int(getattr(settings, "AMBIENT_MAX_MESSAGE_CHARS", 4000))


def truncate(text: str) -> str:
    """Bound what goes into the buffer.

    Somebody pasting a whole paper into a channel is not making a remark, and a
    buffer entry the size of a document is a cost and a liability rather than
    evidence. The head is kept, because a pasted block says what it is in its
    first lines.
    """
    limit = max_chars()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def worth_keeping(
    text: str,
    *,
    source: Source | None = None,
    place_id: str = "",
    is_bot: bool = False,
    from_mylo: bool = False,
    explicit: bool = False,
    has_attachment: bool = False,
) -> Keep:
    """Whether to carry this message at all.

    ``explicit`` — somebody addressed Mylo on purpose — skips the length rule.
    A person who writes "yes" in answer to Mylo's question meant that, and
    dropping it for being three characters long would be the system refusing to
    hear its own conversation.
    """
    if is_bot and not from_mylo:
        return Keep(False, "bot")
    if source is not None and place_id and source.excludes(place_id):
        return Keep(False, "excluded_channel")

    body = (text or "").strip()
    if from_mylo or explicit:
        if not body and not has_attachment:
            return Keep(False, "empty")
        return KEEP

    if not body:
        return Keep(False, "empty") if not has_attachment else KEEP
    if _CHATTER.match(body):
        return Keep(False, "too_short")
    if len(body) < min_chars() and not _LINK.search(body) and not has_attachment:
        return Keep(False, "too_short")

    if source is not None and place_id and source.is_social(place_id):
        # A separate reason from an exclusion, though the outcome is the same:
        # a manager should be able to tell which of their two settings is why
        # a channel is quiet.
        return Keep(False, "social_channel")
    return KEEP
