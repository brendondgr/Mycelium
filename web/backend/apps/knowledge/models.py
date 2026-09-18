"""The knowledge core: concepts, and who is connected to them, and how we know.

Two tables carry nearly all of it. A :class:`Concept` is one idea — a problem, a
method, a setting, a broad research area — independent of anybody who holds it.
An :class:`Edge` is one subject's relation to one concept: a person interested
in it, a project using it as a method, a paper that works on it. Every edge says
where it came from (its **tier**), because the three places knowledge comes from
are not equally strong and are not equally shareable:

* ``declared`` — the person's own profile, a lab's, or a project's stated state.
  What the person controls and can correct.
* ``demonstrated`` — what the person's own published works show (plan CN-02).
* ``conversational`` — what Mylo understood from ambient conversation
  (ambient-profile Plans 04–06). Seen by the person, shapes their own
  recommendations once they confirm it, and is read by **nobody else**.

The tier rules are enforced in :mod:`apps.knowledge.read`, whose functions each
bake in the tiers they may return; nothing outside this app queries these
tables directly (see ``tests/test_import_boundary.py``).

Everything a subject owns is a real foreign key, so deleting a person, a
project, a lab, or a work deletes its edges without anyone having to remember
to. That is the reason this graph lives in Postgres rather than in the Neo4j
container Compose already runs: "forget me" is a guarantee here, not a sync job
across two stores (plan CN-01, OD-CN6).

**Scope.** A concept minted from a private source — a project's state, a
conversation — is born in the narrowest scope that produced it (one person, one
lab, one department) and is never ``global``. It becomes global only by matching
a concept from a shared source, and when it does, its private wording is
replaced (:func:`apps.knowledge.merging.promote`).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from pgvector.django import VectorField


class Facet(models.TextChoices):
    """Which side of a piece of work a concept names (design §3).

    ``area`` holds broad research areas that are not one facet — "machine
    learning" is neither a problem nor a method. Offer and need are not facets;
    they are relations (:class:`Relation`).
    """

    AREA = "area", "Research area"
    PROBLEM = "problem", "Problem"
    METHOD = "method", "Method"
    SETTING = "setting", "Setting or data"


class Scope(models.TextChoices):
    GLOBAL = "global", "Shared vocabulary"
    DEPARTMENT = "department", "One department"
    LAB = "lab", "One lab"
    PERSONAL = "personal", "One person"


class Relation(models.TextChoices):
    INTERESTED_IN = "interested_in", "Interested in"
    WORKS_ON = "works_on", "Works on"
    USES_METHOD = "uses_method", "Uses method"
    WORKS_IN_SETTING = "works_in_setting", "Works in setting / with data"
    WANTS_TO_LEARN = "wants_to_learn", "Wants to learn"
    CAN_DO = "can_do", "Can do"
    OFFERS = "offers", "Offers (reusable)"
    NEEDS = "needs", "Needs"
    REJECTED = "rejected", "Said no to"


class Tier(models.TextChoices):
    DECLARED = "declared", "Declared"
    DEMONSTRATED = "demonstrated", "Demonstrated by their papers"
    CONVERSATIONAL = "conversational", "From conversation"


class EdgeStatus(models.TextChoices):
    """A conversational edge is ``pending`` until its person confirms it.

    Declared and demonstrated edges are ``active`` from birth: the first is the
    person's own word, the second their published record.
    """

    PENDING = "pending", "Pending confirmation"
    ACTIVE = "active", "Active"
    FADED = "faded", "Faded"
    REJECTED = "rejected", "Rejected"


def _scope_consistent(prefix: str = "") -> Q:
    """Each scope names exactly the owner its value implies, and no other."""

    def none_of(*fields):
        return Q(**{f"{prefix}{field}__isnull": True for field in fields})

    return (
        (
            Q(**{f"{prefix}scope": Scope.GLOBAL})
            & none_of("scope_user", "scope_lab", "scope_department")
        )
        | (
            Q(
                **{
                    f"{prefix}scope": Scope.PERSONAL,
                    f"{prefix}scope_user__isnull": False,
                }
            )
            & none_of("scope_lab", "scope_department")
        )
        | (
            Q(**{f"{prefix}scope": Scope.LAB, f"{prefix}scope_lab__isnull": False})
            & none_of("scope_user", "scope_department")
        )
        | (
            Q(
                **{
                    f"{prefix}scope": Scope.DEPARTMENT,
                    f"{prefix}scope_department__isnull": False,
                }
            )
            & none_of("scope_user", "scope_lab")
        )
    )


class _Scoped(models.Model):
    """The scope columns concepts and aliases share."""

    scope = models.CharField(
        max_length=16, choices=Scope.choices, default=Scope.GLOBAL, db_index=True
    )
    scope_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    scope_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    scope_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        abstract = True


class Concept(_Scoped):
    """One idea, independent of who holds it.

    ``label`` is the canonical wording. For a global concept it came from a
    shared source; a person is shown their *own* wording (``Edge.surface``), not
    this, so a label never carries one person's phrasing to another.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged into another concept"

    label = models.CharField(max_length=200)
    facet = models.CharField(max_length=16, choices=Facet.choices)
    neutral_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="The field-neutral phrasing (design §5.5). Filled by CN-02 for "
        "methods; blank until then.",
    )
    # No fixed dimension, and so no ANN index: the project keeps the embedding
    # dimension unlocked everywhere (see Profile.embedding), and a vocabulary of
    # a few thousand concepts is searched faster sequentially than an HNSW
    # index would be maintained. Revisit if the table grows past ~100k rows.
    embedding = VectorField(null=True, blank=True)
    openalex_field_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="OpenAlex field, for measuring distance between fields only "
        "(design §5.6). Filled by CN-02.",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_from",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.CheckConstraint(
                name="knowledge_concept_scope_owner", condition=_scope_consistent()
            ),
            models.CheckConstraint(
                name="knowledge_concept_has_label", condition=~Q(label="")
            ),
            models.CheckConstraint(
                name="knowledge_concept_merge_target",
                condition=Q(status="active", merged_into__isnull=True)
                | Q(status="merged"),
            ),
        ]
        indexes = [models.Index(fields=["facet", "scope", "status"])]

    def __str__(self) -> str:
        return f"{self.label} ({self.facet}, {self.scope})"


