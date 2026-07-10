"""Generalizing the matcher's scoring target from the user to a lab / project.

The builder logic (which interests / watch topics / persist FK a target yields) is
pure and runs on SQLite; the full recommend + opportunity matching over pgvector is
gated on PostgreSQL, mirroring ``test_pipeline`` / ``test_opportunities``.
"""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import Lab, WatchPreference
from apps.content import embeddings
from apps.content.models import ContentItem, RelevanceScore
from apps.content.opportunities import match_opportunities_for_target
from apps.content.pipeline import recommend_for_lab, recommend_for_project
from apps.content.targets import (
    project_interests,
    project_watch_topics,
    target_for_lab,
    target_for_project,
    target_for_user,
)
from apps.research.models import Project

_TOKENS = ["graph", "health", "biomedical", "other"]


def _fake_embed(texts):
    out = []
    for text in texts:
        low = text.casefold()
        vec = [1.0 if tok in low else 0.0 for tok in _TOKENS]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


@pytest.fixture(autouse=True)
def _reset_embedder():
    embeddings.reset_embedder()
    yield
    embeddings.reset_embedder()


# -- pure: target builders ----------------------------------------------------


@pytest.mark.django_db
def test_target_for_user_carries_interests_and_persist_fk():
    user = User.objects.create_user("u", password="x")
    user.profile.interests = {"areas": ["Knowledge Graphs"], "keywords": ["bio"]}
    user.profile.save()
    WatchPreference.objects.update_or_create(user=user, defaults={"topics": ["KG"]})

    target = target_for_user(user)

    assert target.kind == "user"
    assert target.key == "u"
    assert target.interests["areas"] == ["Knowledge Graphs"]
    assert target.watch_topics == ["KG"]
    assert target.persist_kwargs == {"target_user": user}


@pytest.mark.django_db
def test_target_for_lab_reads_curated_columns_and_watch():
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.statement = "We study graphs."
    lab.profile.areas = ["Knowledge Graphs", "Health"]
    lab.profile.save()
    lab.watch.topics = ["graph databases"]
    lab.watch.save()

    target = target_for_lab(lab)

    assert target.kind == "lab"
    assert target.key == "graph-lab"
    assert target.interests["areas"] == ["Knowledge Graphs", "Health"]
    assert target.watch_topics == ["graph databases"]
    assert target.persist_kwargs == {"target_lab": lab}
    # Institutional surfaces keep areas in the embedded text (unlike a person).
    assert "Knowledge Graphs" in target.embedding_text


def test_project_interests_prefers_explicit_focus():
    project = Project(
        name="Cyber",
        goals={"interests": {"areas": ["Cybersecurity"], "keywords": ["malware"]}},
    )
    assert project_interests(project) == {
        "areas": ["Cybersecurity"],
        "keywords": ["malware"],
        "statement": "",
    }


def test_project_interests_derives_from_legacy_goals():
    project = Project(
        name="Legacy",
        goals={"topics": ["Robotics", "Robotics"], "description": "Arm control"},
    )
    ints = project_interests(project)
    assert ints["areas"] == ["Robotics"]  # deduped
    assert ints["statement"] == "Arm control"


def test_project_watch_topics_falls_back_to_areas():
    explicit = Project(name="A", goals={"watch_topics": ["quantum"]})
    assert project_watch_topics(explicit) == ["quantum"]
    derived = Project(name="B", goals={"interests": {"areas": ["Optics"]}})
    assert project_watch_topics(derived) == ["Optics"]


def test_target_for_project_scopes_persist_to_project():
    project = Project(name="Cyber", goals={"interests": {"areas": ["Cybersecurity"]}})
    target = target_for_project(project)
    assert target.kind == "project"
    assert target.interests["areas"] == ["Cybersecurity"]
    assert target.persist_kwargs == {"target_project": project}


# -- full recommend / match over pgvector -------------------------------------


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the target retrieval path needs PostgreSQL + pgvector")


def _vpaper(source, title, vector):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=vector,
        metadata={"title": title, "abstract": title},
    )


