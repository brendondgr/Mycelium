from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.people import display_name, initials

from .interests import validate_interests as _validate_interests_contract
from .models import (
    AcademicTitle,
    DeptProfile,
    LabInvitation,
    LabMembership,
    LabProfile,
    LabWatchPreference,
    Profile,
    WatchPreference,
)
from .services import is_onboarding_complete

# Usernames that collide with top-level routes or reserved app paths.
RESERVED_USERNAMES = frozenset(
    {"login", "logout", "signup", "register", "app", "api", "admin", "me", "auth"}
)


def user_to_dict(user: User) -> dict[str, object]:
    profile = getattr(user, "profile", None)
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "name": display_name(user),
        "initials": initials(user),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "onboarding_completed": is_onboarding_complete(user),
        # Verification is activation: until it is true, the organization
        # endpoints refuse. The app reads it to show the lock up front rather
        # than let someone fill in a lab form that will 403 on save.
        "is_verified": bool(profile and profile.is_verified),
    }


class RegisterSerializer(serializers.Serializer):
    """Validate a registration payload — one person, no organization.

    Sign-up makes a solo account and nothing else. Choosing between a personal, a
    lab, and a department account used to be the *first* thing the form asked,
    before anyone had seen the product or knew which they wanted, and the answer
    quietly fixed their billing scope. Labs and departments are now stood up from
    inside the app, by an account that has proved its own mailbox.

    Password strength is checked through the project's ``AUTH_PASSWORD_VALIDATORS``
    so the policy stays in one place.

    Two write-only fields are *declared* here but judged in the view: the
    invite-only ``access_code`` (``apps.accounts.signup_gate``) and the
    ``invite_token`` that is the other way past it. Both are checked before any of
    this runs, so a bad one costs a strike and never leaks which other fields
    would also have failed.
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
    # Accepted so the payload validates; correctness is the view's job.
    access_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    invite_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
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
        return attrs


class _ContractInterestsMixin(serializers.ModelSerializer):
    """Run ``interests`` through the shared Phase A gate on write."""

    # Columns the ``embed_interest_surface`` pre_save hook re-derives, and the
    # contract/curated inputs that feed them. A save that changes an input must
    # also persist the derived columns; a save that touches neither leaves them
    # alone.
    _EMBED_INPUTS = frozenset({"interests", "statement", "areas", "keywords"})
    _EMBED_OUTPUTS = ("embedding_text", "embedding")

    def validate_interests(self, value):
        # Raises rest_framework ValidationError on any contract violation.
        return _validate_interests_contract(value)

    def update(self, instance, validated_data):
        """Persist only the fields this request changed (plus derived columns).

        The default DRF update writes the whole row, so a basics PATCH would
        write back the ``interests`` it loaded — clobbering a *concurrent*
        interests save (e.g. the three parallel writes onboarding fires on
        finish). Scoping the ``UPDATE`` to the changed columns makes the two
        writes touch disjoint columns, so neither can revert the other.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        update_fields = set(validated_data)
        if not update_fields:
            instance.save()
            return instance
        update_fields.add("updated_at")
        if update_fields & self._EMBED_INPUTS:
            update_fields.update(
                field
                for field in self._EMBED_OUTPUTS
                if hasattr(instance, field)
            )
        instance.save(update_fields=update_fields)
        return instance


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
    # The logo lives on the Lab (LabProfile is OneToOne to it); surface it here
    # read-only so the lab-config editor can show the current mark. Uploads go
    # through LabLogoView, not this serializer.
    has_logo = serializers.BooleanField(source="lab.has_logo", read_only=True)
    logo_version = serializers.IntegerField(
        source="lab.logo_version", read_only=True, allow_null=True
    )

    class Meta:
        model = LabProfile
        fields = [
            "statement",
            "areas",
            "funding_needs",
            "strategic_needs",
            "interests",
            "has_logo",
            "logo_version",
            "embedding_text",
            "updated_at",
        ]
        read_only_fields = ["has_logo", "logo_version", "embedding_text", "updated_at"]


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
    """Read/update what Mylo keeps an eye on for the caller (own only).

    The watch-topic count is capped **per tier** (Free 6, Spore 10, Lab/Canopy 15);
    ``categories`` keeps the generous structural cap. The read payload also reports
    the caller's ``topic_cap`` and whether they are ``topics_over_cap`` (which only
    happens after a downgrade — the excess is honoured on read, never deleted).
    """

    _MAX_ITEMS = 50

    topic_cap = serializers.SerializerMethodField()
    topics_over_cap = serializers.SerializerMethodField()

    class Meta:
        model = WatchPreference
        fields = [
            "topics",
            "categories",
            "cadence",
            "topic_cap",
            "topics_over_cap",
            "updated_at",
        ]
        read_only_fields = ["topic_cap", "topics_over_cap", "updated_at"]

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

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _topic_cap(self) -> int | None:
        """The per-tier watch-topic cap for this serializer, or ``None`` for none."""
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return None
        from apps.billing.entitlements import topic_cap

        return topic_cap(user)

    def get_topic_cap(self, obj) -> int:
        from apps.billing.entitlements import topic_cap

        user = self._request_user()
        if user is None or not user.is_authenticated:
            from apps.billing.entitlements import TOPIC_CAPS, Tier

            return TOPIC_CAPS[Tier.FREE]
        return topic_cap(user)

    def get_topics_over_cap(self, obj) -> bool:
        cap = self.get_topic_cap(obj)
        return len(getattr(obj, "topics", None) or []) > cap

    def validate_topics(self, value: object) -> list[str]:
        cleaned = self._clean_string_list(value, "topics")
        cap = self._topic_cap()
        if cap is not None and len(cleaned) > cap:
            raise serializers.ValidationError(
                {
                    "topics": [
                        f"Your plan allows at most {cap} watch topics. "
                        "Upgrade to monitor more."
                    ]
                }
            )
        return cleaned

    def validate_categories(self, value: object) -> list[str]:
        return self._clean_string_list(value, "categories")


