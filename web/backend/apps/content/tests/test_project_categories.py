"""Per-project recommendation-category customization (goals.watch_categories)."""

import pytest
from tools.recommendation.targets import project_watch_categories

from apps.accounts.models import Lab
from apps.research.models import Project


@pytest.mark.django_db
def test_default_categories_are_all_four() -> None:
    project = Project.objects.create(scope_user=None, scope_lab=_lab(), name="P")
    assert project_watch_categories(project) == [
        "papers",
        "grants",
        "fellowships",
        "conferences",
    ]


@pytest.mark.django_db
def test_stored_categories_are_honoured_and_ordered() -> None:
    project = Project.objects.create(
        scope_lab=_lab(),
        name="P",
        goals={"watch_categories": ["conferences", "papers"]},
    )
    # Stable report order, unknowns dropped.
    assert project_watch_categories(project) == ["papers", "conferences"]


@pytest.mark.django_db
def test_refit_project_narrows_areas_to_categories(monkeypatch) -> None:
    """refit_project only runs the opted-in areas."""
    from tools.recommendation import refitting

    project = Project.objects.create(
        scope_lab=_lab(),
        name="P",
        goals={
            "interests": {"areas": ["x"], "keywords": [], "statement": ""},
            "watch_categories": ["papers", "grants"],
        },
    )

    seen_areas = {}

    def fake_refit_target(target, *, areas, **kwargs):
        seen_areas["areas"] = tuple(areas)
        return refitting.RefitResult(target.key, "ok")

    monkeypatch.setattr(refitting, "refit_target", fake_refit_target)
    refitting.refit_project(project)
    # fellowships + conferences dropped; papers + grants kept in report order.
    assert seen_areas["areas"] == ("papers", "grants")


def _lab() -> Lab:
    return Lab.objects.create(name="L", slug=f"l-{Lab.objects.count()}")
