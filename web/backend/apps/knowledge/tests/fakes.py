"""A deterministic stand-in for the corpus embedder.

Unknown wordings get a pseudo-random unit vector seeded by their text, so two
different wordings are far apart (cosine well under the merge threshold) and
the same wording always lands in the same place. Tests that need two wordings
to be *near* each other say so with :meth:`FakeEmbedder.near`.
"""

from __future__ import annotations

import hashlib
import math

DIM = 16


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def _seeded(text: str) -> list[float]:
    digest = hashlib.sha256(text.casefold().encode()).digest()
    return _unit([(byte / 127.5) - 1.0 for byte in digest[:DIM]])


class FakeEmbedder:
    def __init__(self) -> None:
        self.fixed: dict[str, list[float]] = {}
        self.calls: list[list[str]] = []

    def near(self, anchor: str, *others: str, spread: float = 0.05) -> None:
        """Place each of ``others`` a small step away from ``anchor``."""
        base = self.vector(anchor)
        self.fixed[anchor.casefold()] = base
        for index, other in enumerate(others, start=1):
            offset = _seeded(f"{other}#{index}")
            self.fixed[other.casefold()] = _unit(
                [b + spread * o for b, o in zip(base, offset, strict=True)]
            )

    def vector(self, text: str) -> list[float]:
        return self.fixed.get(text.casefold()) or _seeded(text)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self.vector(text) for text in texts]
