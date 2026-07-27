"""Compose a research-interest profile from a site import and/or a résumé.

This is the orchestration behind onboarding's "Grow my profile": gather text
about the researcher (works' titles + declared interests from a source, and/or
the raw résumé text), hand the whole corpus to the LLM extractor to produce every
interest field in one structured call, and shape the result into a contract-valid
``interests`` payload. When the model is unavailable the structured author draft
(the same signal the importer already computes) is the deterministic fallback, so
the flow never depends on a running model.
"""

from __future__ import annotations

from typing import Any

from apps.accounts.interests import CURRENT_VERSION
from apps.content.clustering import MAX_CLUSTERS

from .drafts import AuthorProfileDraft
from .extract import CompleteFn, ProfileFields, extract_profile_fields
from .merge import merge_drafts
from .resume import draft_from_resume
from .statement import draft_statement

__all__ = ["build_corpus", "synthesize_interests"]


def synthesize_interests(
    *,
    site_draft: AuthorProfileDraft | None = None,
    resume_text: str = "",
    provenance: dict[str, str] | None = None,
    complete: CompleteFn | None = None,
    max_clusters: int = MAX_CLUSTERS,
    max_areas_per_cluster: int | None = None,
) -> tuple[AuthorProfileDraft, dict[str, Any]]:
    """Return ``(merged_draft, interests)`` for the gathered sources.

    ``site_draft`` is an imported author draft (optional); ``resume_text`` is the
    raw extracted résumé text (optional). At least one should carry signal.
    ``max_clusters`` / ``max_areas_per_cluster`` are the caller's plan caps: the
    synthesised clusters are clamped to them here so the organize step opens with
    a grouping the user can actually save, instead of spilling the overflow into
    the Unsorted tray.
    """

    # A deterministic résumé draft backs the fallback path (no model needed).
    resume_draft = (
        draft_from_resume(resume_text, complete=lambda _prompt: None)
        if resume_text.strip()
        else None
    )
    merged = merge_drafts(site_draft, resume_draft)

    corpus = build_corpus(site_draft, resume_text)
    fields = extract_profile_fields(
        corpus,
        complete=complete,
        fallback=lambda: _fields_from_draft(merged),
    )
    interests = _interests_from_fields(fields, merged, provenance or {})
    _attach_clusters(
        interests,
        corpus=corpus,
        complete=complete,
        max_clusters=max_clusters,
        max_areas_per_cluster=max_areas_per_cluster,
    )
    return merged, interests


def _attach_clusters(
    interests: dict[str, Any],
    *,
    corpus: str,
    complete: CompleteFn | None,
    max_clusters: int = MAX_CLUSTERS,
    max_areas_per_cluster: int | None = None,
) -> None:
    """Organise the just-built interests into theme→sub-topic clusters in place.

    Runs the same :func:`compose_clusters` reasoning the "instruct Mylo" box uses,
    grounded in the source corpus, so a profile Mylo builds at sign-up ships the
    same cluster shape a user would get from describing their interests by hand.
    The widened area list (union of the clusters' sub-topics) replaces ``areas``
    so the contract's partition rule holds. A no-op when composition yields
    nothing (e.g. the model is unavailable and there is nothing to group).
    """
    from .clusters import compose_clusters

    clusters, _source = compose_clusters(
        corpus=corpus,
        areas=interests.get("areas", []),
        keywords=interests.get("keywords", []),
        statement=interests.get("statement", ""),
        complete=complete,
        max_clusters=max_clusters,
        max_areas_per_cluster=max_areas_per_cluster,
    )
    if not clusters:
        return
    union = _union_areas(clusters)
    if union:
        interests["areas"] = union
        interests["clusters"] = clusters


def _union_areas(clusters: list[dict]) -> list[str]:
    """Ordered, case-insensitively de-duplicated union of every cluster's areas."""
    out: list[str] = []
    seen: set[str] = set()
    for cluster in clusters:
        for area in cluster.get("areas", []):
            key = str(area).casefold()
            if area and key not in seen:
                seen.add(key)
                out.append(area)
    return out


def build_corpus(draft: AuthorProfileDraft | None, resume_text: str) -> str:
    """Assemble the text the model reads: source signal + raw résumé text."""

    parts: list[str] = []
    if draft is not None:
        if draft.display_name:
            parts.append(f"Name: {draft.display_name}")
        if draft.institution:
            parts.append(f"Institution: {draft.institution}")
        if draft.areas:
            parts.append("Declared areas: " + ", ".join(draft.areas))
        if draft.keywords:
            parts.append("Keywords: " + ", ".join(draft.keywords))
        titles = [
            str(item.get("title", "")).strip()
            for item in draft.evidence
            if str(item.get("title", "")).strip()
        ]
        if titles:
            parts.append("Published works:")
            parts.extend(f"- {title}" for title in titles[:25])
        abstracts = [
            str(item.get("abstract", "")).strip()
            for item in draft.evidence
            if str(item.get("abstract", "")).strip()
        ]
        if abstracts:
            parts.append("Abstracts:")
            parts.extend(abstracts[:10])
    text = (resume_text or "").strip()
    if text:
        parts.append("Résumé / CV text:")
        parts.append(text)
    return "\n".join(parts)


def _fields_from_draft(draft: AuthorProfileDraft) -> ProfileFields:
    """The offline fallback: the structured signal the importer already has."""

    return {
        "statement": draft_statement(draft, complete=lambda _prompt: None),
        "areas": list(draft.areas),
        "keywords": list(draft.keywords),
        "skills": list(draft.skills),
    }


def _interests_from_fields(
    fields: ProfileFields,
    draft: AuthorProfileDraft,
    provenance: dict[str, str],
) -> dict[str, Any]:
    interests: dict[str, Any] = {
        "version": CURRENT_VERSION,
        "areas": list(fields["areas"]),
    }
    if fields["statement"]:
        interests["statement"] = fields["statement"]
    if fields["keywords"]:
        interests["keywords"] = list(fields["keywords"])
    if fields["skills"]:
        interests["skills"] = list(fields["skills"])

    sources: dict[str, Any] = {k: v for k, v in draft.external_ids.items() if v}
    if draft.evidence:
        sources["evidence_count"] = len(draft.evidence)
    sources.update(provenance)
    if sources:
        interests["sources"] = sources
    return interests
