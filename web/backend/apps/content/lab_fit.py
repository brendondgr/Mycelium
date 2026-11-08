"""Which of a department's labs could lead a call — lab-fit, mirroring member-fit.

A department post names labs, never people (plan "What a department sees"). This
ranks the department's labs against one item by the cosine between the item's
vector and each lab's profile vector (stored, or its canonical text embedded by the
item model), above a floor, best first, and says on what grounds: the lab's own
areas that literally appear in the call. No language-model call: the department
post's other prose comes from the bounded editor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings
from tools.recommendation.vectors import cosine
from tools.retrieval.models import ContentItem

#: Labs a department post names under "Labs that could lead".
MAX_LABS = 3


@dataclass(frozen=True)
class LabCandidate:
    lab_id: int
    name: str
    vector: list[float]
    areas: tuple[str, ...]


def candidates(department) -> list[LabCandidate]:
    """The department's labs with a profile vector: the stored one when a lab has
    it, otherwise its canonical text embedded now by the same model the items use
    (nothing writes a stored lab vector today). Labs with no profile text, or no
    embedder installed, are left out."""
    from tools.recommendation.targets import target_for_lab
    from tools.retrieval import embeddings

    from apps.accounts.models import Lab

    found: list[tuple] = []
    missing: list[tuple] = []
    for lab in Lab.objects.filter(department=department).select_related("profile"):
        profile = getattr(lab, "profile", None)
        areas = tuple(
            " ".join(str(a).split()).lower()
            for a in (getattr(profile, "areas", None) or [])
            if str(a).strip()
        )
        vector = None if profile is None else profile.embedding
        if vector is None or len(vector) == 0:
            vector = None if profile is None else profile.derived_embedding
        if vector is not None and len(vector) > 0:
            found.append((lab, list(vector), areas))
            continue
        text = target_for_lab(lab).embedding_text.strip()
        if text:
            missing.append((lab, text, areas))
    if missing:
        vectors = embeddings.embed_texts([text for _lab, text, _a in missing]) or []
        for (lab, _text, areas), vector in zip(missing, vectors, strict=False):
            if vector is not None and len(vector) > 0:
                found.append((lab, list(vector), areas))
    return [
        LabCandidate(lab.id, lab.name, vector, areas) for lab, vector, areas in found
    ]


def rank(
    item: ContentItem,
    labs: Sequence[LabCandidate],
    *,
    floor: float | None = None,
    limit: int = MAX_LABS,
) -> list[dict]:
    """``[{"lab_id", "name", "fit", "why"}]`` best first; empty without vectors."""
    vector = item.embedding
    if vector is None or len(vector) == 0 or not labs:
        return []
    floor = getattr(settings, "LAB_FIT_COSINE_FLOOR", 0.45) if floor is None else floor
    text = _item_text(item)
    scored = [(lab, cosine(list(vector), lab.vector)) for lab in labs]
    scored = [pair for pair in scored if pair[1] >= floor]
    scored.sort(key=lambda pair: (-pair[1], pair[0].name))
    out = []
    for lab, fit in scored[:limit]:
        shared = [area for area in lab.areas if len(area) > 3 and area in text][:2]
        out.append(
            {
                "lab_id": lab.lab_id,
                "name": lab.name,
                "fit": round(fit, 4),
                "why": ", ".join(shared) if shared else "closest to the lab's profile",
            }
        )
    return out


def _item_text(item: ContentItem) -> str:
    meta = item.metadata or {}
    parts = [meta.get("title") or meta.get("name") or ""]
    for key in ("description", "ai_summary", "blurb", "search_text"):
        if meta.get(key):
            parts.append(str(meta[key]))
            break
    return " ".join(" ".join(parts).split()).lower()
