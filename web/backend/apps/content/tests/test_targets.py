"""Generalizing the matcher's scoring target from the user to a lab / project.

The builder logic (which interests / watch topics / persist FK a target yields) is
pure and runs on SQLite; the full recommend + opportunity matching over pgvector is
gated on PostgreSQL, mirroring ``test_pipeline`` / ``test_opportunities``.
"""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection
from tools.retrieval import embeddings
from tools.retrieval.models import ContentItem, RelevanceScore

from apps.accounts.models import Lab, WatchPreference
from apps.content.opportunities import match_opportunities_for_target
from apps.content.pipeline import recommend_for_lab, recommend_for_project
from apps.content.targets import (
    project_interests,
    project_watch_topics,
    target_for_department,
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


def _seed_grants(records, *, embedder, today):
    """Stand-in for the retired ``ingest_pivot`` test fixture (plan Phase 6
    deleted Pivot's grant ingest) — see ``test_opportunities.py``'s twin helper
    for the full rationale. These tests only ever seed one grant apiece to
    exercise lab/project target matching, not ingest.
    """
    created: list[ContentItem] = []
    texts: list[str] = []
    for area, rec in records:
        assert area == "grants", f"only grants are seeded here, got {area!r}"
        parts = (rec.get("title"), rec.get("sponsor"), rec.get("matched_topics"))
        text = " ".join(str(part) for part in parts if part)
        obj = ContentItem.objects.create(
            type=ContentItem.Type.GRANT,
            source="grants:test",
            external_id=rec["id"],
            source_url=rec.get("url", ""),
            metadata={
                "title": rec.get("title", ""),
                "sponsor": rec.get("sponsor", ""),
                "deadline_date": rec.get("deadline_date", ""),
                "matched_topics": rec.get("matched_topics", ""),
                "search_text": text,
                "first_seen": f"{today}T00:00:00+00:00",
            },
        )
        created.append(obj)
        texts.append(text)
    vectors = embedder(texts)
    for obj, vector in zip(created, vectors, strict=False):
        obj.embedding = vector
        obj.save(update_fields=["embedding"])
    return created


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


@pytest.mark.django_db
def test_target_for_department_mirrors_a_lab_under_its_own_fk():
    from apps.accounts.models import Department

    head = User.objects.create_user("head")
    dept = Department.objects.create(owner=head, name="Earth Sciences")
    dept.profile.statement = "Ocean and climate science."
    dept.profile.areas = ["Ocean Forecasting"]
    dept.profile.save()

    target = target_for_department(dept)

    assert target.kind == "department"
    assert target.key == str(dept.pk)
    assert target.interests["areas"] == ["Ocean Forecasting"]
    assert target.watch_topics == []  # opportunities only; no paper search
    assert target.persist_kwargs == {"target_department": dept}
    assert "Ocean Forecasting" in target.embedding_text


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


def test_project_interests_carries_v2_clusters():
    """A project with organized clusters exposes the partition (dispatch signal)."""
    from apps.content.clustering import cluster_interests

    project = Project(
        name="Structural ML",
        goals={
            "interests": {
                "areas": ["graph neural networks", "protein folding"],
                "keywords": [],
                "statement": "",
                "clusters": [
                    {
                        "id": "c-ml",
                        "label": "ML",
                        "areas": ["graph neural networks"],
                    },
                    {"id": "c-bio", "label": "Bio", "areas": ["protein folding"]},
                ],
            }
        },
    )
    target = target_for_project(project)
    clusters = cluster_interests(target.interests)
    # Two real clusters → the recommend_for_target dispatch takes the cluster path.
    assert [c.id for c in clusters] == ["c-ml", "c-bio"]
    assert not any(c.is_implicit for c in clusters)


def test_clustered_project_team_merge_keeps_partition(db):
    """Team-signal broadening must not orphan areas outside a project's clusters."""
    from tools.retrieval.models import ProjectProfile

    from apps.content.clustering import cluster_interests

    lab = Lab.objects.create(name="L", slug="l-merge")
    project = Project.objects.create(
        scope_lab=lab,
        name="P",
        goals={
            "interests": {
                "areas": ["graph neural networks"],
                "keywords": ["gnn"],
                "statement": "",
                "clusters": [
                    {
                        "id": "c-ml",
                        "label": "ML",
                        "areas": ["graph neural networks"],
                    }
                ],
            }
        },
    )
    ProjectProfile.objects.create(
        project=project,
        interests={"areas": ["unrelated topic"], "keywords": ["extra"]},
    )
    target = target_for_project(project)
    # Areas stay the declared partition; keywords still broaden.
    assert target.interests["areas"] == ["graph neural networks"]
    assert "extra" in target.interests["keywords"]
    clusters = cluster_interests(target.interests)
    assert [c.id for c in clusters] == ["c-ml"]


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
    embeddings.set_embedder(_fake_embed)
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()

    _seed_grants(
        [
            (
                "grants",
                {
                    "id": "g_match",
                    "title": "graph theory research award",
                    "sponsor": "NSF",
                    "deadline_date": "2026-12-01",
                    "url": "https://example.org/funding_opps/g_match",
                    "matched_topics": "graph",
                },
            )
        ],
        embedder=_fake_embed,
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

    embeddings.set_embedder(_fake_embed)
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    lab.profile.areas = ["graph"]
    lab.profile.save()
    _seed_grants(
        [
            (
                "grants",
                {
                    "id": "g",
                    "title": "graph theory award",
                    "sponsor": "NSF",
                    "deadline_date": "2026-12-01",
                    "url": "https://example.org/funding_opps/g",
                    "matched_topics": "graph",
                },
            )
        ],
        embedder=_fake_embed,
        today="2026-07-05",
    )
    # The daily run scores only items ingested on the run day; stamp created_at to
    # the simulated run date so this new grant is in that day's new-items pool.
    from datetime import UTC, datetime

    ContentItem.objects.filter(type=ContentItem.Type.GRANT).update(
        created_at=datetime(2026, 7, 5, 12, tzinfo=UTC)
    )

    batch = run_daily_opportunities_batch(
        [], labs=[lab], areas=("grants",), prune=False,
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


@pytest.mark.django_db
def test_daily_opportunities_batch_matches_department(pgvector):
    """Parity: a department is matched like a lab, under ``target_department``."""
    from datetime import UTC, datetime

    from apps.accounts.models import Department
    from apps.content.opportunities import run_daily_opportunities_batch

    embeddings.set_embedder(_fake_embed)
    head = User.objects.create_user("head")
    dept = Department.objects.create(owner=head, name="Graph Department")
    dept.profile.areas = ["graph"]
    dept.profile.save()
    _seed_grants(
        [
            (
                "grants",
                {
                    "id": "g",
                    "title": "graph theory award",
                    "sponsor": "NSF",
                    "deadline_date": "2026-12-01",
                    "url": "https://example.org/funding_opps/g",
                    "matched_topics": "graph",
                },
            )
        ],
        embedder=_fake_embed,
        today="2026-07-05",
    )
    ContentItem.objects.filter(type=ContentItem.Type.GRANT).update(
        created_at=datetime(2026, 7, 5, 12, tzinfo=UTC)
    )

    batch = run_daily_opportunities_batch(
        [], departments=[dept], areas=("grants",), prune=False,
        complete=lambda _p: None, today="2026-07-05",
    )

    ok = [r for r in batch.results if r.status == "ok" and r.username == str(dept.pk)]
    assert ok, batch.results
    assert RelevanceScore.objects.filter(
        target_department=dept, content__type="grant"
    ).exists()
