"""Eight weeks of nights over the ambient world (EXP-2026-09-014, Plan 05).

After Plan 04's pipeline has read the four weeks of conversation, this replays
the nights that follow with the clock frozen at each one, answers every
suggestion the way the planted truth says the person would, and checks the
evolving layer's promises every night:

* only what a person said yes to is ever active, and pending, faded or rejected
  understanding never ranks and never reaches collaboration search;
* the declared profile is byte-identical from the first night to the last;
* explorations fade at two half-lives unless the person comes back to them;
  capabilities never fade;
* "forget that" and "delete my observations" remove what they must;
* a private development never reaches a lab reader, and an undone one never
  comes back;
* the context version moves exactly when the picture of the reader does.

Then it measures the exploration themes in ranking (the drift hook) on a
small templated paper corpus: does a confirmed exploration get a slate of its
own topic, and does it leave the declared themes and the global feed alone?

Answers are written with the knowledge core's own ``confirm`` / ``reject`` —
Plan 06's dialogue, which will write them for real, does not exist yet.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from .world import World

INTEREST_PLANTS = {"emerging", "learning"}
NIGHTS = (0, 7, 14, 21, 28, 35, 42, 49, 56)


def _words(text: str) -> set[str]:
    return {
        w
        for w in "".join(c if c.isalnum() else " " for c in text.casefold()).split()
        if len(w) > 2
    }


def _truth(world: World) -> dict[str, dict[str, str]]:
    """``{username: {topic: plant kind}}`` — what each person really said."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for plant in world.plants:
        out[plant.person].setdefault(plant.topic, plant.kind)
    return out


def _wanted(truth: dict[str, str], label: str, relation: str) -> bool:
    """Would the person say yes? Yes to their own emerging interests and
    learning goals (for ``interested_in`` / ``wants_to_learn``) and their real
    capabilities (``can_do``); no to everything else."""
    for topic, kind in truth.items():
        if not (_words(topic) & _words(label)):
            continue
        if relation == "can_do":
            return kind == "capability"
        return kind in INTEREST_PLANTS
    return False


def _profiles_digest(users) -> dict[int, str]:
    from apps.accounts.models import Profile

    return {
        p.user_id: hashlib.sha256(
            json.dumps(p.interests, sort_keys=True).encode()
        ).hexdigest()
        for p in Profile.objects.filter(user__in=users)
    }


class Checks:
    """Invariant violations, by name, accumulated over every night."""

    def __init__(self) -> None:
        self.violations: Counter = Counter()
        self.examples: dict[str, list] = defaultdict(list)

    def fail(self, name: str, example) -> None:
        self.violations[name] += 1
        if len(self.examples[name]) < 5:
            self.examples[name].append(example)


def _night(t) -> dict:
    from apps.ambient import deliberate, evolve

    with mock.patch("django.utils.timezone.now", return_value=t):
        decided = deliberate.deliberate(now=t).as_dict()
        evolved = evolve.evolve(now=t).as_dict()
    return {"deliberate": decided, "evolve": evolved}


def _mine():
    """This experiment's people only. The sandbox template also holds the
    collaboration world, whose planted conversational edges are not ours
    (EXP-2026-09-014 run 2)."""
    from apps.knowledge.models import Edge

    return Edge.objects.filter(user__username__startswith="amb_")


