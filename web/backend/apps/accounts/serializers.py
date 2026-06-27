from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.billing.services import ACCOUNT_TYPES

from .interests import validate_interests as _validate_interests_contract
from .models import DeptProfile, LabProfile, Profile

# Usernames that collide with top-level routes or reserved app paths.
RESERVED_USERNAMES = frozenset(
    {"login", "logout", "signup", "register", "app", "api", "admin", "me", "auth"}
)


def user_to_dict(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


class RegisterSerializer(serializers.Serializer):
    """Validate a registration payload (identity + account type).

    Identity fields are always required; ``org_name`` is required only for lab
    and department accounts. Password strength is checked through the project's
    ``AUTH_PASSWORD_VALIDATORS`` so the policy stays in one place.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    account_type = serializers.ChoiceField(choices=ACCOUNT_TYPES)
    # Required only for lab / department (checked in validate()).
    org_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    institution = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )

    def validate_username(self, value: str) -> str:
        if value.strip().lower() in RESERVED_USERNAMES:
            raise serializers.ValidationError("That username is reserved.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_email(self, value: str) -> str:
        # Django's User.email is not unique by default — enforce it here.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with that email already exists."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        try:
            validate_password(attrs["password"])  # AUTH_PASSWORD_VALIDATORS
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"password": list(exc.messages)}
            ) from exc
        if attrs["account_type"] in ("lab", "department") and not attrs.get(
            "org_name", ""
        ).strip():
            label = "lab" if attrs["account_type"] == "lab" else "department"
            raise serializers.ValidationError(
                {"org_name": f"A {label} name is required."}
            )
        return attrs


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
            "is_verified",
            "embedding_text",
            "updated_at",
        ]
        read_only_fields = ["is_verified", "embedding_text", "updated_at"]


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
