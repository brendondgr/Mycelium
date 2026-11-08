"""The interests contract — the one validated shape ``Profile.interests`` holds.

Everything that writes interests (the Mylo intake agent, the author importer,
manual admin edits, the API) funnels through :func:`validate_interests`, so a
single gate enforces the schema (brief Phase A). The validator is a DRF
serializer because DRF is already the project's API layer; there is no Pydantic
dependency to reach for.

Each field has one deliberate job in the scan → retrieve → rank → suggest
pipeline; the table's "Feeds" column is the contract for what reads it:

| Key            | Type      | Required | Feeds                              |
|----------------|-----------|----------|------------------------------------|
| ``version``    | int       | system   | migration safety                   |
| ``statement``  | str       | no       | embedding (primary text), LLM      |
| ``areas``      | list[str] | yes      | focus re-rank boost + LLM judgment |
| ``keywords``   | list[str] | no       | embedding + LLM (semantic match)   |
| ``clusters``   | list[obj] | no (v2)  | cluster-scoped scoring + attribution |
| ``skills``     | list[str] | no       | LLM prompts + team-gap matcher     |
| ``funding_needs`` | list[str] | no    | grant matching                     |
| ``eligibility``| dict      | no       | grant/fellowship gating            |
| ``seeking``    | list[str] | no       | fellowship matching (students)     |
| ``exclusions`` | list[str] | no       | noise reduction                    |
| ``preferences``| list[str] | no       | write-up beats, explanation (Plan 05) |
| ``trajectory`` | dict      | no       | fellowship / grant matching (Plan 05) |
| ``learning_goals`` | list[str] | no   | wants_to_learn edges; never a skill |
| ``sources``    | dict      | no       | provenance / audit                 |

Notes on the fields with a non-obvious role:

- ``areas`` ("research focus") does *not* drive the literature search and is
  *not* baked into the embedding vector. It feeds the weighted re-rank
  (``tools.recommendation.ranking``) as a focus boost and is handed to the language
  model
  to judge and explain match strength. The actual search queries come from a
  separate per-user ``WatchPreference`` (the sole source of search terms).
- ``keywords`` (with ``statement``) is the semantic fingerprint that *is*
  embedded and retrieved against.
- ``skills`` reaches the model prompts (the profile block built by
  ``tools.delivery.briefing`` and ``tools.recommendation.opportunity_llm``) and the
  deterministic ``tools.delivery.matchers.team_gap`` matcher, which reads ``areas``
  and ``skills`` together as "what this person says they do". It is deliberately
  *not* embedded and *not* turned into search queries. Fellowship matching still
  does not read it — that gates on ``eligibility``, ``seeking`` and stage.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

CURRENT_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)

# The cluster count when no person is in context (fixtures, commands). A person's
# own limit comes from apps.billing.entitlements.cluster_cap. Kept in sync with
# tools.recommendation.clustering.MAX_CLUSTERS, the number Mylo proposes by default.
MAX_CLUSTERS = 6

# Broad fellowship-field buckets (matches Illinois Fellowship Finder vocabulary).
ELIGIBILITY_FIELDS = [
    "Social Sciences",
    "Sciences/Engineering/Math",
    "Professional Programs",
    "Fine Arts",
    "Humanities",
]

# Restriction groups a user can opt in to (controls which group-limited awards surface).
ELIGIBLE_RESTRICTIONS = ["Women", "Equity"]

# Citizenship tokens.
CITIZENSHIP_CHOICES = ["us", "international", ""]

# Academic stage tokens.
STAGE_CHOICES = [
    "masters",
    "doctoral_early",
    "doctoral_dissertation",
    "postdoc",
    "",
]


def _str_list(**kwargs: Any) -> serializers.ListField:
    return serializers.ListField(child=serializers.CharField(), **kwargs)


class EligibilityContract(serializers.Serializer):
    """Validated shape for ``Profile.interests["eligibility"]``.

    All fields are optional with safe defaults so an incomplete or absent block
    still produces a usable eligibility profile for fellowship matching.
    Unknown extra keys (e.g. ``career_stage`` written by intake/agent.py) are
    preserved and not hard-rejected, matching the loose DictField behaviour they
    replaced — the ``to_internal_value`` override skips unknown-key rejection.

    Fields:
      citizenship  "us" | "international" | "" — default "us".
      stage        academic stage token — default "". Blank is not the same as
                   "no stage": :func:`tools.recommendation.fellowships.derive_stage`
                   falls back to ``career_stage`` and then to the profile's
                   ``academic_title``, so an account that never answered the
                   eligibility step still places on the ladder. The stage gate is
                   asymmetric — it only ever hides an award whose *earliest*
                   acceptable stage is above the applicant's.
      fields       subset of five broad field buckets — validated, allow empty.
      eligible_restrictions  subset of ["Women","Equity"] — default [].
      lab_visible  opt-in: may this member's fellowship eligibility be shown to
                   their labs? Default False — a lab fellowship recommendation names
                   only members who explicitly consent (D-11 privacy), never who
                   was ineligible, so nothing leaks by inference until opt-in.
      phd_completed_year  the year the doctorate was conferred, when known. The
                   one input for awards that limit how long ago that was ("within
                   24 months of the PhD"); such a limit is only ever enforced when
                   both it and this are known.
      career_stage  kept for backward-compat (intake/agent.py writes it).
    """

    citizenship = serializers.ChoiceField(
        choices=CITIZENSHIP_CHOICES, required=False, default="us", allow_blank=True
    )
    stage = serializers.ChoiceField(
        choices=STAGE_CHOICES, required=False, default="", allow_blank=True
    )
    fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ELIGIBILITY_FIELDS),
        required=False,
        default=list,
    )
    eligible_restrictions = serializers.ListField(
        child=serializers.ChoiceField(choices=ELIGIBLE_RESTRICTIONS),
        required=False,
        default=list,
    )
    # Opt-in consent for lab-visible fellowship eligibility (D-11). Default off.
    lab_visible = serializers.BooleanField(required=False, default=False)
    # Year the doctorate was conferred; only meaningful for post-PhD applicants.
    phd_completed_year = serializers.IntegerField(
        required=False, allow_null=True, min_value=1900, max_value=2200
    )
    # Backward-compat: intake/agent.py writes career_stage; keep it as a plain
    # string so old data round-trips without error.
    career_stage = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Pass through unknown keys rather than hard-failing.

        The existing DictField contract accepted any keys inside eligibility.
        We validate the *known* keys but carry unknown ones through unchanged so
        that data written by intake/agent.py (career_stage, university, etc.)
        is never silently destroyed.
        """
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["eligibility must be an object"]}
            )
        # Validate only the keys we know about; carry the rest through.
        known = {k: v for k, v in data.items() if k in self.fields}
        unknown = {k: v for k, v in data.items() if k not in self.fields}
        validated = super().to_internal_value(known)
        validated.update(unknown)
        return validated


