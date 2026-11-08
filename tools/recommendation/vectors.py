"""Profile-vector helpers shared by ranking and delivery.

Pure-Python cosine similarity and a member's interest vector (their stored
profile embedding, or one embedded on demand). Split out of the share fan-out
so ranking code can use them without importing delivery code.
"""

from __future__ import annotations

import math

from apps.accounts.embedding import canonical_text

from tools.retrieval import embeddings


def cosine(a, b) -> float:
    """Pure-Python cosine similarity; ``0.0`` for an empty or zero vector.

    Shared by :mod:`tools.recommendation.member_fit`, lab fit and the share fan-out,
    which thresholds on the same
    absolute similarity to shortlist who an item is for.
    """
    if not a or not b:
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def member_vector(user, *, embed_missing: bool = True) -> list[float] | None:
    """A member's interest vector: stored ``Profile.embedding`` or embed on demand."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.embedding is not None:
        return list(profile.embedding)
    if not embed_missing:
        return None
    text = canonical_text(profile)
    if not text.strip():
        return None
    return embeddings.embed_text(text)
