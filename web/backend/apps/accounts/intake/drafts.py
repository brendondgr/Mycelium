"""The shared output shape every author adapter normalizes into.

:class:`AuthorProfileDraft` is the parity contract: each normalizer
(scholar/openalex/semantic) must return this exact set of fields, which is what
makes the three sources interchangeable. The draft is *profile-focused* — it
carries aggregated interest signal and provenance, not paper records for content
ingest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.accounts.interests import CURRENT_VERSION


@dataclass
class AuthorProfileDraft:
    """Aggregated interest signal for one author, drawn from ≤N recent works."""

    display_name: str = ""
    institution: str = ""
    areas: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    coauthors: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_interests(self, *, statement: str = "") -> dict[str, Any]:
        """Render a contract-valid ``Profile.interests`` payload (brief Phase A).

        Fills the keys an import/résumé can ground (``areas``/``keywords``/
        ``methods``/``skills``/``sources``); the remaining chat-sourced keys
        (``funding_needs``, ``eligibility``, ``seeking``, ``exclusions``) are left
        for the Mylo intake agent to gather. Most adapters leave ``skills`` empty
        — a résumé is the source that populates it.
        """

        interests: dict[str, Any] = {
            "version": CURRENT_VERSION,
            "areas": list(self.areas),
        }
        if statement:
            interests["statement"] = statement
        if self.keywords:
            interests["keywords"] = list(self.keywords)
        if self.methods:
            interests["methods"] = list(self.methods)
        if self.skills:
            interests["skills"] = list(self.skills)

        sources: dict[str, Any] = {k: v for k, v in self.external_ids.items() if v}
        if self.evidence:
            sources["evidence_count"] = len(self.evidence)
        if sources:
            interests["sources"] = sources
        return interests
