"""The embedding hook: build a canonical text blob and (re)embed on save.

Intake's deliverable is the canonical text plus the trigger; the scoring phase
owns the model and the vector dimension. Until then the embedder is a pluggable
no-op that leaves ``embedding`` NULL while ``embedding_text`` is persisted — so a
later re-embed is deterministic and the dimension stays unlocked (brief Phase F).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

#: An embedder maps canonical text to a vector (or ``None`` while deferred).
Embedder = Callable[[str], list[float] | None]


def _noop_embedder(text: str) -> None:
    return None


_embedder: Embedder = _noop_embedder


def get_embedder() -> Embedder:
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Install the embedder (scoring phase) or reset to the no-op (``None``)."""
    global _embedder
    _embedder = embedder or _noop_embedder


def _clean(items: Iterable | None) -> list[str]:
    return [str(item).strip() for item in (items or []) if str(item).strip()]


def build_canonical_text(
    *,
    statement: str = "",
    areas: Iterable | None = None,
    methods: Iterable | None = None,
    keywords: Iterable | None = None,
) -> str:
    """One canonical text blob: statement + joined areas/methods/keywords."""
    parts: list[str] = []
    if statement and statement.strip():
        parts.append(statement.strip())
    for label, items in (
        ("Areas", areas),
        ("Methods", methods),
        ("Keywords", keywords),
    ):
        cleaned = _clean(items)
        if cleaned:
            parts.append(f"{label}: {', '.join(cleaned)}")
    return "\n".join(parts)


def canonical_text(instance) -> str:
    """Canonical text for a Profile or a lab/dept interest surface.

    Profile draws purely from its ``interests`` contract; lab/dept surfaces
    prefer their curated columns, falling back to the contract.
    """
    interests = getattr(instance, "interests", None) or {}
    if hasattr(instance, "user"):  # Profile
        return build_canonical_text(
            statement=interests.get("statement", ""),
            areas=interests.get("areas", []),
            methods=interests.get("methods", []),
            keywords=interests.get("keywords", []),
        )
    # LabProfile / DeptProfile carry curated columns alongside the contract.
    return build_canonical_text(
        statement=getattr(instance, "statement", "") or interests.get("statement", ""),
        areas=getattr(instance, "areas", None) or interests.get("areas", []),
        methods=interests.get("methods", []),
        keywords=interests.get("keywords", []),
    )


def apply_embedding(instance) -> None:
    """Set ``embedding_text`` (and ``embedding`` if an embedder is installed).

    Called from ``pre_save`` so it runs before the row is written — no recursion,
    no extra query.
    """
    text = canonical_text(instance)
    instance.embedding_text = text
    vector = get_embedder()(text)
    if vector is not None:
        instance.embedding = vector
