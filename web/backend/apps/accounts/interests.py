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
| ``skills``     | list[str] | no       | fellowship matching (future)       |
| ``funding_needs`` | list[str] | no    | grant matching                     |
| ``eligibility``| dict      | no       | grant/fellowship gating            |
| ``seeking``    | list[str] | no       | fellowship matching (students)     |
| ``exclusions`` | list[str] | no       | noise reduction                    |
| ``sources``    | dict      | no       | provenance / audit                 |

Notes on the fields with a non-obvious role:

- ``areas`` ("research focus") does *not* drive the literature search and is
  *not* baked into the embedding vector. It feeds the weighted re-rank
  (``apps.content.ranking``) as a focus boost and is handed to the language model
  to judge and explain match strength. The actual search queries come from a
  separate per-user ``WatchPreference`` (the sole source of search terms).
- ``keywords`` (with ``statement``) is the semantic fingerprint that *is*
  embedded and retrieved against.
- ``skills`` is collected and stored but not yet consumed by any matcher; it is
  parked for the planned fellowship-matching feature.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

CURRENT_VERSION = 1
SUPPORTED_VERSIONS = (1,)

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
      stage        academic stage token — default "".
      fields       subset of five broad field buckets — validated, allow empty.
      eligible_restrictions  subset of ["Women","Equity"] — default [].
      lab_visible  opt-in: may this member's fellowship eligibility be shown to
                   their labs? Default False — a lab fellowship recommendation names
                   only members who explicitly consent (D-11 privacy), never who
                   was ineligible, so nothing leaks by inference until opt-in.
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


class InterestsContract(serializers.Serializer):
    """Validate one ``Profile.interests`` payload against the v1 contract."""

    version = serializers.IntegerField(required=False)
    statement = serializers.CharField(required=False, allow_blank=True)
    areas = _str_list()  # required: a profile must declare its research areas
    keywords = _str_list(required=False)
    skills = _str_list(required=False)
    funding_needs = _str_list(required=False)
    eligibility = EligibilityContract(required=False)
    seeking = _str_list(required=False)
    exclusions = _str_list(required=False)
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


def validate_interests(data: Any) -> dict[str, Any]:
    """Return a validated, version-stamped interests dict, or raise.

    Raises :class:`rest_framework.serializers.ValidationError` (a DRF/Django
    ``ValidationError``) on any contract violation, so the same gate produces a
    400 from the API and a friendly admin-form error.
    """

    serializer = InterestsContract(data=data)
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
    data.setdefault("version", CURRENT_VERSION)
    seeking = data.get("seeking")
    if isinstance(seeking, str):
        data["seeking"] = [seeking] if seeking else []
    return data
