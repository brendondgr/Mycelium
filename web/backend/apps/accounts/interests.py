"""The interests contract — the one validated shape ``Profile.interests`` holds.

Everything that writes interests (the Mylo intake agent, the author importer,
manual admin edits, the API) funnels through :func:`validate_interests`, so a
single gate enforces the schema (brief Phase A). The validator is a DRF
serializer because DRF is already the project's API layer; there is no Pydantic
dependency to reach for.

The shape (``version: 1``):

| Key            | Type      | Required | Feeds                          |
|----------------|-----------|----------|--------------------------------|
| ``version``    | int       | system   | migration safety               |
| ``statement``  | str       | no       | embedding (primary text)       |
| ``areas``      | list[str] | yes      | embedding, keyword overlap     |
| ``methods``    | list[str] | no       | scoring signal, graph          |
| ``keywords``   | list[str] | no       | keyword overlap                |
| ``skills``     | list[str] | no       | fellowship matching            |
| ``funding_needs`` | list[str] | no    | grant matching                 |
| ``eligibility``| dict      | no       | grant/fellowship gating        |
| ``seeking``    | list[str] | no       | fellowship matching (students) |
| ``exclusions`` | list[str] | no       | noise reduction                |
| ``sources``    | dict      | no       | provenance / audit             |
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

CURRENT_VERSION = 1
SUPPORTED_VERSIONS = (1,)


def _str_list(**kwargs: Any) -> serializers.ListField:
    return serializers.ListField(child=serializers.CharField(), **kwargs)


class InterestsContract(serializers.Serializer):
    """Validate one ``Profile.interests`` payload against the v1 contract."""

    version = serializers.IntegerField(required=False)
    statement = serializers.CharField(required=False, allow_blank=True)
    areas = _str_list()  # required: a profile must declare its research areas
    methods = _str_list(required=False)
    keywords = _str_list(required=False)
    skills = _str_list(required=False)
    funding_needs = _str_list(required=False)
    eligibility = serializers.DictField(required=False)
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
