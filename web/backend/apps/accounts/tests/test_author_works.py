"""The author import keeps the works it read, instead of mining and discarding.

The import pulls a person's recent papers, extracts areas and keywords, and threw
the papers away. That was fine while the only question was "what does this person
work on". It is wrong for the question a project-aware report asks constantly:
*did the reader write this?* Surfacing someone their own paper as a discovery is
the most credibility-destroying thing a research feed can do, and Mylo already had
the list in hand.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.author_works import store_author_works
from apps.accounts.intake.drafts import AuthorProfileDraft
from apps.accounts.models import AuthorWork


def _draft(**rows) -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        evidence=[
            {
                "title": "Notes on the Analytical Engine",
                "year": 1843,
                "source_id": "W1",
                "cited_by": 900,
                "abstract": "On the engine.",
                "coauthors": ["Charles Babbage"],
                "doi": "10.1000/notes",
            },
            {
                "title": "A Second Memoir",
                "year": None,
                "source_id": "",
                "cited_by": None,
                "abstract": "",
                "coauthors": [],
                "doi": "",
            },
            {"title": "   ", "source_id": "W3"},
        ],
        **rows,
    )


@pytest.mark.django_db
def test_works_are_stored_with_everything_the_matcher_needs() -> None:
    user = User.objects.create_user("ada", password="p")

    written = store_author_works(user, _draft(), source="openalex")

    assert written == 2  # the untitled row is not a work
    first = AuthorWork.objects.get(source_id="W1")
    assert first.title == "Notes on the Analytical Engine"
    assert first.year == 1843
    assert first.doi == "10.1000/notes"
    assert first.coauthors == ["Charles Babbage"]


@pytest.mark.django_db
def test_a_work_with_no_source_id_is_still_kept() -> None:
    """Keyed on a hash of the title — which is what the matcher compares anyway."""
    user = User.objects.create_user("ada", password="p")

    store_author_works(user, _draft(), source="scholar")

    row = AuthorWork.objects.get(title="A Second Memoir")
    assert row.source_id.startswith("title:")
    # Stable across re-imports: an index-based key would renumber the whole list
    # whenever the source returned the works in a different order.
    store_author_works(user, _draft(), source="scholar")
    assert AuthorWork.objects.filter(title="A Second Memoir").count() == 1


@pytest.mark.django_db
def test_reimporting_updates_in_place_rather_than_accumulating() -> None:
    user = User.objects.create_user("ada", password="p")
    store_author_works(user, _draft(), source="openalex")

    revised = _draft()
    revised.evidence[0]["cited_by"] = 1200
    store_author_works(user, revised, source="openalex")

    assert AuthorWork.objects.filter(user=user, source="openalex").count() == 2
    assert AuthorWork.objects.get(source_id="W1").cited_by == 1200


@pytest.mark.django_db
def test_the_same_work_from_two_sources_is_two_rows() -> None:
    """Deliberate: the ids are a source's own, and reconciling them is a guess."""
    user = User.objects.create_user("ada", password="p")

    store_author_works(user, _draft(), source="openalex")
    store_author_works(user, _draft(), source="semantic")

    assert AuthorWork.objects.filter(user=user).count() == 4


@pytest.mark.django_db
def test_a_nonsense_year_is_dropped_rather_than_shown() -> None:
    user = User.objects.create_user("ada", password="p")
    draft = _draft()
    draft.evidence[0]["year"] = 0

    store_author_works(user, draft, source="openalex")

    assert AuthorWork.objects.get(source_id="W1").year is None


@pytest.mark.django_db
def test_storing_never_raises_and_never_costs_the_import() -> None:
    """The import's product is the interest draft; the works are a bonus."""
    assert store_author_works(None, _draft(), source="openalex") == 0
    user = User.objects.create_user("ada", password="p")
    assert store_author_works(user, AuthorProfileDraft(), source="openalex") == 0


@pytest.mark.django_db
def test_the_import_endpoint_keeps_the_works_it_previewed(monkeypatch) -> None:
    """The endpoint previews *interests*; the works are saved because it read them."""
    from apps.accounts import views

    user = User.objects.create_user("ada", password="p")
    monkeypatch.setattr(views, "import_author", lambda _id, _source: _draft())
    client = APIClient()
    client.force_authenticate(user)

    resp = client.post(
        "/api/auth/intake/import/",
        {"identifier": "A123", "source": "openalex"},
        format="json",
    )

    assert resp.status_code == 200
    assert AuthorWork.objects.filter(user=user).count() == 2


# --- identities and fields (collaboration-network plan CN-02) -----------------


def _openalex_payload():
    me = {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"}
    return {
        "author": me,
        "works": [
            {
                "id": "https://openalex.org/W7",
                "title": "Kriging reef temperatures",
                "publication_year": 2021,
                "primary_topic": {
                    "field": {"id": "https://openalex.org/fields/23"},
                },
                "authorships": [
                    {"author": me},
                    {
                        "author": {
                            "id": "https://openalex.org/A2",
                            "display_name": "Charles Babbage",
                        }
                    },
                ],
            }
        ],
    }


def test_the_openalex_import_keeps_coauthor_ids_and_the_field():
    from apps.accounts.intake.normalizers.openalex import normalize

    row = normalize(_openalex_payload()).evidence[0]
    assert row["coauthor_ids"] == ["A2"]
    assert row["field_id"] == "23"
    assert row["coauthors"] == ["Charles Babbage"]


@pytest.mark.django_db
def test_storing_a_work_keeps_its_identities_and_marks_the_field_checked():
    from apps.accounts.intake.normalizers.openalex import normalize

    user = User.objects.create_user("ada2", "ada2@example.org", "pw")
    store_author_works(user, normalize(_openalex_payload()), source="openalex")
    work = AuthorWork.objects.get(user=user)
    assert work.coauthor_ids == ["A2"]
    assert work.openalex_field_id == "23"
    assert work.field_checked_at is not None


@pytest.mark.django_db
def test_enrich_fields_asks_once_per_doi_and_retries_only_on_failure():
    import urllib.error

    from apps.accounts.author_works import enrich_fields

    user = User.objects.create_user("bo", "bo@example.org", "pw")
    user.profile.openalex_id = "A9"
    user.profile.save()

    def make(source_id, doi):
        return AuthorWork.objects.create(
            user=user, source="scholar", source_id=source_id, title=source_id, doi=doi
        )

    known, unknown, flaky, no_doi = (
        make("known", "10.1/known"),
        make("unknown", "10.1/unknown"),
        make("flaky", "10.1/flaky"),
        make("nodoi", ""),
    )
    asked = []

    def fetch(url):
        asked.append(url)
        if "known" in url and "unknown" not in url:
            return {
                "primary_topic": {"field": {"id": "https://openalex.org/fields/17"}},
                "authorships": [
                    {"author": {"id": "https://openalex.org/A9"}},
                    {"author": {"id": "https://openalex.org/A3"}},
                ],
            }
        if "unknown" in url:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        raise TimeoutError("slow")

    assert enrich_fields([known, unknown, flaky, no_doi], fetch=fetch) == 2
    for work in (known, unknown, flaky, no_doi):
        work.refresh_from_db()
    assert (known.openalex_field_id, known.coauthor_ids) == ("17", ["A3"])
    assert unknown.field_checked_at is not None and unknown.openalex_field_id == ""
    assert flaky.field_checked_at is None
    assert no_doi.field_checked_at is None
    assert len(asked) == 3

    asked.clear()
    enrich_fields([known, unknown], fetch=fetch)
    assert asked == []
