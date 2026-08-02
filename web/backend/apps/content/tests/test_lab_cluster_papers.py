"""A lab's papers are chosen per research theme, not by one global ranking.

The reported symptom was a lab whose Research Papers page held seven articles,
numbered ``1 → 2 → 11 → 12``, while its grants and conferences ran into the
hundreds. Two causes, both fixed here and in ``test_pipeline``:

* the model only ever saw the global top slice, so a lab's strongest theme took
  the entire budget and the others surfaced nothing explained;
* the papers it *did* judge harshly were withheld while the papers it never saw
  were not — leaving a feed that was mostly unexplained and full of gaps.

Ranking within each cluster is scale-free, which is what a lab needs: its areas
are broad theme names, so absolute scores are not comparable across themes.
"""

from __future__ import annotations

import json
import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import Lab
from apps.content import embeddings
from apps.content.fusion import ClusteredHit, top_per_cluster
from apps.content.models import ContentItem, RelevanceScore
from apps.content.pipeline import recommend_for_lab, recommend_for_user

_TOKENS = ["ocean", "health", "climate", "other"]


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


@pytest.fixture(autouse=True)
def _feed_settings(settings):
    """Isolate from production tuning; each test states what it exercises."""
    settings.PAPER_MATCH_THRESHOLD = 0.0
    settings.PAPER_MIN_MATCH_PERCENT = 0
    settings.PAPER_CLUSTER_TOP_N = 10


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the lab retrieval path needs PostgreSQL + pgvector")


# --------------------------------------------------------------------------- #
# Pure: the selection itself
# --------------------------------------------------------------------------- #
def _hit(name: str, per_cluster: dict[str, float]) -> ClusteredHit:
    best = max(per_cluster, key=lambda cid: per_cluster[cid])
    return ClusteredHit(
        item=ContentItem(external_id=name, metadata={"title": name}),
        final_score=per_cluster[best],
        cluster_id=best,
        per_cluster=per_cluster,
        per_interest={},
        bridge_cluster_ids=[],
        n_matched=1,
    )


def test_each_cluster_ranks_by_its_own_score() -> None:
    """The point of the change: a weaker theme still gets its own best first.

    ``a`` beats ``b`` globally, but within ``c-two`` the order reverses — which is
    exactly the case a global ranking cannot express.
    """
    a = _hit("a", {"c-one": 0.9, "c-two": 0.1})
    b = _hit("b", {"c-one": 0.2, "c-two": 0.8})

    picked = top_per_cluster([a, b], limit=1)

    assert picked["c-one"] == [a]
    assert picked["c-two"] == [b]


def test_a_quiet_cluster_is_not_crowded_out() -> None:
    """A theme whose absolute scores all run low still contributes its share."""
    loud = [_hit(f"loud{n}", {"c-loud": 0.9 - n / 100}) for n in range(20)]
    quiet = [_hit(f"quiet{n}", {"c-quiet": 0.2 - n / 100}) for n in range(5)]

    picked = top_per_cluster(loud + quiet, limit=10)

    assert len(picked["c-loud"]) == 10
    assert len(picked["c-quiet"]) == 5  # everything it has, not nothing
    assert [h.item.external_id for h in picked["c-quiet"]][0] == "quiet0"


def test_no_slate_is_requested_when_the_limit_is_zero() -> None:
    assert top_per_cluster([_hit("a", {"c-one": 0.5})], limit=0) == {}


# --------------------------------------------------------------------------- #
# The lab feed end to end
# --------------------------------------------------------------------------- #
def _lab_with_two_themes(slug: str = "pulse") -> Lab:
    lab = Lab.objects.create(name="Pulse Lab", slug=slug)
    lab.profile.interests = {
        "areas": ["ocean", "health"],
        "keywords": [],
        "statement": "",
        "clusters": [
            {"id": "c-ocean", "label": "AI for Oceanography", "areas": ["ocean"]},
            {"id": "c-health", "label": "AI in Health Sciences", "areas": ["health"]},
        ],
    }
    lab.profile.areas = ["ocean", "health"]
    lab.profile.save()
    return lab


def _vpaper(source: str, title: str, vector: list[float]) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=vector,
        metadata={"title": title, "abstract": title},
    )


def _score_everything(match: int):
    """A model that gives every candidate the same verdict."""

    def complete(prompt: str) -> str:
        rows = [
            {"paper": int(line[1 : line.index("]")]), "match": match, "reason": "Yes."}
            for line in prompt.splitlines()
            if line.startswith("[")
        ]
        return json.dumps({"suggestions": rows})

    return complete