class ConceptAlias(_Scoped):
    """A normalised surface form that names a concept: the linker's exact path.

    An alias keeps the scope of the source that produced it, even after its
    concept is promoted to global — a lab's private wording stays the lab's.
    """

    concept = models.ForeignKey(
        Concept, on_delete=models.CASCADE, related_name="aliases"
    )
    text = models.CharField(max_length=200, help_text="Normalised (linker.normalise).")
    # The facet the wording was recorded under — the concept's own at the
    # time. Kept on the alias so the database can check uniqueness, and so an
    # unspecified (area) wording stays one after it folds into a specific
    # concept (linker._facets).
    facet = models.CharField(max_length=16, choices=Facet.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="knowledge_alias_scope_owner", condition=_scope_consistent()
            ),
            models.UniqueConstraint(
                fields=["facet", "text"],
                condition=Q(scope=Scope.GLOBAL),
                name="knowledge_alias_unique_global",
            ),
            models.UniqueConstraint(
                fields=["scope_user", "facet", "text"],
                condition=Q(scope=Scope.PERSONAL),
                name="knowledge_alias_unique_personal",
            ),
            models.UniqueConstraint(
                fields=["scope_lab", "facet", "text"],
                condition=Q(scope=Scope.LAB),
                name="knowledge_alias_unique_lab",
            ),
            models.UniqueConstraint(
                fields=["scope_department", "facet", "text"],
                condition=Q(scope=Scope.DEPARTMENT),
                name="knowledge_alias_unique_department",
            ),
        ]
        indexes = [models.Index(fields=["text"])]

    def __str__(self) -> str:
        return f"{self.text} → {self.concept_id}"


#: The subject columns of an edge. Exactly one is set on every row.
SUBJECT_FIELDS = ("user", "project", "lab", "author_work", "content_item")


def _exactly_one_subject() -> Q:
    clauses = []
    for chosen in SUBJECT_FIELDS:
        clauses.append(
            Q(**{f"{field}__isnull": field != chosen for field in SUBJECT_FIELDS})
        )
    condition = clauses[0]
    for clause in clauses[1:]:
        condition |= clause
    return condition


