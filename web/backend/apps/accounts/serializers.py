from django.contrib.auth.models import User
from rest_framework import serializers

from .interests import validate_interests as _validate_interests_contract
from .models import DeptProfile, LabProfile, Profile


def user_to_dict(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


class _ContractInterestsMixin(serializers.ModelSerializer):
    """Run ``interests`` through the shared Phase A gate on write."""

    def validate_interests(self, value):
        # Raises rest_framework ValidationError on any contract violation.
        return _validate_interests_contract(value)


class ProfileSerializer(_ContractInterestsMixin):
    """Read/update a user's own research profile (brief G).

    ``embedding`` is intentionally excluded (vector dimension deferred); the
    canonical ``embedding_text`` is exposed read-only for transparency.
    """

    class Meta:
        model = Profile
        fields = [
            "academic_title",
            "institution",
            "orcid",
            "openalex_id",
            "scholar_id",
            "interests",
            "embedding_text",
            "updated_at",
        ]
        read_only_fields = ["embedding_text", "updated_at"]


class LabProfileSerializer(_ContractInterestsMixin):
    class Meta:
        model = LabProfile
        fields = [
            "statement",
            "areas",
            "funding_needs",
            "strategic_needs",
            "interests",
            "embedding_text",
            "updated_at",
        ]
        read_only_fields = ["embedding_text", "updated_at"]


class DeptProfileSerializer(_ContractInterestsMixin):
    class Meta:
        model = DeptProfile
        fields = [
            "statement",
            "areas",
            "funding_needs",
            "strategic_needs",
            "interests",
            "embedding_text",
            "updated_at",
        ]
        read_only_fields = ["embedding_text", "updated_at"]
