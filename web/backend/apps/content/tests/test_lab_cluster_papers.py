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
from tools.retrieval import embeddings
from tools.retrieval.models import ContentItem, RelevanceScore

from apps.accounts.models import Lab
from apps.content.fusion import ClusteredHit, top_per_cluster
from apps.content.pipeline import recommend_for_lab, recommend_for_user
from apps.content.tests.entitle import entitle_lab, entitle_user

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


def _mylo(verdict: str = "read", caveat: str = "Preliminary."):
    """A model that answers both stages: the précis first, then the fit verdict.

    One injected seam serves both prompts because that is how the pipeline calls
    it. The prompts are told apart by their opening line rather than by a flag —
    a test double that has to be told which stage it is in stops proving the
    stages are wired to the same client.
    """

    def complete(prompt: str) -> str:
        if prompt.startswith("Title:"):
            return json.dumps(
                {
                    "problem": "A problem.",
                    "method": "A method.",
                    "setting": "A cohort.",
                    "claim": "A claim.",
                    "limitations": "Small sample.",
                    "reusable": "A baseline.",
                    "thin": False,
                }
            )
        rows = [
            {
                "n": int(line[1 : line.index("]")]),
                "verdict": verdict,
                "matters": "It speaks to this strand.",
                "use": "Use it as a baseline.",
                "take": "Take Table 2.",
                "caveat": caveat,
            }
            for line in prompt.splitlines()
            if line.startswith("[")
        ]
        return json.dumps({"items": rows})

    return complete


def _fit_prompts(prompts: list[str]) -> list[str]:
    """Only the per-theme fit prompts — the comprehension calls are stage one."""
    return [p for p in prompts if not p.startswith("Title:")]


@pytest.mark.django_db
def test_every_theme_reaches_the_model(pgvector) -> None:
    """One fit call per theme, and both themes are represented in what Mylo read."""
    embeddings.set_embedder(_fake_embed)
    for n in range(6):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.1 * n])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.1 * n])
    lab = _lab_with_two_themes()
    entitle_lab(lab)

    prompts: list[str] = []
    answer = _mylo()

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return answer(prompt)

    result = recommend_for_lab(lab, complete=complete)

    assert result.status == "ok"
    fits = _fit_prompts(prompts)
    # One prompt per theme — not one global prompt covering whichever theme won.
    assert len(fits) == 2
    assert any("AI for Oceanography" in p for p in fits)
    assert any("AI in Health Sciences" in p for p in fits)
    # Every paper carries Mylo's verdict; none is left unexplained.
    scores = RelevanceScore.objects.filter(target_lab=lab)
    assert scores.count() == 12
    assert all(s.signals["source"] == "llm" for s in scores)
    assert all(s.signals["verdict"] in {"read", "skim", "file", "skip"} for s in scores)


@pytest.mark.django_db
def test_each_theme_keeps_its_own_slate_and_positions(pgvector) -> None:
    """No global list: every theme's slate is numbered from one, in its own order."""
    embeddings.set_embedder(_fake_embed)
    for n in range(4):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.1 * n])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.1 * n])
    lab = _lab_with_two_themes()

    recommend_for_lab(lab, complete=lambda _p: None)

    slates: dict[str, set[int]] = {}
    for score in RelevanceScore.objects.filter(target_lab=lab):
        for cluster_id, entry in (score.signals.get("cluster_slates") or {}).items():
            slates.setdefault(cluster_id, set()).add(entry["rank"])
    assert set(slates) == {"c-ocean", "c-health"}
    # Each theme numbers from 1 — a niche theme's best is first *of its theme*.
    for ranks in slates.values():
        assert min(ranks) == 1


@pytest.mark.django_db
def test_a_lukewarm_verdict_never_removes_a_paper(pgvector) -> None:
    """A theme's best is shown whatever Mylo thinks of it.

    The percent floor that used to withhold papers is gone: an item the run chose
    as one of a theme's best is in the slate, and a poor verdict demotes it in the
    document rather than deleting it from the feed.
    """
    embeddings.set_embedder(_fake_embed)
    for n in range(4):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.1 * n])
        _vpaper(f"h{n}", f"health study {n}", [0.0, 1.0, 0.0, 0.1 * n])
    lab = _lab_with_two_themes()
    entitle_lab(lab)

    result = recommend_for_lab(lab, complete=_mylo("skip"))

    assert result.status == "ok"
    shown = [
        s
        for s in RelevanceScore.objects.filter(target_lab=lab)
        if s.signals["suggested"]
    ]
    assert len(shown) == 8
    assert {s.signals["verdict"] for s in shown} == {"skip"}
    # No percent survives anywhere.
    assert {s.signals["match_percent"] for s in shown} == {None}
    # And the numbering describes the list, with no gaps.
    assert sorted(s.signals["rank"] for s in shown) == list(range(1, 9))


@pytest.mark.django_db
def test_a_single_theme_lab_keeps_one_slate(pgvector) -> None:
    """One cluster means one slate — the same items, in the same order, as before."""
    embeddings.set_embedder(_fake_embed)
    for n in range(20):
        _vpaper(f"o{n}", f"ocean study {n}", [1.0, 0.0, 0.0, 0.0])
    lab = Lab.objects.create(name="One Theme", slug="one-theme")
    lab.profile.areas = ["ocean"]
    lab.profile.save()

    recommend_for_lab(lab, complete=lambda _p: None)

    rows = list(RelevanceScore.objects.filter(target_lab=lab))
    # The per-interest RRF floor drops the weakest of the twenty; what matters is
    # that one theme yields exactly one slate, not how deep the pool went.
    assert 15 <= len(rows) <= 20
    # A lone implicit cluster carries no attribution — no phantom badge appears.
    assert all("cluster_id" not in r.signals for r in rows)
    slate_ids = {
        cid
        for r in rows
        for cid in (r.signals.get("cluster_slates") or {})
    }
    assert slate_ids == {"c-all"}


@pytest.mark.django_db
def test_a_person_also_gets_per_theme_slates(pgvector) -> None:
    """The redesign is not institution-only: a person's themes each get a slate."""
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
    entitle_user(user)

    prompts: list[str] = []
    answer = _mylo()

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return answer(prompt)

    recommend_for_user(user, complete=complete)

    fits = _fit_prompts(prompts)
    # Each prompt is about exactly one strand, and both strands are covered. The
    # count is a batching detail; the invariant is that no prompt mixes themes.
    assert fits
    named = {
        line.split(": ", 1)[1]
        for prompt in fits
        for line in prompt.splitlines()
        if line.startswith("The strand you are judging for: ")
    }
    assert named == {"Ocean", "Health"}
    slates: dict[str, set[str]] = {}
    for score in RelevanceScore.objects.filter(target_user=user):
        for cluster_id in score.signals.get("cluster_slates") or {}:
            slates.setdefault(cluster_id, set()).add(str(score.content_id))
    assert set(slates) == {"c-ocean", "c-health"}