@pytest.mark.django_db
def test_recommend_for_lab_persists_lab_scores(pgvector):
    """A lab's aggregate interests produce RelevanceScore rows under target_lab."""
    embeddings.set_embedder(_fake_embed)
    p_both = _vpaper("both", "graph health", [1.0, 1.0, 0.0, 0.0])
    _vpaper("far", "unrelated other topic", [0.0, 0.0, 0.0, 1.0])

    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph", "health"]
    lab.profile.save()

    result = recommend_for_lab(lab, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.interests == 2
    scores = RelevanceScore.objects.filter(target_lab=lab)
    assert scores.filter(content=p_both).exists()
    top = scores.get(content=p_both)
    assert top.signals["n_matched"] == 2
    # No cross-contamination: nothing was written to a user or project target.
    assert not RelevanceScore.objects.filter(target_user__isnull=False).exists()
    assert not RelevanceScore.objects.filter(target_project__isnull=False).exists()


@pytest.mark.django_db
def test_recommend_for_project_is_independent_of_lab(pgvector):
    """A project's own focus scores under target_project, distinct from its lab."""
    embeddings.set_embedder(_fake_embed)
    p_graph = _vpaper("graph", "graph theory", [1.0, 0.0, 0.0, 0.0])
    p_health = _vpaper("health", "public health", [0.0, 1.0, 0.0, 0.0])

    lab = Lab.objects.create(name="Broad Lab", slug="broad-lab")
    # A narrow, cybersecurity-style project: only the "graph" axis here.
    project = Project.objects.create(
        scope_lab=lab, name="Graph project", goals={"interests": {"areas": ["graph"]}}
    )

    result = recommend_for_project(project, complete=lambda _p: None)

    assert result.status == "ok"
    proj_scores = RelevanceScore.objects.filter(target_project=project)
    assert proj_scores.filter(content=p_graph).exists()
    # The unrelated "health" paper fell below the per-interest floor for this
    # single-area project and was not surfaced.
    assert not proj_scores.filter(content=p_health).exists()


@pytest.mark.django_db
def test_recommend_for_target_no_interests_short_circuits():
    """A target with no declared interests skips instead of scanning the corpus."""
    lab = Lab.objects.create(name="Empty Lab", slug="empty-lab")
    result = recommend_for_lab(lab, complete=lambda _p: None)
    assert result.status == "no_interests"


@pytest.mark.django_db
def test_match_grants_for_lab_target(pgvector):
    """Grants match against a lab target and persist under target_lab."""
    from apps.scraper.pivot.ingest import ingest_pivot

    embeddings.set_embedder(_fake_embed)
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()

    ingest_pivot(
        [
            (
                "grants",
                {
                    "id": "g_match",
                    "title": "graph theory research award",
                    "sponsor": "NSF",
                    "deadline_date": "2026-12-01",
                    "url": "https://pivot.proquest.com/funding_opps/g_match",
                    "matched_topics": "graph",
                },
            )
        ],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )

    result = match_opportunities_for_target(
        target_for_lab(lab), "grants", complete=lambda _p: None, today="2026-07-05"
    )

    assert result.status == "ok"
    scores = RelevanceScore.objects.filter(target_lab=lab, content__type="grant")
    assert scores.exists()
    assert scores.first().signals["area"] == "grant"


# -- daily batch + refit fan out to labs and projects -------------------------


def _no_search(*_args, **_kwargs):
    return []


@pytest.mark.django_db
def test_daily_batch_matches_labs_and_projects(pgvector):
    """A single daily paper run also recommends for labs and their projects."""
    from apps.content.pipeline import run_daily_batch

    embeddings.set_embedder(_fake_embed)
    p_both = _vpaper("both", "graph health", [1.0, 1.0, 0.0, 0.0])

    lab = Lab.objects.create(name="Both Lab", slug="both-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()
    project = Project.objects.create(
        scope_lab=lab, name="Health project", goals={"interests": {"areas": ["health"]}}
    )

    result = run_daily_batch(
        [], labs=[lab], projects=[project], search_fn=_no_search,
        embed=False, complete=lambda _p: None,
    )

    statuses = {r.username: r.status for r in result.results}
    assert statuses["both-lab"] == "ok"
    assert statuses[str(project.id)] == "ok"
    assert RelevanceScore.objects.filter(target_lab=lab, content=p_both).exists()
    assert RelevanceScore.objects.filter(
        target_project=project, content=p_both
    ).exists()


@pytest.mark.django_db
def test_daily_opportunities_batch_matches_lab(pgvector):
    from apps.content.opportunities import run_daily_opportunities_batch
    from apps.scraper.pivot.ingest import ingest_pivot

    embeddings.set_embedder(_fake_embed)
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()
    ingest_pivot(
        [
            (
                "grants",
                {
                    "id": "g",
                    "title": "graph theory award",
                    "sponsor": "NSF",
                    "deadline_date": "2026-12-01",
                    "url": "https://pivot.proquest.com/funding_opps/g",
                    "matched_topics": "graph",
                },
            )
        ],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )

    batch = run_daily_opportunities_batch(
        [], labs=[lab], areas=("grants",), ingest=False, prune=False,
        complete=lambda _p: None, today="2026-07-05",
    )

    ok = [r for r in batch.results if r.status == "ok" and r.username == "graph-lab"]
    assert ok, batch.results
    assert RelevanceScore.objects.filter(target_lab=lab, content__type="grant").exists()


@pytest.mark.django_db
def test_refit_lab_scores_over_existing_store(pgvector):
    from apps.content.refitting import refit_lab

    embeddings.set_embedder(_fake_embed)
    _vpaper("both", "graph health", [1.0, 1.0, 0.0, 0.0])
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()

    result = refit_lab(lab, areas=("papers",), complete=lambda _p: None)

    assert result.status == "ok"
    assert result.areas["papers"]["status"] == "ok"
    assert RelevanceScore.objects.filter(target_lab=lab).exists()
