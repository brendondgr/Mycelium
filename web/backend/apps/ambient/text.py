"""Normalising message text for one purpose only: telling repeats apart.

A lab channel repeats itself. The same link is pasted in two channels, a
forwarded message quotes an earlier one word for word, somebody re-sends what
they wrote yesterday. Three copies of one thought are one piece of evidence, and
the profile should read them that way.

The normalisation here exists solely to produce that hash. It is never stored,
never shown, and never fed to a model — the normalised string is computed,
hashed, and dropped inside one function call.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Zero-width and bidi control characters. Copy-paste carries them and they would
# make two identical-looking messages hash differently.
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠﻿]")
_WHITESPACE = re.compile(r"\s+")
# Discord/Slack mention and custom-emoji syntax. The same sentence addressed to
# two different people is the same sentence.
_MENTION = re.compile(r"<[@#!&:][^>]{0,64}>")


def normalise(text: str) -> str:
    """Fold a message to its comparable core. For hashing only."""
    folded = unicodedata.normalize("NFKC", text or "")
    folded = _INVISIBLE.sub("", folded)
    folded = _MENTION.sub(" ", folded)
    folded = _WHITESPACE.sub(" ", folded)
    return folded.strip().casefold()


def content_hash(text: str) -> str:
    """The sha256 of the normalised text, hex. Empty text hashes to ``""``.

    An empty hash means "nothing to compare" rather than "identical to every
    other empty message", so attachment-only posts never collapse into one
    another.
    """
    folded = normalise(text)
    if not folded:
        return ""
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()