def simulate(world: World, *, seed: int = 20260919) -> dict:
    from django.contrib.auth import get_user_model

    from apps.ambient import reconcile
    from apps.ambient.evolve import undo_development
    from apps.ambient.models import Finding, Observation, ProjectDevelopment, Visibility
    from apps.ambient.read import developments_in_effect
    from apps.content.understanding import context_version
    from apps.knowledge.models import EdgeStatus
    from apps.knowledge.read import (
        confirmed_explorations,
        discoverable_edges,
        ranking_edges,
    )
    from apps.knowledge.service import confirm, reject
    from apps.research.models import Project

    rng = random.Random(seed)
    User = get_user_model()
    users = {u.username: u for u in User.objects.filter(username__startswith="amb_")}
    speakers = [u for name, u in users.items() if world.person(name).opted_in]
    truth = _truth(world)
    digests = _profiles_digest(users.values())
    checks = Checks()
    now0 = timezone.now()
    said_yes: set[tuple[int, int, str]] = set()
    said_no: set[tuple[int, int, str]] = set()
    reinforce: set[tuple[int, int]] = set()
    forgotten: set[int] = set()
    undone: set[int] = set()
    versions: dict[int, str] = {}
    version_moves: Counter = Counter()
    log = []
    answered = Counter()

    for k in NIGHTS:
        t = now0 + timedelta(days=k)
        entry = {"night": k, **_night(t)}

        # -- answers, the morning after the night that raised them ------------------
        with mock.patch("django.utils.timezone.now", return_value=t):
            for edge in (
                _mine()
                .filter(
                    tier="conversational", status=EdgeStatus.PENDING, user__in=speakers
                )
                .select_related("user", "concept")
            ):
                key = (edge.user_id, edge.concept_id, edge.relation)
                if key in said_yes or key in said_no:
                    continue
                if _wanted(
                    truth[edge.user.username],
                    edge.surface or edge.concept.label,
                    edge.relation,
                ):
                    review = (
                        (t + timedelta(days=30)).date()
                        if edge.qualifier == "current_curiosity"
                        else None
                    )
                    confirm(edge.user, edge.concept_id, edge.relation, review_on=review)
                    said_yes.add(key)
                    answered["yes"] += 1
                    # Half the people keep coming back to what they confirmed.
                    if edge.qualifier == "current_curiosity" and rng.random() < 0.5:
                        reinforce.add((edge.user_id, edge.concept_id))
                else:
                    reject(edge.user, edge.concept_id, edge.relation)
                    said_no.add(key)
                    answered["no"] += 1

        # -- events -------------------------------------------------------------------
        if k == 7:
            # Undo one told development per lab.
            for lab in world.labs:
                row = ProjectDevelopment.objects.filter(
                    project__scope_lab__slug=lab.slug,
                    status=ProjectDevelopment.Status.ACTIVE,
                ).first()
                if row is not None:
                    undo_development(row, by=row.speaker)
                    undone.add(row.pk)
        if k == 14:
            # One person per lab opts out with deletion; another forgets one thing.
            for lab in world.labs:
                people = [p for p in lab.people if p.opted_in]
                gone = users[people[1].username]
                with mock.patch("django.utils.timezone.now", return_value=t):
                    reconcile.forget_person(gone)
                forgotten.add(gone.pk)
                other = users[people[2].username]
                one = Observation.objects.filter(speaker=other).first()
                if one is not None:
                    with mock.patch("django.utils.timezone.now", return_value=t):
                        reconcile.forget_observations(other, [one.pk])
        if k in (21, 35):
            # The people who keep coming back to an exploration say so again.
            for user_id, concept_id in sorted(reinforce):
                if user_id in forgotten:
                    continue
                original = Observation.objects.filter(
                    speaker_id=user_id, concept_id=concept_id
                ).first()
                if original is None:
                    continue
                for offset, key in ((1, "a"), (6, "b")):
                    Observation.objects.create(
                        source=original.source,
                        external_message_ids=[f"sim-{k}-{user_id}-{concept_id}-{key}"],
                        observed_at=t - timedelta(days=offset),
                        speaker_id=user_id,
                        text="Said again that they want to keep exploring this.",
                        subject="self",
                        understanding_kind="current_curiosity",
                        force="preference",
                        place_kind=original.place_kind,
                        place_label=original.place_label,
                        visibility=Visibility.PERSONAL,
                        facet=original.facet,
                        topic=original.topic,
                        concept_id=concept_id,
                        conversation_key=f"sim-{k}-{key}",
                    )

        # -- invariants -----------------------------------------------------------------  # noqa: E501
        for edge in _mine().filter(tier="conversational", status=EdgeStatus.ACTIVE):
            if (edge.user_id, edge.concept_id, edge.relation) not in said_yes:
                checks.fail("active_without_yes", edge.pk)
        for key in said_no:
            if (
                _mine()
                .filter(
                    user_id=key[0],
                    concept_id=key[1],
                    relation=key[2],
                    tier="conversational",
                )
                .exclude(status=EdgeStatus.REJECTED)
                .exists()
            ):
                checks.fail("no_not_kept", key)
        if _profiles_digest(users.values()) != digests:
            checks.fail("declared_profile_changed", k)
        for user in speakers:
            for edge in confirmed_explorations(user):
                if edge.status != "active":
                    checks.fail("exploration_not_active", edge.concept_id)
            for edge in ranking_edges(user):
                if edge.tier == "conversational" and edge.status != "active":
                    checks.fail("pending_ranks", edge.concept_id)
        for edge in discoverable_edges(users.values()):
            if edge.tier == "conversational":
                checks.fail("conversation_discoverable", edge.concept_id)
        for user_id in forgotten:
            if _mine().filter(user_id=user_id, tier="conversational").exists():
                checks.fail("forgotten_edges_remain", user_id)
            if Finding.objects.filter(user_id=user_id).exists():
                checks.fail("forgotten_findings_remain", user_id)
        live_ids = set(Observation.objects.values_list("pk", flat=True))
        for edge in _mine().filter(tier="conversational"):
            for item in edge.evidence or []:
                if item.startswith("obs:") and int(item[4:]) not in live_ids:
                    checks.fail("evidence_of_deleted", edge.pk)
        for row in ProjectDevelopment.objects.all():
            if row.pk in undone and row.status != ProjectDevelopment.Status.REJECTED:
                checks.fail("undone_came_back", row.pk)
            if row.visibility == Visibility.LAB:
                private = Observation.objects.filter(
                    pk__in=row.observation_ids
                ).exclude(visibility=Visibility.LAB)
                if private.exists():
                    checks.fail("lab_development_on_private", row.pk)
        for project in Project.objects.filter(scope_lab__slug__startswith="amb-"):
            for row in developments_in_effect(project):
                if row.visibility != Visibility.LAB:
                    checks.fail("private_development_to_lab", row.pk)
        # Fading: two half-lives (42 days) without reinforcement.
        for edge in _mine().filter(
            tier="conversational", qualifier="current_curiosity"
        ):
            age = (t - edge.last_reinforced).days
            if edge.status == EdgeStatus.ACTIVE and age > 42:
                checks.fail("should_have_faded", edge.pk)
            if (
                edge.status == EdgeStatus.FADED
                and (edge.user_id, edge.concept_id) in reinforce
                and age <= 42
            ):
                checks.fail("faded_while_reinforced", edge.pk)
        if (
            _mine()
            .filter(
                tier="conversational", qualifier="capability", status=EdgeStatus.FADED
            )
            .exists()
        ):
            checks.fail("capability_faded", k)
        # How often each person's context version moved (reported, not a
        # check: the unit tests pin exactly when it must move).
        with mock.patch("django.utils.timezone.now", return_value=t):
            for user in speakers:
                projects = list(Project.objects.filter(members=user))
                version = context_version(user, None, projects)
                if user.pk in versions and versions[user.pk] != version:
                    version_moves[user.pk] += 1
                versions[user.pk] = version

        entry["edges"] = dict(
            Counter(
                _mine().filter(tier="conversational").values_list("status", flat=True)
            )
        )
        entry["developments"] = dict(
            Counter(ProjectDevelopment.objects.values_list("status", flat=True))
        )
        log.append(entry)

    faded = _mine().filter(tier="conversational", status=EdgeStatus.FADED)
    reinforced_active = sum(
        1
        for user_id, concept_id in reinforce
        if _mine()
        .filter(user_id=user_id, concept_id=concept_id, status=EdgeStatus.ACTIVE)
        .exists()
    )
    return {
        "nights": log,
        "answered": dict(answered),
        "said_yes": len(said_yes),
        "said_no": len(said_no),
        "reinforced_topics": len(reinforce),
        "reinforced_still_active": reinforced_active,
        "faded": faded.count(),
        "forgotten_people": len(forgotten),
        "undone_developments": len(undone),
        "context_version_moves": sum(version_moves.values()),
        "violations": dict(checks.violations),
        "violation_examples": {
            k: [str(x) for x in v] for k, v in checks.examples.items()
        },
        "violations_total": sum(checks.violations.values()),
    }