class Edge(models.Model):
    """One subject's relation to one concept, with where that knowledge came from.

    ``surface`` is the subject's own wording — what the person typed, what the
    project states — and is what the person is shown. ``evidence`` holds ids and
    paths only: observation ids, work ids, or the profile field the edge
    mirrors. Never text.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_edges",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_edges",
    )
    lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_edges",
    )
    author_work = models.ForeignKey(
        "accounts.AuthorWork",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_edges",
    )
    content_item = models.ForeignKey(
        "content.ContentItem",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_edges",
    )

    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="edges")
    relation = models.CharField(max_length=24, choices=Relation.choices)
    tier = models.CharField(max_length=16, choices=Tier.choices)
    status = models.CharField(
        max_length=16,
        choices=EdgeStatus.choices,
        default=EdgeStatus.ACTIVE,
        db_index=True,
    )
    surface = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="The subject's own wording for this concept.",
    )
    weight = models.FloatField(default=1.0)
    first_seen = models.DateTimeField(default=timezone.now)
    last_reinforced = models.DateTimeField(default=timezone.now)
    half_life_days = models.FloatField(
        null=True,
        blank=True,
        help_text="Null for declared and demonstrated edges, which do not decay.",
    )
    evidence = models.JSONField(
        default=list,
        blank=True,
        help_text="Ids and field paths only — never text.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_reinforced", "-pk"]
        constraints = [
            models.CheckConstraint(
                name="knowledge_edge_one_subject", condition=_exactly_one_subject()
            ),
            models.CheckConstraint(
                name="knowledge_edge_weight_nonnegative", condition=Q(weight__gte=0)
            ),
            # Only conversation waits for a person; everything else is either
            # their own word or their published record.
            models.CheckConstraint(
                name="knowledge_edge_pending_is_conversational",
                condition=~Q(status=EdgeStatus.PENDING) | Q(tier=Tier.CONVERSATIONAL),
            ),
            # Conversation is about a person. A project, a lab, or a work never
            # acquires a conversational edge (projects get developments, Plan 05).
            models.CheckConstraint(
                name="knowledge_edge_conversational_is_personal",
                condition=~Q(tier=Tier.CONVERSATIONAL) | Q(user__isnull=False),
            ),
            *[
                models.UniqueConstraint(
                    fields=[subject, "relation", "concept", "tier"],
                    condition=Q(**{f"{subject}__isnull": False}),
                    name=f"knowledge_edge_unique_{subject}",
                )
                for subject in SUBJECT_FIELDS
            ],
        ]
        indexes = [models.Index(fields=["concept", "tier", "status"])]

    def __str__(self) -> str:
        return (
            f"Edge({self.subject_label} {self.relation} {self.concept_id}, {self.tier})"
        )

    @property
    def subject_label(self) -> str:
        for field in SUBJECT_FIELDS:
            value = getattr(self, f"{field}_id")
            if value is not None:
                return f"{field}:{value}"
        return "?"


class ConceptMerge(models.Model):
    """An append-only record of every merge, promotion, and reversal.

    Enough is kept to reverse an admin merge exactly (the moved edge and alias
    ids, and the rows that collapsed into an existing edge). A promotion keeps
    ids only: its source was private, and the point of promoting is that the
    private wording stops existing.
    """

    class Kind(models.TextChoices):
        MERGE = "merge", "Merged by staff"
        PROMOTE = "promote", "Promoted to the shared vocabulary"
        UNMERGE = "unmerge", "Merge reversed"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    source = models.ForeignKey(
        Concept,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merges_out",
    )
    target = models.ForeignKey(
        Concept,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merges_in",
    )
    moved_edges = models.JSONField(default=list, blank=True)
    collapsed_edges = models.JSONField(default=list, blank=True)
    moved_aliases = models.JSONField(default=list, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reversed_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reverses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"ConceptMerge({self.kind} {self.source_id} → {self.target_id})"


class WorkFacets(models.Model):
    """What one of a person's own published works shows, facet by facet.

    One row per :class:`~apps.accounts.models.AuthorWork`, written once per
    (prompt version, source fingerprint) and never again for unchanged text —
    the same rule the corpus précis follows. Two layers:

    * **Sentences** (``problem``, ``method``, ``setting``, ``reusable``) and one
      vector per facet: what retrieval ranks, per work, so a person is never
      averaged into one vector (design §5.3).
    * **Terms** (short noun phrases per facet): what the linker turns into
      concepts and ``demonstrated`` edges.

    ``method_neutral`` restates the main method without field vocabulary
    (design §5.5) so a method can be matched across fields. A thin work — no
    abstract, or nothing the model could ground — produces no edges.
    """

    author_work = models.OneToOneField(
        "accounts.AuthorWork", on_delete=models.CASCADE, related_name="facets"
    )
    problem = models.TextField(blank=True, default="")
    method = models.TextField(blank=True, default="")
    setting = models.TextField(blank=True, default="")
    reusable = models.TextField(blank=True, default="")
    method_neutral = models.CharField(max_length=200, blank=True, default="")
    terms = models.JSONField(
        default=dict,
        blank=True,
        help_text="{problem|method|setting|reusable: [short phrases]}",
    )
    thin = models.BooleanField(default=False)
    refused = models.JSONField(
        default=list,
        blank=True,
        help_text="What failed validation and was dropped, for diagnosis.",
    )
    problem_vec = VectorField(null=True, blank=True)
    method_vec = VectorField(null=True, blank=True)
    method_neutral_vec = VectorField(null=True, blank=True)
    setting_vec = VectorField(null=True, blank=True)
    reusable_vec = VectorField(null=True, blank=True)
    openalex_field_id = models.CharField(max_length=32, blank=True, default="")
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    source_fingerprint = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "work facets"

    def __str__(self) -> str:
        return f"WorkFacets({self.author_work_id}{', thin' if self.thin else ''})"
