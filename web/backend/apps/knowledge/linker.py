"""Which concept does this wording name? The linker, model-free.

Given a surface form ("conformal prediction", "CP intervals", "the imaging
data"), a facet when the caller knows one, and the scope of the source it came
from, return the concept it names. Three paths, in order:

1. **Alias.** An exact match on the normalised text, looked for in the source's
   own scope first and the shared vocabulary second.
2. **Embedding.** The nearest active concept visible from that scope, accepted
   only at cosine ≥ ``settings.KNOWLEDGE_MERGE_COSINE``. The wording becomes an
   alias of it, so the next time is path 1.
3. **Mint.** A new concept, in the source's own scope.

Two rules keep private words private:

* A source only ever sees its own scope and the shared (global) one. A lab's
  project never links to another lab's concept.
* Only a shared source (a declared profile, a published work, a call) links in
  global scope. When it does and a private concept names the same thing, that
  private concept is promoted to global under the shared wording, and any other
  private duplicates are folded into it (:mod:`.merging`). That is how a
  project's private concept and its members' declared interests end up as one
  concept without the project's phrasing ever leaving the lab.

When the embedder is unavailable the linker never mints: a new concept minted
without the embedding check is exactly the duplicate the check exists to
prevent. Those requests come back ``deferred`` and the nightly sweep retries.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from pgvector.django import CosineDistance

from apps.content.embeddings import embed_texts

from . import merging
from .models import Concept, ConceptAlias, Facet, Scope

#: How linking went, per request. ``skipped`` is a value that is not a term
#: (empty, or prose longer than ``KNOWLEDGE_MAX_SURFACE_CHARS``).
HOW = ("alias", "embedding", "promoted", "minted", "deferred", "skipped")

_SEPARATORS = re.compile(r"[\s_\-–—/()\[\]{}]+")
_EDGE_PUNCTUATION = " .,;:!?\"'`"
_MAX_TEXT = 200


def clean(surface) -> str:
    """The wording as it should be shown: whitespace collapsed, nothing else."""
    return " ".join(str(surface or "").split())[:_MAX_TEXT]


def normalise(surface) -> str:
    """The alias key: case-folded, separators unified, edge punctuation dropped.

    "Graph-Neural Networks", "graph neural networks." and "graph_neural
    networks" are one key, and brackets read as spaces. Other inner
    punctuation carries meaning and stays — "C++" and "C#" are not "C".
    """
    text = unicodedata.normalize("NFKC", str(surface or "")).casefold()
    text = _SEPARATORS.sub(" ", text)
    text = text.strip(_EDGE_PUNCTUATION)
    return " ".join(text.split())[:_MAX_TEXT]


@dataclass(frozen=True)
class LinkRequest:
    """One wording to link.

    ``facet`` restricts matching to that facet; ``None`` accepts a match of any
    facet and mints as ``default_facet`` — how a declared keyword links, since
    a person's own words are never reinterpreted into a facet by a model.
    ``owner`` is the user, lab, or department a non-global scope belongs to.
    """

    surface: str
    facet: str | None = None
    default_facet: str = Facet.AREA
    scope: str = Scope.GLOBAL
    owner: object = None


@dataclass(frozen=True)
class LinkResult:
    request: LinkRequest
    how: str
    concept: Concept | None = None


def _owner_kwargs(scope: str, owner) -> dict:
    if scope == Scope.GLOBAL:
        return {"scope": Scope.GLOBAL}
    if owner is None:
        raise ValueError(f"a {scope} link needs an owner")
    field = {
        Scope.PERSONAL: "scope_user",
        Scope.LAB: "scope_lab",
        Scope.DEPARTMENT: "scope_department",
    }[scope]
    return {"scope": scope, field: owner}


def _visible(request: LinkRequest, prefix: str = "") -> Q:
    """What a source may link to: the shared vocabulary and its own scope."""
    visible = Q(**{f"{prefix}scope": Scope.GLOBAL})
    if request.scope != Scope.GLOBAL:
        own = {
            f"{prefix}{key}": value
            for key, value in _owner_kwargs(request.scope, request.owner).items()
        }
        visible |= Q(**own)
    return visible


def _facet_filter(request: LinkRequest, prefix: str = "") -> Q:
    if request.facet is None:
        return Q()
    return Q(**{f"{prefix}facet": request.facet})


def _live(concept: Concept) -> Concept:
    """Follow a merge chain to the concept that is still active."""
    seen = set()
    while concept.status == Concept.Status.MERGED and concept.merged_into_id:
        if concept.pk in seen:  # pragma: no cover - a cycle is a data bug
            break
        seen.add(concept.pk)
        concept = concept.merged_into
    return concept


def _by_alias(request: LinkRequest, text: str) -> Concept | None:
    aliases = (
        ConceptAlias.objects.filter(text=text)
        .filter(_visible(request))
        .filter(_facet_filter(request))
        .select_related("concept")
    )
    best = None
    for alias in aliases:
        # The source's own words first: a lab's alias beats the shared one.
        if alias.scope != Scope.GLOBAL:
            return _live(alias.concept)
        best = best or alias
    return _live(best.concept) if best else None


def _nearest(queryset, vector) -> tuple[Concept | None, float]:
    concept = (
        queryset.filter(status=Concept.Status.ACTIVE, embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance", "pk")
        .first()
    )
    if concept is None:
        return None, 0.0
    return concept, 1.0 - float(concept.distance)


def _add_alias(concept: Concept, text: str, request: LinkRequest) -> None:
    try:
        with transaction.atomic():
            ConceptAlias.objects.get_or_create(
                text=text,
                facet=concept.facet,
                **_owner_kwargs(request.scope, request.owner),
                defaults={"concept": concept},
            )
    except IntegrityError:  # pragma: no cover - a concurrent link won the race
        pass


def _private_matches(request: LinkRequest, text: str, vector) -> list[Concept]:
    """Private concepts, in any scope, that name what this shared source names."""
    threshold = settings.KNOWLEDGE_MERGE_COSINE
    private = Concept.objects.exclude(scope=Scope.GLOBAL).filter(
        status=Concept.Status.ACTIVE
    )
    if request.facet is not None:
        private = private.filter(facet=request.facet)
    found: dict[int, tuple[float, Concept]] = {}
    for alias in ConceptAlias.objects.filter(
        text=text, concept__in=private
    ).select_related("concept"):
        found[alias.concept_id] = (2.0, alias.concept)  # exact wording ranks first
    for concept in (
        private.filter(embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", vector))
        .filter(distance__lte=1.0 - threshold)
        .order_by("distance", "pk")[:50]
    ):
        found.setdefault(concept.pk, (1.0 - float(concept.distance), concept))
    return [concept for _, concept in sorted(found.values(), key=lambda p: -p[0])]


def _absorb(shared: Concept, private: list[Concept]) -> None:
    for concept in private:
        if concept.pk != shared.pk and concept.facet == shared.facet:
            merging.merge(concept, shared, kind="promote")


def _link_one(request: LinkRequest, text: str, vector) -> LinkResult:
    concept = _by_alias(request, text)
    if concept is not None:
        return LinkResult(request, "alias", concept)
    if vector is None:
        return LinkResult(request, "deferred")

    threshold = settings.KNOWLEDGE_MERGE_COSINE
    visible = Concept.objects.filter(_visible(request)).filter(_facet_filter(request))
    nearest, cosine = _nearest(visible, vector)
    shared = request.scope == Scope.GLOBAL

    if nearest is not None and cosine >= threshold:
        _add_alias(nearest, text, request)
        if shared:
            _absorb(nearest, _private_matches(request, text, vector))
        return LinkResult(request, "embedding", nearest)

    if shared:
        private = _private_matches(request, text, vector)
        if private:
            chosen = merging.promote(
                private[0], label=clean(request.surface), embedding=vector
            )
            _absorb(chosen, private[1:])
            _add_alias(chosen, text, request)
            return LinkResult(request, "promoted", chosen)

    concept = Concept.objects.create(
        label=clean(request.surface),
        facet=request.facet or request.default_facet,
        embedding=vector,
        **_owner_kwargs(request.scope, request.owner),
    )
    _add_alias(concept, text, request)
    return LinkResult(request, "minted", concept)


def link_many(requests: list[LinkRequest]) -> list[LinkResult]:
    """Link a batch, embedding every wording that needs it in one call."""
    texts = [normalise(request.surface) for request in requests]
    limit = settings.KNOWLEDGE_MAX_SURFACE_CHARS
    usable = [
        bool(text) and len(clean(request.surface)) <= limit
        for request, text in zip(requests, texts, strict=True)
    ]

    # Only wordings no alias already answers are worth an embedding.
    needs_vector = [
        index
        for index, request in enumerate(requests)
        if usable[index] and _by_alias(request, texts[index]) is None
    ]
    vectors: dict[int, list[float] | None] = {}
    if needs_vector:
        embedded = embed_texts([clean(requests[i].surface) for i in needs_vector])
        for position, index in enumerate(needs_vector):
            vectors[index] = embedded[position] if embedded else None

    results: list[LinkResult] = []
    for index, request in enumerate(requests):
        if not usable[index]:
            results.append(LinkResult(request, "skipped"))
            continue
        with transaction.atomic():
            results.append(_link_one(request, texts[index], vectors.get(index)))
    return results


def link(surface: str, **kwargs) -> LinkResult:
    """Link one wording. See :class:`LinkRequest` for the arguments."""
    return link_many([LinkRequest(surface=surface, **kwargs)])[0]