# -- the drift hook, on a templated corpus ------------------------------------------------  # noqa: E501

_SETTINGS = (
    "clinical cohorts",
    "satellite imagery",
    "field recordings",
    "survey panels",
)
_FRAMES = (
    "A study of {t} applied to {s}, with a reproducible pipeline and an ablation.",
    "We revisit {t} for {s} and report where it fails.",
    "Scaling {t}: lessons from {s}.",
    "{T} meets {s}: a benchmark and baselines.",
)


def seed_corpus(topics: list[str]) -> int:
    from apps.content.embeddings import embed_texts
    from apps.content.models import ContentItem

    ContentItem.objects.filter(source="sandbox-ambient").delete()
    rows = []
    for topic in topics:
        for i, frame in enumerate(_FRAMES):
            abstract = frame.format(t=topic, T=topic.capitalize(), s=_SETTINGS[i])
            rows.append((topic, i, f"{topic.capitalize()} — study {i + 1}", abstract))
    vectors = (
        embed_texts([f"{title}. {abstract}" for _, _, title, abstract in rows]) or []
    )
    items = [
        ContentItem(
            type=ContentItem.Type.PAPER,
            source="sandbox-ambient",
            external_id=f"{topic}-{i}",
            metadata={"title": title, "abstract": abstract, "sandbox_topic": topic},
            embedding=vector,
        )
        for (topic, i, title, abstract), vector in zip(rows, vectors, strict=False)
    ]
    ContentItem.objects.bulk_create(items, batch_size=500)
    return len(items)


