"""Normalize a Semantic Scholar ``{author, papers}`` payload into a draft."""

from __future__ import annotations

from typing import Any

from ..drafts import AuthorProfileDraft


def _external_ids(author: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    author_id = author.get("authorId")
    if author_id:
        ids["semantic"] = str(author_id)
    orcid = (author.get("externalIds") or {}).get("ORCID")
    if orcid:
        ids["orcid"] = str(orcid)
    return ids


def normalize(raw: dict[str, Any]) -> AuthorProfileDraft:
    author = raw.get("author") or {}
    papers = raw.get("papers") or []

    affiliations = author.get("affiliations") or []
    draft = AuthorProfileDraft(
        display_name=author.get("name") or "",
        institution=affiliations[0] if affiliations else "",
        external_ids=_external_ids(author),
    )

    for paper in papers:
        for field_of_study in paper.get("fieldsOfStudy") or []:
            if field_of_study:
                draft.areas.append(field_of_study)
        for s2_field in paper.get("s2FieldsOfStudy") or []:
            category = (s2_field or {}).get("category")
            if category:
                draft.areas.append(category)
        for coauthor in paper.get("authors") or []:
            name = (coauthor or {}).get("name")
            if name and name != draft.display_name:
                draft.coauthors.append(name)
        draft.evidence.append(
            {
                "title": paper.get("title") or "",
                "year": paper.get("year"),
                "source_id": paper.get("paperId"),
                "cited_by": paper.get("citationCount"),
            }
        )

    return draft
