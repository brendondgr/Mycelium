"""Score the graph built from the synthetic world against what was planted.

Every number here is a comparison with known truth, not a judgement: which
method each paper really used, which ideas each person declared, what each
project needs that nobody on it covers. Invariants — things that must be zero —
are reported beside the rates, and :func:`failures` lists every invariant that
was not.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.contrib.auth import get_user_model

from apps.accounts.models import AuthorWork
from apps.knowledge import read
from apps.knowledge.linker import normalise
from apps.knowledge.models import (
    Concept,
    Edge,
    EdgeStatus,
    Relation,
    Scope,
    Tier,
)
from apps.knowledge.works import EMPTY_ABSTRACTIONS
from apps.research.models import Project

from . import world as world_mod

INVARIANTS = (
    "conversational_edges",
    "private_concepts_from_papers",
    "thin_works_with_edges",
    "rollup_evidence_from_someone_elses_work",
    "neutral_phrases_in_deny_list",
    "second_pass_model_calls",
    "second_pass_works_read",
    "second_projection_writes",
)


def _signature_methods(text: str) -> set[str]:
    lowered = f" {text.lower()} "
    return {m.key for m in world_mod.METHODS if any(s in lowered for s in m.signature)}


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def score_cn02(world: world_mod.World, corpus: dict[str, dict], run: dict) -> dict:
    papers = {p.key: p for p in world.papers}
    people = {p.key: p for p in world.people}
    works = {
        work.source_id.removeprefix("SB-"): work
        for work in AuthorWork.objects.select_related("facets", "user")
    }
    facets = {key: getattr(work, "facets", None) for key, work in works.items()}

    # --- extraction -------------------------------------------------------
    read_rows = [row for row in facets.values() if row is not None]
    clean = [
        key
        for key, paper in papers.items()
        if not (corpus.get(key) or {}).get("problems")
        and corpus.get(key, {}).get("abstract")
    ]
    non_thin = [key for key in clean if facets.get(key) and not facets[key].thin]
    refused_by_facet = Counter()
    for row in read_rows:
        for failure in row.refused or []:
            refused_by_facet[failure.split(":", 1)[0]] += 1
    neutral_present = sum(1 for key in non_thin if facets[key].method_neutral)
    deny_violations = sum(
        1 for row in read_rows if normalise(row.method_neutral) in EMPTY_ABSTRACTIONS
    )

    # --- method linking against the planted truth -------------------------
    method_edges = defaultdict(list)  # paper key -> [(surface, concept id)]
    for edge in Edge.objects.filter(
        author_work__isnull=False,
        tier=Tier.DEMONSTRATED,
        relation=Relation.USES_METHOD,
    ).select_related("author_work"):
        key = edge.author_work.source_id.removeprefix("SB-")
        method_edges[key].append((edge.surface, edge.concept_id))

    recalled = 0
    contaminated = 0
    concepts_by_method: dict[str, Counter] = defaultdict(Counter)
    methods_by_concept: dict[int, set[str]] = defaultdict(set)
    surfaces_by_concept: dict[int, set[str]] = defaultdict(set)
    for key in non_thin:
        planted = papers[key].method
        hit = False
        for surface, concept_id in method_edges.get(key, []):
            named = _signature_methods(surface)
            if planted in named:
                hit = True
                concepts_by_method[planted][concept_id] += 1
            if named - {planted}:
                contaminated += 1
            for m in named:
                methods_by_concept[concept_id].add(m)
            surfaces_by_concept[concept_id].add(surface)
        recalled += int(hit)

    splits = {
        m: len(counter) - 1
        for m, counter in concepts_by_method.items()
        if len(counter) > 1
    }
    wrong_merges = {
        concept_id: sorted(methods)
        for concept_id, methods in methods_by_concept.items()
        if len(methods) > 1
    }

    # --- the field ruler --------------------------------------------------
    field_checks = field_right = 0
    for m, counter in concepts_by_method.items():
        canonical = counter.most_common(1)[0][0]
        fields_seen = {
            world_mod.FIELDS[
                [k for k, _, _ in world_mod.FIELDS].index(papers[key].field)
            ][1]
            for key in non_thin
            if papers[key].method == m
            and any(c == canonical for _, c in method_edges.get(key, []))
        }
        expected = next(iter(fields_seen)) if len(fields_seen) == 1 else ""
        actual = Concept.objects.get(pk=canonical).openalex_field_id
        field_checks += 1
        field_right += int(actual == expected)

    # --- Q2 against the planted profile -----------------------------------
    both = both_total = declared_only = declared_only_total = 0
    undeclared_shown = undeclared_total = 0
    for person_key, person in people.items():
        user = User.objects.filter(username=person_key).first()
        if user is None:
            continue
        rows = read.backing(user)
        for method_key in person.methods[:2]:  # the ones they declare
            both_total += 1
            both += int(
                any(
                    row.declared
                    and row.demonstrated
                    and method_key in _signature_methods(f"{row.surface} {row.label}")
                    for row in rows
                )
            )
        declared_only_total += 1
        declared_only += int(
            any(
                row.declared_only
                and normalise(row.surface) == normalise(person.declared_only)
                for row in rows
            )
        )
        if person.undeclared_method not in person.methods[:2]:
            undeclared_total += 1
            undeclared_shown += int(
                any(
                    row.demonstrated
                    and not row.declared
                    and person.undeclared_method in _signature_methods(row.surface)
                    for row in rows
                )
            )

    # --- Q1 on every project ------------------------------------------------
    q1_hits = q1_expected = q1_returned = 0
    for spec in world.projects:
        project = Project.objects.get(
            name=spec.name, scope_lab__slug=f"sandbox-{spec.lab}"
        )
        viewer = project.scope_lab.memberships.get(is_lead=True).user
        returned = {
            normalise(v.surface)
            for v in read.undeclared_project_concepts(project, viewer)
        }
        expected = {
            normalise(x) for x in (spec.problem, *spec.data, spec.uncovered_need)
        }
        q1_expected += len(expected)
        q1_returned += len(returned)
        q1_hits += len(expected & returned)

    # --- invariants -------------------------------------------------------
    invariants = {
        "conversational_edges": Edge.objects.filter(tier=Tier.CONVERSATIONAL).count(),
        "private_concepts_from_papers": Concept.objects.filter(
            edges__author_work__isnull=False
        )
        .exclude(scope=Scope.GLOBAL)
        .distinct()
        .count(),
        "thin_works_with_edges": Edge.objects.filter(
            author_work__facets__thin=True
        ).count(),
        "rollup_evidence_from_someone_elses_work": _foreign_evidence(),
        "neutral_phrases_in_deny_list": deny_violations,
        "second_pass_model_calls": run.get("second_pass_model_calls", -1),
        "second_pass_works_read": run.get("second_pass", {}).get("read", -1),
        "second_projection_writes": run.get("second_projection_writes", -1),
    }

    return {
        "works_total": len(works),
        "works_clean_corpus": len(clean),
        "corpus_generator_slips": len(papers) - len(clean),
        "works_read": len(read_rows),
        "works_non_thin": len(non_thin),
        "thin_rate_on_clean": _rate(len(clean) - len(non_thin), len(clean)),
        "refused_by_facet": dict(refused_by_facet),
        "neutral_present_rate": _rate(neutral_present, len(non_thin)),
        "method_recall": _rate(recalled, len(non_thin)),
        "method_term_contamination": contaminated,
        "methods_split": splits,
        "method_split_total": sum(splits.values()),
        "split_examples": {
            m: [
                {
                    "concept": cid,
                    "papers": n,
                    "surfaces": sorted(surfaces_by_concept[cid])[:5],
                }
                for cid, n in concepts_by_method[m].most_common(6)
            ]
            for m in splits
        },
        "wrong_merges": {
            str(k): {"methods": v, "surfaces": sorted(surfaces_by_concept[k])[:6]}
            for k, v in wrong_merges.items()
        },
        "wrong_merge_total": len(wrong_merges),
        "field_ruler_accuracy": _rate(field_right, field_checks),
        "q2_declared_and_demonstrated_recall": _rate(both, both_total),
        "q2_declared_only_recall": _rate(declared_only, declared_only_total),
        "q2_undeclared_method_shown_recall": _rate(undeclared_shown, undeclared_total),
        "q1_recall": _rate(q1_hits, q1_expected),
        "q1_precision": _rate(q1_hits, q1_returned),
        "concepts_global": Concept.objects.filter(scope=Scope.GLOBAL).count(),
        "concepts_private": Concept.objects.exclude(scope=Scope.GLOBAL).count(),
        "edges_by_tier": dict(Counter(Edge.objects.values_list("tier", flat=True))),
        "invariants": invariants,
        "run": run,
    }


def _foreign_evidence() -> int:
    """Roll-up edges whose evidence names a work that is not the person's."""
    owner = {
        str(pk): user_id
        for pk, user_id in AuthorWork.objects.values_list("pk", "user_id")
    }
    bad = 0
    for user_id, evidence in Edge.objects.filter(
        user__isnull=False, tier=Tier.DEMONSTRATED, status=EdgeStatus.ACTIVE
    ).values_list("user_id", "evidence"):
        for item in evidence or []:
            bad += int(owner.get(str(item).removeprefix("work:")) != user_id)
    return bad


def failures(metrics: dict) -> list[str]:
    return [
        f"{name} = {value}"
        for name, value in metrics["invariants"].items()
        if value != 0
    ]


__all__ = ["INVARIANTS", "failures", "score_cn02"]

User = get_user_model()
