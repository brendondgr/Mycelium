from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.billing.services import ACCOUNT_TYPES
from apps.core.people import display_name, initials

from .interests import validate_interests as _validate_interests_contract
from .models import DeptProfile, LabMembership, LabProfile, Profile, WatchPreference
from .services import is_onboarding_complete

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
        "onboarding_completed": is_onboarding_complete(user),
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


class WatchPreferenceSerializer(serializers.ModelSerializer):
    """Read/update what Milo keeps an eye on for the caller (own only)."""

    _MAX_ITEMS = 50

    class Meta:
        model = WatchPreference
        fields = ["topics", "categories", "cadence", "updated_at"]
        read_only_fields = ["updated_at"]

    def _clean_string_list(self, value: object, field: str) -> list[str]:
        if not isinstance(value, list):
            raise serializers.ValidationError({field: ["must be a list of strings"]})
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item).split())
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                cleaned.append(text)
        if len(cleaned) > self._MAX_ITEMS:
            raise serializers.ValidationError(
                {field: [f"at most {self._MAX_ITEMS} items"]}
            )
        return cleaned

    def validate_topics(self, value: object) -> list[str]:
        return self._clean_string_list(value, "topics")

    def validate_categories(self, value: object) -> list[str]:
        return self._clean_string_list(value, "categories")


class MyLabSerializer(serializers.Serializer):
    """One of the caller's lab memberships, for the workspace switcher.

    Serialized from a :class:`LabMembership` so the caller's ``role`` and
    ``is_lead`` (PI) flag travel with the lab. The frontend turns these into a
    display label; the backend stays honest and sends the raw role.
    """

    slug = serializers.CharField(source="lab.slug")
    name = serializers.CharField(source="lab.name")
    role = serializers.CharField()
    is_lead = serializers.BooleanField()
    department = serializers.SerializerMethodField()

    def get_department(self, membership: LabMembership):
        dept = membership.lab.department
        return dept.name if dept else None


class LabMemberSerializer(serializers.Serializer):
    """A lab member as a read-only display row (from a ``LabMembership``)."""

    username = serializers.CharField(source="user.username")
    name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    email = serializers.CharField(source="user.email")
    role = serializers.CharField()
    is_lead = serializers.BooleanField()

    def get_name(self, membership: LabMembership) -> str:
        return display_name(membership.user)

    def get_initials(self, membership: LabMembership) -> str:
        return initials(membership.user)
