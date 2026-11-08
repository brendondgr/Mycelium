"""The recommendation tool's models: how well each corpus item fits each target.

These were models of the old ``content`` app. They keep their tables
(``content_relevancescore`` …) — each ``Meta.db_table`` is pinned — and moved
here by state-only migrations, so no data or schema changed.
"""

import uuid

from apps.core.db import exactly_one, validate_exactly_one
from django.conf import settings
from django.db import models

from tools.retrieval.models import ContentItem

TARGET_FIELDS = ("target_user", "target_project", "target_lab", "target_department")


class RelevanceScore(models.Model):
    """The match between a content item and a scoring target (briefing §3, §6).

    The target is polymorphic — a user's interest profile, a project, a lab, or
    a department — guarded so exactly one target is set. ``signals`` carries the
    per-signal breakdown (including the project-vs-interest weighting) so digests
    can explain why an item surfaced; the weighting lives in the engine, not the
    schema.
    """

    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    target_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_scores",
    )
    score = models.FloatField()
    signals = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-signal breakdown — the 'why this matters'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'content_relevancescore'
        ordering = ["-score"]
        constraints = [
            models.CheckConstraint(
                name="content_relevance_one_target",
                condition=exactly_one(*TARGET_FIELDS),
            ),
            *[
                models.UniqueConstraint(
                    fields=["content", field],
                    name=f"content_relevance_unique_{field}",
                )
                for field in TARGET_FIELDS
            ],
        ]

    def clean(self) -> None:
        validate_exactly_one(self, *TARGET_FIELDS)

    @property
    def target_type(self) -> str:
        """Derived discriminator: ``user`` / ``project`` / ``lab`` / ``department``."""
        if self.target_user_id is not None:
            return "user"
        if self.target_project_id is not None:
            return "project"
        if self.target_lab_id is not None:
            return "lab"
        return "department"

    @property
    def target(self):
        return (
            self.target_user
            or self.target_project
            or self.target_lab
            or self.target_department
        )

    def __str__(self) -> str:
        return f"{self.content} → {self.target_type} ({self.score:.3f})"


class RelevanceEvent(models.Model):
    """An append-only engagement event — a weak relevance label (Feature D).

    Every view / save / share / thumb / dismiss is logged with a config-driven
    weight (``settings.RELEVANCE_EVENT_WEIGHTS``). This is the ground-truth stream a
    future team-relevance recompute (and the evaluation harness) will read; it never
    mutates any individual profile. ``project`` is nullable so the same log can carry
    non-project engagement later.
    """

    class Action(models.TextChoices):
        VIEW = "view", "View"
        SAVE = "save", "Save"
        SHARE = "share", "Share"
        THUMBS_UP = "thumbs_up", "Thumbs up"
        THUMBS_DOWN = "thumbs_down", "Thumbs down"
        DISMISS = "dismiss", "Dismiss"
        OPEN_EXTERNAL = "open_external", "Open external"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    project = models.ForeignKey(
        "research.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    content = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="relevance_events",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    weight = models.FloatField(
        help_text="Per-action weight at capture time (config-driven)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'content_relevanceevent'
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["user", "content"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.action} {self.content} ({self.weight:+.2f})"


class ProjectProfile(models.Model):
    """A project's recomputed team-relevance signal (briefing Feature D).

    Separate from any individual :class:`~apps.accounts.models.Profile` — the team
    signal updates the *project*, never the member (project principle). The derived
    vector itself is written to ``research.Project.embedding`` (previously unused) so
    the recommendation pipeline can read it as the project's query vector; this row
    carries the aggregated interest terms and the recompute bookkeeping.
    """

    class Reason(models.TextChoices):
        MEMBERSHIP_CHANGE = "membership_change", "Membership change"
        ENGAGEMENT = "engagement", "Engagement"
        MANUAL = "manual", "Manual"

    project = models.OneToOneField(
        "research.Project",
        on_delete=models.CASCADE,
        related_name="team_profile",
    )
    interests = models.JSONField(
        default=dict,
        blank=True,
        help_text="Aggregated / deduped interest terms from members + engagement.",
    )
    last_recomputed = models.DateTimeField(null=True, blank=True)
    recompute_reason = models.CharField(
        max_length=20, choices=Reason.choices, blank=True, default=""
    )

    def __str__(self) -> str:
        return f"team profile for project {self.project_id}"

    class Meta:
        db_table = 'content_projectprofile'


class ItemComprehension(models.Model):
    """A structured précis of one content item, written once and reused forever.

    Stage one of the two-stage model pipeline. It is deliberately **profile-blind**
    — no reader, no interests, no relevance judgement in the input — which is what
    makes one extraction serve every user and every theme indefinitely. That is
    both where the depth in the final write-ups comes from and where the cost
    saving lives: the fit stage that follows reads this instead of six hundred
    truncated characters of abstract, and never pays to re-read the paper.

    Every field is grounded in the source text. An absent field is left empty
    rather than inferred, and ``thin`` marks a source too sparse to support a
    précis at all — a valid outcome that downstream stages degrade on rather than
    receiving a fabrication.

    Two things invalidate a stored précis and nothing else does (plan §19):
    ``prompt_version`` changing, and ``source_fingerprint`` changing because the
    item's own text changed — most often an abstract backfilled after an empty
    first pass. Time alone never invalidates: a précis from three months ago is
    still a correct reading of the same paper.
    """

    content = models.OneToOneField(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="comprehension",
    )
    problem = models.TextField(blank=True, default="")
    method = models.TextField(blank=True, default="")
    setting = models.TextField(
        blank=True,
        default="",
        help_text="The data, cohort, or setting the work was carried out in.",
    )
    claim = models.TextField(blank=True, default="")
    limitations = models.TextField(
        blank=True,
        default="",
        help_text="Limitations the authors themselves state — never inferred.",
    )
    reusable = models.TextField(
        blank=True,
        default="",
        help_text=(
            "What an outside researcher could concretely take: a method, a "
            "dataset, a baseline, a negative result, an evaluation protocol."
        ),
    )
    thin = models.BooleanField(
        default=False,
        help_text="The source text was too sparse to support a précis.",
    )
    prompt_version = models.CharField(max_length=32, default="", blank=True)
    source_fingerprint = models.CharField(max_length=64, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'content_itemcomprehension'
        indexes = [models.Index(fields=["prompt_version"])]

    def __str__(self) -> str:
        return f"comprehension<{self.content_id}>"

    @property
    def is_empty(self) -> bool:
        """True when nothing usable was extracted (a thin or failed pass)."""
        return self.thin or not any(
            (self.problem, self.method, self.claim, self.reusable)
        )

    def as_prompt_block(self) -> str:
        """The précis as the fit prompt reads it — labelled lines, empties dropped."""
        rows = (
            ("Problem", self.problem),
            ("Method", self.method),
            ("Data / setting", self.setting),
            ("Headline claim", self.claim),
            ("Stated limitations", self.limitations),
            ("Reusable", self.reusable),
        )
        return "\n".join(f"    {label}: {value}" for label, value in rows if value)
