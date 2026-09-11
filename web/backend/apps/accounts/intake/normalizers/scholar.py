"""Normalize a Google Scholar ``{author, publications}`` payload into a draft.

scholarly exposes the author's research ``interests`` directly — the cleanest
area signal of the three sources. Coauthors come from each publication's
``bib.author`` string ("A and B and C").
"""

from __future__ import annotations

from typing import Any

from ..drafts import AuthorProfileDraft


def _interest_label(interest: Any) -> str:
    if isinstance(interest, dict):
        return interest.get("interest") or interest.get("title") or ""
    return str(interest or "")


def _split_authors(value: Any) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(" and ") if part.strip()]


def _year_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize(raw: dict[str, Any]) -> AuthorProfileDraft:
    author = raw.get("author") or {}
    publications = raw.get("publications") or author.get("publications") or []

    draft = AuthorProfileDraft(
        display_name=author.get("name") or "",
        institution=author.get("affiliation") or "",
    )
    scholar_id = author.get("scholar_id")
    if scholar_id:
        draft.external_ids["scholar"] = str(scholar_id)

    for interest in author.get("interests") or []:
        label = _interest_label(interest)
        if label:
            draft.areas.append(label)

    for pub in publications:
        bib = pub.get("bib") or {}
        pub_coauthors: list[str] = []
        for name in _split_authors(bib.get("author")):
            if name != draft.display_name:
                draft.coauthors.append(name)
                pub_coauthors.append(name)
        draft.evidence.append(
            {
                "title": bib.get("title") or "",
                "year": _year_or_none(bib.get("pub_year")),
                "source_id": pub.get("author_pub_id"),
                "cited_by": pub.get("num_citations"),
                "abstract": bib.get("abstract") or "",
                "coauthors": pub_coauthors,
                # Scholar exposes no DOI on a publication stub.
                "doi": "",
            }
        )

    return draft
