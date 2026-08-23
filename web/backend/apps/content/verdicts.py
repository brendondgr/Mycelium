"""The four-point verdict that replaced the percent match.

A percentage implied a measurement the system never made. The number came out of
a language model asked to guess a similarity, was rendered next to a
deterministic embedding cosine that meant something else entirely, and a reader
had no way to know which was which. Position within a theme plus a qualitative
verdict says the same useful thing without the false precision:

============  ==========================================================
``read``      Worth their attention today.
``skim``      Worth a look; the abstract may be enough.
``file``      Keep for later — relevant, not urgent.
``skip``      Not worth their time. Never chipped; the item drops to the
              reference block with no write-up and no narrative mention.
============  ==========================================================

Two derivations, and both must exist (plan §18). The deterministic one is the
**baseline product**, not a fallback: most readers are on a plan without model
reasoning and their document must read as complete, not as a paid one with the
good parts missing. :func:`derive_verdict` gives them a verdict from the one
thing that is always true — where the item landed in its own theme's ranking.
:func:`parse_verdict` handles the paid path, where the model judged it.
"""

from __future__ import annotations

from typing import Any

READ = "read"
SKIM = "skim"
FILE = "file"
SKIP = "skip"

#: The only four values that may ever be persisted. A model returning anything
#: else is a parse failure, not a new category.
VERDICTS: tuple[str, ...] = (READ, SKIM, FILE, SKIP)

#: Chip copy. ``skip`` deliberately has no chip — see the module docstring.
VERDICT_LABELS: dict[str, str] = {
    READ: "Read",
    SKIM: "Skim",
    FILE: "File",
    SKIP: "Skip",
}

#: What each verdict tells the reader, for tooltips and accessible names.
VERDICT_BLURBS: dict[str, str] = {
    READ: "Worth your attention today.",
    SKIM: "Worth a look — the abstract may be enough.",
    FILE: "Relevant, but not urgent. Keep it for later.",
    SKIP: "Probably not worth your time.",
}

#: Rank bands, as a fraction of the theme's slate depth. The top fifth is a read,
#: the next third a skim, the rest a file. Nothing is *derived* as a skip: a skip
#: is a judgement that something is not worth reading, and a deterministic ranker
#: has no basis for it — being twentieth in a theme is not the same as being bad.
_READ_BAND = 0.2
_SKIM_BAND = 0.5


def derive_verdict(position: int, *, depth: int) -> str:
    """The deterministic verdict for an item at ``position`` in a slate of ``depth``.

    Position is 1-based and within the item's **own theme**, which is the only
    reason this is meaningful: a global position would be comparing scores that
    are not comparable, which is the failure this whole redesign removes.
    """
    if depth <= 0 or position <= 0:
        return FILE
    fraction = position / depth
    if fraction <= _READ_BAND:
        return READ
    if fraction <= _SKIM_BAND:
        return SKIM
    return FILE


def parse_verdict(value: Any) -> str | None:
    """Normalise a model-supplied verdict, or ``None`` when it is not one of ours.

    ``None`` means the caller must fall back rather than persist a novel label —
    a fifth verdict appearing in the store is unreadable in the UI and
    undebuggable in the eval harness, so it is rejected at the boundary.
    """
    if not isinstance(value, str):
        return None
    normalised = value.strip().casefold()
    return normalised if normalised in VERDICTS else None


def is_shown(verdict: str | None) -> bool:
    """Whether a verdict earns a write-up and a narrative mention.

    A ``skip`` does not. It keeps its slate place and appears in the reference
    block — hiding it would be a second, silent relevance filter on top of the
    ranking — but it gets no prose. This replaces the old after-the-fact hiding
    filter, which could spend the model budget and then discard the output.
    """
    return verdict in (READ, SKIM, FILE)