class ClusterContract(serializers.Serializer):
    """Validated shape for one entry in ``Profile.interests["clusters"]``.

    A cluster is a named grouping over a subset of the profile's ``areas``:

      id     stable slug, generated once at creation and never regenerated on
             relabel/edit — this is what makes badges, filters, and attribution
             survive profile edits. Required and non-blank.
      label  the human display name shown on cluster badges.
      areas  this cluster's subset of the profile's declared areas (>= 1).

    Cross-field rules (the partition — union == areas, no overlap, no orphan)
    are enforced on the parent :class:`InterestsContract`, which is the only
    place that sees both ``areas`` and ``clusters`` together.
    """

    id = serializers.CharField()
    label = serializers.CharField()
    areas = _str_list(allow_empty=False)


class TrajectoryContract(serializers.Serializer):
    """Where the person wants their career to go (ambient Plan 05).

    Confirmed understanding only: written when the person says yes to Mylo's
    reading, or types it themselves. ``direction`` is short free text;
    ``target_stage`` and ``horizon`` are optional ("postdoc", "two years").
    """

    direction = serializers.CharField(max_length=200)
    target_stage = serializers.CharField(
        max_length=60, required=False, allow_blank=True
    )
    horizon = serializers.CharField(max_length=60, required=False, allow_blank=True)