class LabWatchPreferenceSerializer(WatchPreferenceSerializer):
    """Read/update what Mylo keeps an eye on for a lab (same shape as a user's).

    A lab's shared watch list is a team resource, so it keeps only the structural
    ``_MAX_ITEMS`` cap — the per-member tier cap governs each member's *own*
    :class:`WatchPreference`, not the lab's shared one.
    """

    class Meta(WatchPreferenceSerializer.Meta):
        model = LabWatchPreference

    def _topic_cap(self) -> int | None:
        return None  # lab shared watch keeps the structural cap only

    def get_topic_cap(self, obj) -> int:
        return self._MAX_ITEMS

    def get_topics_over_cap(self, obj) -> bool:
        return False


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
    has_logo = serializers.BooleanField(source="lab.has_logo", read_only=True)
    logo_version = serializers.IntegerField(
        source="lab.logo_version", read_only=True, allow_null=True
    )

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


class MyInvitationSerializer(serializers.Serializer):
    """A pending lab invitation addressed to the caller, for the notifications panel."""

    id = serializers.UUIDField(read_only=True)
    lab_slug = serializers.CharField(source="lab.slug", read_only=True)
    lab_name = serializers.CharField(source="lab.name", read_only=True)
    role = serializers.CharField(read_only=True)
    inviter = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_inviter(self, invitation: LabInvitation) -> str | None:
        return display_name(invitation.inviter) if invitation.inviter else None


class LabInvitationSerializer(serializers.Serializer):
    """A lab invitation as seen by a lab manager (roster of sent invites)."""

    id = serializers.UUIDField(read_only=True)
    lab_slug = serializers.CharField(source="lab.slug", read_only=True)
    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    invited_email = serializers.CharField(read_only=True)
    invited_username = serializers.CharField(read_only=True)
    invitee = serializers.SerializerMethodField()
    inviter = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    responded_at = serializers.DateTimeField(read_only=True)

    def get_invitee(self, invitation: LabInvitation) -> str | None:
        return display_name(invitation.invitee) if invitation.invitee else None

    def get_inviter(self, invitation: LabInvitation) -> str | None:
        return display_name(invitation.inviter) if invitation.inviter else None


# -- Account management (name, email, affiliation, password) -------------------


class AccountSerializer(serializers.Serializer):
    """The Account page's one payload: identity split across two tables.

    ``User`` holds the name and the address; ``Profile`` holds the affiliation
    and career stage. The page treats them as one form, so the API does too
    rather than making the client orchestrate two round trips and reconcile a
    half-applied save.

    Username is read-only on purpose. It is the handle lab invitations, audit
    rows, and Discord links resolve against; renaming it is an account-migration
    feature, not a settings field.
    """

    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    pending_email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    institution = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    academic_title = serializers.ChoiceField(
        choices=AcademicTitle.choices, required=False
    )


class _PasswordPolicyMixin:
    """Run a candidate password through ``AUTH_PASSWORD_VALIDATORS``."""

    def _check_policy(self, password: str, field: str, user=None) -> None:
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({field: list(exc.messages)}) from exc


class PasswordChangeSerializer(_PasswordPolicyMixin, serializers.Serializer):
    """Step two of a password change: the emailed code and the new password.

    The current password is deliberately **not** asked for. Control of the
    account's mailbox is the whole proof, exactly as it is for a signed-out
    reset — and it has to be, because the person most likely to be changing a
    password is the person who cannot remember it. Demanding the old one here
    would also have secured nothing: anyone able to satisfy it could sign out
    and take the same account through ``password/reset/``, which never asked.

    A code is still worth one use, expires, and is scoped to this purpose, so it
    cannot be a code the account was sent for something else.
    """

    code = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        self._check_policy(
            attrs["new_password"], "new_password", self.context["user"]
        )
        return attrs


class PasswordResetConfirmSerializer(_PasswordPolicyMixin, serializers.Serializer):
    """The link's uid/token plus the password it is being spent on."""

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs


class EmailChangeSerializer(serializers.Serializer):
    """Start a move to a new address.

    Nothing is written to the account here. The new address has to answer a code
    first, because an address entered with a typo would otherwise take the
    account's password reset with it.

    Unlike a password change, this one *does* ask for the current password, and
    the asymmetry is deliberate. The mailbox is what proves a password change,
    so moving the mailbox is the one move that would let someone bootstrap a
    full takeover out of a borrowed browser — point the account at an address
    they control, then reset. There is no signed-out flow that does this, so the
    check is not redundant here the way it was there.
    """

    new_email = serializers.EmailField()
    current_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context["user"]
        if not user.check_password(value):
            raise serializers.ValidationError("That is not your current password.")
        return value

    def validate_new_email(self, value: str) -> str:
        user = self.context["user"]
        if value.strip().lower() == (user.email or "").strip().lower():
            raise serializers.ValidationError(
                "That is already the address on your account."
            )
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                "An account with that email already exists."
            )
        return value