@pytest.mark.django_db
def test_every_theme_reaches_the_model(pgvector) -> None:
    """One call per theme, and both themes are represented in what Mylo read."""
    embeddings.set_embedder(_fake_embed)
    for n in range(6):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.1 * n])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.1 * n])
    lab = _lab_with_two_themes()

    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return _score_everything(80)(prompt)

    result = recommend_for_lab(lab, complete=complete)

    assert result.status == "ok"
    # One prompt per theme — not one global prompt covering whichever theme won.
    assert len(prompts) == 2
    assert any("ocean study" in p for p in prompts)
    assert any("health study" in p for p in prompts)
    # Every paper carries Mylo's verdict; none is left unexplained.
    scores = RelevanceScore.objects.filter(target_lab=lab)
    assert scores.count() == 12
    assert all(s.signals["source"] == "llm" for s in scores)


@pytest.mark.django_db
def test_a_themes_best_papers_are_shown_even_when_mylo_is_lukewarm(
    pgvector, settings
) -> None:
    """The behaviour that turns seven papers into a full feed.

    Sending more papers to the model only helps if the model's verdict stops
    deciding membership. A paper the run chose as one of a theme's best is shown
    with whatever percent it earned.
    """
    settings.PAPER_MIN_MATCH_PERCENT = 60
    embeddings.set_embedder(_fake_embed)
    for n in range(4):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.1 * n])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.1 * n])
    lab = _lab_with_two_themes()

    result = recommend_for_lab(lab, complete=_score_everything(25))

    assert result.status == "ok"
    shown = [
        s
        for s in RelevanceScore.objects.filter(target_lab=lab)
        if s.signals["suggested"]
    ]
    assert len(shown) == 8
    assert {s.signals["match_percent"] for s in shown} == {25}
    # And the numbering describes the list, with no gaps.
    assert sorted(s.signals["rank"] for s in shown) == list(range(1, 9))


@pytest.mark.django_db
def test_a_paper_outside_the_slate_still_obeys_the_floor(pgvector, settings) -> None:
    """The floor is not abolished — it just stops overruling a deliberate pick."""
    settings.PAPER_MIN_MATCH_PERCENT = 60
    settings.PAPER_CLUSTER_TOP_N = 1
    embeddings.set_embedder(_fake_embed)
    _vpaper("o-best", "ocean study best", [1.0, 0.0, 0.0, 0.0])
    _vpaper("o-rest", "ocean study rest", [0.9, 0.0, 0.0, 0.4])
    _vpaper("h-best", "health study best", [0.0, 1.0, 0.0, 0.0])
    lab = _lab_with_two_themes()

    def complete(prompt: str) -> str:
        rows = []
        for line in prompt.splitlines():
            if not line.startswith("["):
                continue
            idx = int(line[1 : line.index("]")])
            rows.append({"paper": idx, "match": 20, "reason": "Weak."})
        return json.dumps({"suggestions": rows})

    recommend_for_lab(lab, complete=complete)

    by_source = {
        s.content.external_id: s.signals
        for s in RelevanceScore.objects.filter(target_lab=lab).select_related("content")
    }
    # Each theme's single best pick survives its 20% verdict...
    assert by_source["o-best"]["suggested"] is True
    assert by_source["h-best"]["suggested"] is True
    # ...while the runner-up, which the model never judged, keeps the old rule.
    assert by_source["o-rest"]["source"] == "fallback"
    assert by_source["o-rest"]["suggested"] is True


@pytest.mark.django_db
def test_a_single_theme_lab_is_unchanged(pgvector) -> None:
    """One cluster means no cross-theme problem to solve — the flat path stands."""
    embeddings.set_embedder(_fake_embed)
    for n in range(20):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.0])
    lab = Lab.objects.create(name="One Theme", slug="one-theme")
    lab.profile.areas = ["ocean"]
    lab.profile.save()

    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return _score_everything(80)(prompt)

    recommend_for_lab(lab, complete=complete)

    # A single global call of ten, and the unscored tail still surfaces unexplained.
    assert len(prompts) == 1
    sources = [
        s.signals["source"] for s in RelevanceScore.objects.filter(target_lab=lab)
    ]
    assert sources.count("llm") == 10
    assert sources.count("fallback") >= 1


@pytest.mark.django_db
def test_a_persons_feed_is_untouched(pgvector) -> None:
    """The slate is an institutional answer to an institutional problem."""
    from apps.accounts.models import WatchPreference

    embeddings.set_embedder(_fake_embed)
    for n in range(12):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.0])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.0])
    user = User.objects.create_user("solo", password="x")
    user.profile.interests = {
        "areas": ["ocean", "health"],
        "keywords": [],
        "clusters": [
            {"id": "c-ocean", "label": "Ocean", "areas": ["ocean"]},
            {"id": "c-health", "label": "Health", "areas": ["health"]},
        ],
    }
    user.profile.save()
    WatchPreference.objects.update_or_create(user=user, defaults={"topics": ["ocean"]})

    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return _score_everything(80)(prompt)

    recommend_for_user(user, complete=complete)

    # One global call of ten, exactly as before; the rest stay the unscored tail.
    assert len(prompts) == 1
    sources = [
        s.signals["source"] for s in RelevanceScore.objects.filter(target_user=user)
    ]
    assert sources.count("llm") == 10