def drift(world: World, weights=(0.15, 1.0)) -> dict:
    """Declared-only against declared-plus-explorations, per person with one."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.content import explorations
    from apps.content.clustering import cluster_interests
    from apps.content.interests_query import search_interests
    from apps.content.models import ContentItem
    from apps.content.pipeline import (
        DEFAULT_BETA,
        DEFAULT_POOL_PER_INTEREST,
        fuse_clusters_pool,
    )
    from apps.content.retrieval import latest_gather_date
    from apps.content.slates import slate_depth

    created_on = latest_gather_date(content_type=ContentItem.Type.PAPER)
    depth = slate_depth(ContentItem.Type.PAPER)

    def run(interests, cluster_weights=None):
        clusters = cluster_interests(interests)
        search = search_interests(interests, clusters=clusters)
        pairs, _rows, _n, slates = fuse_clusters_pool(
            search,
            clusters,
            content_type=ContentItem.Type.PAPER,
            surface_limit=25,
            pool_per_interest=DEFAULT_POOL_PER_INTEREST,
            beta=DEFAULT_BETA,
            emit=lambda _m: None,
            created_on=created_on,
            match_threshold=None,
            cluster_top_n=depth,
            cluster_weights=cluster_weights,
        )
        order = sorted(pairs, key=lambda pair: -pair[1])
        top = [str(item.id) for item, _ in order[:25]]
        return (
            clusters,
            top,
            {cid: [str(hit[0].id) for hit in hits] for cid, hits in slates.items()},
        )

    topic_of = {
        str(pk): meta.get("sandbox_topic")
        for pk, meta in ContentItem.objects.filter(
            source="sandbox-ambient"
        ).values_list("id", "metadata")
    }
    User = get_user_model()
    out: dict[str, dict] = {}
    settings.AMBIENT_DRIFT_ENABLED = True
    for weight in weights:
        settings.AMBIENT_DRIFT_WEIGHT = weight
        jaccards, precisions, displaced, people = [], [], [], 0
        # Post hoc (EXP-2026-09-014 run 2): the corpus holds four papers per
        # topic, so "share of a 25-deep slate on the topic" is capped near
        # 0.16. This asks the answerable question: of the topic's own papers,
        # how many lead its exploration slate?
        own_at_top = []
        for user in User.objects.filter(username__startswith="amb_"):
            found = explorations.for_user(user)
            if not found:
                continue
            people += 1
            declared = user.profile.interests
            clusters_off, top_off, slates_off = run(declared)
            augmented, cw = explorations.with_explorations(declared, found)
            _clusters_on, top_on, slates_on = run(augmented, cw)
            for cluster in clusters_off:
                a, b = (
                    set(slates_off.get(cluster.id, [])),
                    set(slates_on.get(cluster.id, [])),
                )
                if a or b:
                    jaccards.append(len(a & b) / len(a | b))
            for concept_id, label in found:
                slate = slates_on.get(f"{explorations.EXPLORE_PREFIX}{concept_id}", [])
                own = [
                    cid
                    for cid, topic in topic_of.items()
                    if (topic or "").casefold() == label.casefold()
                ]
                if slate and own:
                    top = slate[: len(own)]
                    own_at_top.append(len(set(top) & set(own)) / len(own))
                if slate:
                    precisions.append(
                        sum(
                            1
                            for cid in slate
                            if topic_of.get(cid, "").casefold() == label.casefold()
                        )
                        / len(slate)
                    )
            declared_top = [cid for cid in top_off]
            displaced.append(len(set(declared_top) - set(top_on)))
        out[str(weight)] = {
            "people": people,
            "declared_slate_jaccard_mean": round(sum(jaccards) / len(jaccards), 4)
            if jaccards
            else None,
            "declared_slate_jaccard_min": round(min(jaccards), 4) if jaccards else None,
            "exploration_slate_precision_mean": round(
                sum(precisions) / len(precisions), 4
            )
            if precisions
            else None,
            "exploration_slates": len(precisions),
            "exploration_own_papers_at_top_mean": (
                round(sum(own_at_top) / len(own_at_top), 4) if own_at_top else None
            ),
            "declared_displaced_from_top25_mean": round(
                sum(displaced) / len(displaced), 4
            )
            if displaced
            else None,
            "declared_displaced_from_top25_max": max(displaced) if displaced else None,
        }
    settings.AMBIENT_DRIFT_ENABLED = False
    return out
