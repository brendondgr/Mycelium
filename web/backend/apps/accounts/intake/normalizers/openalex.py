"""Normalize an OpenAlex ``{author, works}`` payload into an AuthorProfileDraft."""

from __future__ import annotations

from typing import Any

from ..drafts import AuthorProfileDraft


def _bare_id(value: Any) -> str:
    if not value:
        return ""
    return str(value).rstrip("/").rsplit("/", 1)[-1]


def _bare_orcid(value: Any) -> str:
    if not value:
        return ""
    return str(value).rstrip("/").rsplit("/", 1)[-1]


def _institution(author: dict[str, Any]) -> str:
    institutions = author.get("last_known_institutions")
    if isinstance(institutions, list) and institutions:
        return (institutions[0] or {}).get("display_name") or ""
    return (author.get("last_known_institution") or {}).get("display_name") or ""


def _external_ids(author: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    openalex = _bare_id(author.get("id"))
    if openalex:
        ids["openalex"] = openalex
    orcid = _bare_orcid(author.get("orcid"))
    if orcid:
        ids["orcid"] = orcid
    return ids


def normalize(raw: dict[str, Any]) -> AuthorProfileDraft:
    author = raw.get("author") or {}
    works = raw.get("works") or []

    draft = AuthorProfileDraft(
        display_name=author.get("display_name") or "",
        institution=_institution(author),
        external_ids=_external_ids(author),
    )

    for work in works:
        for topic in work.get("topics") or []:
            name = (topic or {}).get("display_name")
            if name:
                draft.areas.append(name)
            subfield = ((topic or {}).get("subfield") or {}).get("display_name")
            if subfield:
                draft.areas.append(subfield)
        for concept in work.get("concepts") or []:
            if (concept or {}).get("level", 99) <= 1:
                name = concept.get("display_name")
                if name:
                    draft.areas.append(name)
        for keyword in work.get("keywords") or []:
            name = (keyword or {}).get("display_name") or (keyword or {}).get("keyword")
            if name:
                draft.keywords.append(name)
        work_coauthors: list[str] = []
        work_coauthor_ids: list[str] = []
        own_id = draft.external_ids.get("openalex", "")
        for authorship in work.get("authorships") or []:
            person = (authorship or {}).get("author") or {}
            name = person.get("display_name")
            author_id = _bare_id(person.get("id"))
            if author_id and author_id == own_id:
                continue
            if name and name != draft.display_name:
                draft.coauthors.append(name)
                work_coauthors.append(name)
                if author_id:
                    work_coauthor_ids.append(author_id)
        draft.evidence.append(
            {
                "title": work.get("title") or work.get("display_name") or "",
                "year": work.get("publication_year"),
                "source_id": _bare_id(work.get("id")),
                "cited_by": work.get("cited_by_count"),
                "abstract": _abstract(work.get("abstract_inverted_index")),
                # Kept per work, not only aggregated on the draft: the
                # known-literature matcher asks "did *this* person write *this*
                # paper", which a flattened set of every collaborator cannot answer.
                "coauthors": work_coauthors,
                # By identity as well as by name, so "already works with" and
                # introduction paths rest on who, not on how a name is spelled.
                "coauthor_ids": work_coauthor_ids,
                "field_id": primary_field_id(work),
                "doi": _bare_doi(work.get("doi")),
            }
        )

    return draft


def primary_field_id(work: dict[str, Any]) -> str:
    """The OpenAlex field of a work's primary topic ("17", Computer Science).

    The field level, not the topic: topic assignment is too noisy to measure
    distance with, the field is not (collaboration-network design §5.6).
    """
    topic = work.get("primary_topic") or {}
    return _bare_id(
        ((topic.get("field") or {}) if isinstance(topic, dict) else {}).get("id")
    )


def _bare_doi(value: Any) -> str:
    """``10.1234/xyz`` from OpenAlex's full ``https://doi.org/…`` URL form."""
    text = str(value or "").strip()
    return text.rsplit("doi.org/", 1)[-1] if text else ""


def _abstract(inverted_index: Any) -> str:
    """Reconstruct an abstract from OpenAlex's word -> positions inverted index."""

    if not isinstance(inverted_index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, locations in inverted_index.items():
        for location in locations or []:
            if isinstance(location, int):
                positions.append((location, str(word)))
    positions.sort()
    return " ".join(word for _, word in positions)