class InterestsContract(serializers.Serializer):
    """Validate one ``Profile.interests`` payload against the contract.

    v2 adds ``clusters`` (a partition of ``areas`` into named groups). A payload
    with no ``clusters`` key is a valid v1 profile — it behaves downstream as one
    implicit cluster over all areas (:mod:`tools.recommendation.clustering`), so no data
    migration is needed; v2 is written on the next profile save.
    """

    version = serializers.IntegerField(required=False)
    statement = serializers.CharField(required=False, allow_blank=True)
    areas = _str_list()  # required: a profile must declare its research areas
    keywords = _str_list(required=False)
    clusters = ClusterContract(many=True, required=False)
    skills = _str_list(required=False)
    funding_needs = _str_list(required=False)
    eligibility = EligibilityContract(required=False)
    seeking = _str_list(required=False)
    exclusions = _str_list(required=False)
    # Ambient Plan 05. Confirmed understanding only, and none of it counts
    # against a cluster or topic cap: preferences reach explanation, trajectory
    # reaches opportunities, learning goals are topics to learn — never skills.
    preferences = _str_list(required=False)
    trajectory = TrajectoryContract(required=False)
    learning_goals = _str_list(required=False)
    sources = serializers.DictField(required=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["interests must be an object"]}
            )
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: ["unknown field"] for key in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_version(self, value: int) -> int:
        if value not in SUPPORTED_VERSIONS:
            raise serializers.ValidationError(
                f"unsupported version {value}; supported: {list(SUPPORTED_VERSIONS)}"
            )
        return value

    def _cluster_cap(self) -> int | None:
        """The saving person's cluster limit (``limits.clusters``, or their tier's
        under subscriptions; ``None`` = unlimited).

        With no person in context — a project's focus, an importer, a command —
        the instance's ``limits.clusters`` while billing is off, and the
        historical ``MAX_CLUSTERS`` under subscriptions.
        """
        from apps.billing.entitlements import (
            billing_enabled,
            cluster_cap,
            instance_limit,
        )

        context = self.context or {}
        user = context.get("user") or getattr(context.get("request"), "user", None)
        if user is not None and user.is_authenticated:
            return cluster_cap(user)
        return MAX_CLUSTERS if billing_enabled() else instance_limit("clusters")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Enforce the cluster partition: every area in exactly one cluster.

        Only runs when ``clusters`` is present; a clusterless payload is a valid
        v1 profile. Rules (brief Phase 0): union of ``clusters[].areas`` equals
        ``areas`` exactly (no orphan area, no cluster area outside ``areas``), no
        area in two clusters, cluster ids unique, and no more clusters than the
        saving person's limit (:meth:`_cluster_cap`).
        Comparison is case-insensitive on whitespace-normalized strings so the
        cluster areas need only match the declared areas up to trivial drift.
        """
        clusters = attrs.get("clusters")
        if not clusters:
            return attrs

        cap = self._cluster_cap()
        if cap is not None and len(clusters) > cap:
            raise serializers.ValidationError(
                {"clusters": [f"at most {cap} clusters allowed"]}
            )

        ids = [str(c.get("id", "")).strip() for c in clusters]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError(
                {"clusters": ["cluster ids must be unique"]}
            )

        area_folds = {" ".join(a.split()).casefold() for a in attrs.get("areas", [])}
        seen: set[str] = set()
        assigned: set[str] = set()
        for cluster in clusters:
            for area in cluster.get("areas", []):
                fold = " ".join(str(area).split()).casefold()
                if fold in seen:
                    raise serializers.ValidationError(
                        {"clusters": [f"area '{area}' is in more than one cluster"]}
                    )
                if fold not in area_folds:
                    raise serializers.ValidationError(
                        {"clusters": [f"cluster area '{area}' is not a declared area"]}
                    )
                seen.add(fold)
                assigned.add(fold)

        orphans = area_folds - assigned
        if orphans:
            raise serializers.ValidationError(
                {
                    "clusters": [
                        "every area must belong to a cluster; unassigned: "
                        + ", ".join(sorted(orphans))
                    ]
                }
            )
        return attrs


def validate_interests(data: Any, *, user=None) -> dict[str, Any]:
    """Return a validated, version-stamped interests dict, or raise.

    Raises :class:`rest_framework.serializers.ValidationError` (a DRF/Django
    ``ValidationError``) on any contract violation, so the same gate produces a
    400 from the API and a friendly admin-form error. ``user`` is the person
    whose profile this is, so their own cluster limit applies.
    """

    serializer = InterestsContract(data=data, context={"user": user})
    serializer.is_valid(raise_exception=True)
    validated = dict(serializer.validated_data)
    validated.setdefault("version", CURRENT_VERSION)
    return validated


def stamp_version(interests: dict[str, Any] | None) -> dict[str, Any]:
    """Wrap a pre-contract interests row to ``version: 1`` without reshaping.

    Used by the backfill migration and any importer of legacy data. The one
    coercion beyond stamping: the demo seeder historically wrote ``seeking`` as a
    single string, while the contract types it ``list[str]`` — promote it.
    """

    data = dict(interests or {})
    # Legacy rows have no clusters; stamp them v1 (they behave as one implicit
    # cluster). v2 is written the next time the profile is saved through the API.
    data.setdefault("version", 1)
    seeking = data.get("seeking")
    if isinstance(seeking, str):
        data["seeking"] = [seeking] if seeking else []
    return data
