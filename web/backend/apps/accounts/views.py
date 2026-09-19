import dataclasses
import json

from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.billing.services import (
    create_department_workspace,
    create_lab_workspace,
    provision_workspace,
    signup_grant_tier,
)

from . import email_verification, institution, invites, password_reset, signup_gate
from .author_works import store_author_works
from .intake import (
    AuthorImportError,
    IntakeAgent,
    ResolutionError,
    extract_text,
    import_author,
    source_text_from_links,
    synthesize_interests,
    synthesize_lab_interests,
)
from .interests import validate_interests
from .models import (
    Department,
    DeptMembership,
    EmailVerification,
    Lab,
    LabInvitation,
    LabMembership,
    LabWatchPreference,
    OrgInvite,
    WatchPreference,
)
from .permissions import (
    require_verified_email,
    user_can_edit_dept_profile,
    user_can_edit_lab_profile,
    user_can_invite_to_department,
    user_can_invite_to_lab,
    user_can_manage_department,
    user_can_manage_lab,
    user_has_department_access,
    user_has_lab_access,
)
from .serializers import (
    AccountSerializer,
    DeptProfileSerializer,
    EmailChangeSerializer,
    LabInvitationSerializer,
    LabMemberSerializer,
    LabProfileSerializer,
    LabWatchPreferenceSerializer,
    MyInvitationSerializer,
    MyLabSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    ProfileSerializer,
    RegisterSerializer,
    WatchPreferenceSerializer,
    institution_fields,
    user_to_dict,
)
from .services import (
    accept_invitation,
    add_dept_member,
    add_lab_member,
    attach_existing_lab_to_department,
    cancel_invitation,
    claim_pending_invitations,
    create_lab_in_department,
    decline_invitation,
    department_labs_payload,
    department_members_payload,
    detach_lab_from_department,
    invite_to_lab,
    record_audit_event,
    remove_dept_member,
    remove_lab_member,
    set_lab_department_inclusion,
    set_lab_member_role,
)

INVALID_CREDENTIALS_MESSAGE = "Invalid username or password."


class RegisterRateThrottle(AnonRateThrottle):
    """Throttle anonymous account creation (rate from DEFAULT_THROTTLE_RATES)."""

    scope = "register"


class EmailVerifyThrottle(UserRateThrottle):
    """Per-account cap on code submissions and resends."""

    scope = "email_verify"


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request: Request) -> Response:
    get_token(request)
    return Response({"detail": "ok"})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))

    if not username or not password:
        return Response(
            {"non_field_errors": ["Enter both username and password."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"non_field_errors": [INVALID_CREDENTIALS_MESSAGE]},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    login(request, user)
    return Response(user_to_dict(user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register_view(request: Request) -> Response:
    """Create one solo account, then log them in.

    Sign-up provisions a personal workspace and nothing else. It no longer asks
    whether the person is a lab or a department, because that question came
    before they had seen anything and its answer set their billing scope for
    them. Labs and departments are created from inside the app by an account that
    has verified its address — see ``MyLabsView`` and ``MyDepartmentsView``.

    Getting in takes one of two proofs, checked before any other validation so a
    bad one costs a strike and reveals nothing about the rest of the payload:

    * the live invite-only ``access_code``, or
    * an ``invite_token`` — someone already inside asked for this person by name.
      An invitation the beta gate can turn away is not an invitation, so a live
      token stands in for the code.

    Three consecutive misses shadow-ban the client for an hour; see
    ``signup_gate`` for why every outcome shares one message.

    After the gate, everything happens inside one transaction — the ``User`` (its
    post_save signal creates the ``Profile``), the personal subscription and
    seat, and the invited membership — so a failure anywhere leaves no half-built
    account behind.

    The account normally starts **unverified**, with a six-digit code on its way
    to the address it was created with; verification is what activates it (see
    ``apps.accounts.permissions``). The exception is an email invitation redeemed
    by the address it was addressed to: Mycelium mailed a secret to that mailbox
    and it came back, which is the same proof the code goes looking for, so the
    account is already activated and is not asked twice.
    """
    subject = signup_gate.client_subject(request)
    banned = signup_gate.is_shadow_banned(subject)
    token = str(request.data.get("invite_token", "") or "").strip()

    invite = None
    if token and not banned:
        try:
            invite = invites.find_invite(token)
        except invites.InviteError as exc:
            return Response(
                {"invite_token": [str(exc)], "reason": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if invite is None and (
        banned or not signup_gate.code_matches(request.data.get("access_code", ""))
    ):
        # Only a genuine miss adds a strike; an attempt made while already banned
        # neither extends the ban nor tells the caller anything new.
        if not banned:
            signup_gate.record_failure(subject)
        return Response(
            {"access_code": [signup_gate.INVALID_CODE_MESSAGE]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    signup_gate.clear_failures(subject)

    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)  # -> 400 with field errors
    data = serializer.validated_data

    # An email invitation is spendable by one address. Check it against what they
    # actually typed before creating anything, so the refusal is a plain field
    # error rather than a rolled-back account.
    if invite is not None:
        try:
            invites.check_email_matches(invite, data["email"])
        except invites.InviteError as exc:
            return Response(
                {"email": [str(exc)], "reason": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    with transaction.atomic():
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],  # hashed by the project's password hashers
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )  # post_save signal creates the Profile

        # Passing the invite-only gate is itself the entitlement: a new account is
        # provisioned on the granted tier rather than on Free, so nobody has to ask
        # for an upgrade they already proved they were invited to.
        result = provision_workspace(
            user, "personal", personal_tier=signup_grant_tier()
        )

        # Surface any lab invitations that were sent to this email before signup.
        claim_pending_invitations(user)

        joined = None
        if invite is not None:
            try:
                invites.redeem(invite, user)
            except invites.InviteError as exc:
                return Response(
                    {"invite_token": [str(exc)], "reason": exc.reason},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            joined = invite
            if invite.kind == OrgInvite.Kind.EMAIL:
                profile = user.profile
                profile.is_verified = True
                profile.save(update_fields=["is_verified"])
                institution.verified_then_sync(user)

        record_audit_event(
            actor=user,
            action="account.register",
            target_type="user",
            target_id=str(user.pk),
            metadata={
                "tier": result.subscription.tier,
                "invite_id": str(joined.id) if joined else None,
                "invited_org": joined.org_kind if joined else None,
            },
        )

    # Outside the transaction: `issue` mails on commit, so a rollback can never
    # leave a live code in a real inbox for an account that does not exist. An
    # account activated by its invitation has nothing left to prove.
    if not user.profile.is_verified:
        email_verification.issue(user, user.email)

    login(request, user)  # set the session immediately, same as login_view
    return Response(user_to_dict(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request: Request) -> Response:
    if not request.user.is_authenticated:
        return Response(status=status.HTTP_204_NO_CONTENT)

    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request: Request) -> Response:
    user = request.user
    if not isinstance(user, User) or not user.is_authenticated:
        return Response(status=status.HTTP_401_UNAUTHORIZED)

    return Response(user_to_dict(user))


# -- Account management: name, email, password --------------------------------


class AccountView(APIView):
    """The Account page's read/write surface for who the user is.

    Identity is split across two tables — ``User`` owns the name and address,
    ``Profile`` owns the affiliation and career stage — but it is one form to the
    person filling it in, so it is one endpoint. Email and password are
    deliberately *not* writable here: each has its own endpoint because each
    needs a proof this one does not ask for.
    """

    def get(self, request: Request) -> Response:
        return Response(_account_payload(request.user))

    def patch(self, request: Request) -> Response:
        refused = _typed_institution_refused(request.user, request.data)
        if refused is not None:
            return refused
        serializer = AccountSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        user_fields = [f for f in ("first_name", "last_name") if f in data]
        if user_fields:
            for field in user_fields:
                setattr(user, field, data[field])
            user.save(update_fields=user_fields)

        profile = user.profile
        profile_fields = [f for f in ("academic_title",) if f in data]
        if profile_fields:
            for field in profile_fields:
                setattr(profile, field, data[field])
            # Scoped to the changed columns: a full-row save here would write
            # back the `interests` this request loaded, clobbering a concurrent
            # profile edit. Same reason the profile serializer scopes its writes.
            profile.save(update_fields=profile_fields)

        return Response(_account_payload(user))


def _typed_institution_refused(user: User, data) -> Response | None:
    """A 400 when a write tries to set an institution the email does not prove.

    The institution is derived (:mod:`apps.accounts.institution`); a request may
    resend the one it was shown, never change it.
    """
    if "institution" not in data:
        return None
    reason = institution.refusal(user, str(data.get("institution") or ""))
    if reason is None:
        return None
    return Response(
        {"institution": [reason], "code": institution.REFUSAL_CODE},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _account_payload(user: User) -> dict[str, object]:
    profile = user.profile
    return {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        **institution_fields(user),
        "academic_title": profile.academic_title,
        "is_verified": profile.is_verified,
        "pending_email": email_verification.pending_email(user),
    }


class PasswordChangeRequestView(APIView):
    """Step one of a password change: mail a confirmation code.

    A signed-in session is not authority to change a password — control of the
    account's mailbox is, and that is the *only* thing asked for. The current
    password is not required, for two reasons that point the same way: the
    person changing a password is very often the person who cannot remember it,
    and anyone who could satisfy such a check could sign out and take the same
    account through ``password/reset/``, which never asked for it either. The
    two routes to a new password therefore demand exactly the same proof.

    Abuse is bounded by the resend cooldown and the per-account throttle rather
    than by a password, matching the signed-out endpoint, which is open to
    anyone who knows an address.
    """

    throttle_classes = [EmailVerifyThrottle]

    def post(self, request: Request) -> Response:
        address = request.user.email
        if not address:
            return Response(
                {"detail": ["Your account has no email address to confirm with."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            email_verification.issue(
                request.user,
                address,
                EmailVerification.Purpose.PASSWORD,
                enforce_cooldown=True,
            )
        except email_verification.ResendTooSoon as exc:
            return Response(
                {"detail": [str(exc)]}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        record_audit_event(
            actor=request.user,
            action="account.password_change_requested",
            target_type="user",
            target_id=str(request.user.pk),
        )
        return Response(
            {"detail": f"We sent a confirmation code to {address}."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordChangeView(APIView):
    """Step two: spend the emailed code on a new password.

    The code is the whole proof, so it has to be a code issued *for this*: it is
    looked up under its own purpose, meaning one sent to verify an address or to
    settle an email change cannot be redirected here.
    """

    throttle_classes = [EmailVerifyThrottle]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        try:
            email_verification.verify(
                user,
                serializer.validated_data["code"],
                EmailVerification.Purpose.PASSWORD,
            )
        except email_verification.VerificationError as exc:
            return Response(
                {"code": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        # Every *other* session dies with the old password hash; this one is
        # re-stamped so the person who just changed it is not signed out of the
        # page they did it from.
        update_session_auth_hash(request, user)

        record_audit_event(
            actor=user,
            action="account.password_change",
            target_type="user",
            target_id=str(user.pk),
        )
        return Response({"detail": "Your password has been changed."})


class EmailChangeView(APIView):
    """Start moving the account to a new address.

    Nothing is written to the account here — the new address is parked on a
    verification row until a code sent to it comes back. An address accepted on
    trust is an address a typo can hand the account's password reset to.
    """

    def post(self, request: Request) -> Response:
        serializer = EmailChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data["new_email"]

        email_verification.issue(
            request.user, new_email, EmailVerification.Purpose.CHANGE
        )
        record_audit_event(
            actor=request.user,
            action="account.email_change_requested",
            target_type="user",
            target_id=str(request.user.pk),
        )
        return Response(
            {
                "detail": f"We sent a code to {new_email}. Enter it to finish.",
                "pending_email": new_email,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@api_view(["POST"])
@throttle_classes([EmailVerifyThrottle])
def email_verify_view(request: Request) -> Response:
    """Submit a six-digit code and activate the account.

    One endpoint for both purposes: a pending address change is settled first if
    there is one, otherwise the code is read as the sign-up confirmation. The
    caller does not have to know which flow it is in, and cannot get it wrong.
    """
    code = str(request.data.get("code", ""))
    purpose = (
        EmailVerification.Purpose.CHANGE
        if email_verification.pending_email(request.user)
        else EmailVerification.Purpose.SIGNUP
    )
    try:
        email_verification.verify(request.user, code, purpose)
    except email_verification.VerificationError as exc:
        return Response(
            {"code": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
        )

    request.user.refresh_from_db()
    record_audit_event(
        actor=request.user,
        action="account.email_verified",
        target_type="user",
        target_id=str(request.user.pk),
        metadata={"purpose": purpose},
    )
    return Response(_account_payload(request.user))


@api_view(["POST"])
@throttle_classes([EmailVerifyThrottle])
def email_resend_view(request: Request) -> Response:
    """Send a fresh code, replacing whatever was outstanding.

    Re-sends to the pending new address when a change is in flight, so the
    button on the "check your inbox" screen always means the inbox that screen
    is talking about.
    """
    pending = email_verification.pending_email(request.user)
    purpose = (
        EmailVerification.Purpose.CHANGE
        if pending
        else EmailVerification.Purpose.SIGNUP
    )
    address = pending or request.user.email
    if not address:
        return Response(
            {"detail": ["Your account has no email address."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        email_verification.issue(
            request.user, address, purpose, enforce_cooldown=True
        )
    except email_verification.ResendTooSoon as exc:
        return Response(
            {"detail": [str(exc)]}, status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    return Response({"detail": f"We sent a new code to {address}.", "email": address})


class EmailCheckThrottle(AnonRateThrottle):
    """Cap on sign-up address lookups (see ``email_check_view``)."""

    scope = "email_check"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([EmailCheckThrottle])
def email_check_view(request: Request) -> Response:
    """Whether an address is free, for the sign-up form to say so early.

    This is an account-enumeration oracle, which is why it is behind the same
    invite code registration is behind: a genuine sign-up already holds it, and
    nobody else can ask. Without the gate the answer would be free to anyone; with
    it, the gate's own shadow-ban budget is what bounds guessing.
    """
    subject = signup_gate.client_subject(request)
    if signup_gate.is_shadow_banned(subject) or not signup_gate.code_matches(
        request.data.get("access_code", "")
    ):
        return Response(
            {"access_code": [signup_gate.INVALID_CODE_MESSAGE]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = str(request.data.get("email", "")).strip()
    try:
        validate_email(email)
    except DjangoValidationError:
        return Response(
            {"email": ["Enter a valid email address."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    taken = User.objects.filter(email__iexact=email).exists()
    return Response({"email": email, "available": not taken})


# -- Password reset by emailed link -------------------------------------------


class PasswordResetThrottle(AnonRateThrottle):
    """Cap on reset requests — each one mails an address the caller chose."""

    scope = "password_reset"


#: The single answer a reset request gets, registered address or not.
RESET_REQUESTED_MESSAGE = (
    "If that email belongs to a Mycelium account, a reset link is on its way."
)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def password_reset_request_view(request: Request) -> Response:
    """Mail a reset link, and say the same thing either way.

    Varying the response on whether the address is registered would turn this
    endpoint into a way to test whether someone has a Mycelium account, so it
    does not vary — not in the body, not in the status.
    """
    email = str(request.data.get("email", "")).strip()
    password_reset.request_reset(email)
    return Response({"detail": RESET_REQUESTED_MESSAGE})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def password_reset_verify_view(request: Request) -> Response:
    """Whether a link is still good, so the page can say so before the form.

    Discovering a dead link only after typing a new password twice is a bad
    enough experience to be worth one extra round trip.
    """
    try:
        password_reset.resolve(
            str(request.data.get("uid", "")), str(request.data.get("token", ""))
        )
    except password_reset.ResetTokenInvalid as exc:
        return Response({"valid": False, "detail": str(exc)})
    return Response({"valid": True})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def password_reset_confirm_view(request: Request) -> Response:
    """Spend a reset link on a new password.

    The token stops verifying the moment the password changes, so the link is
    single-use without a table to write, and every other session for that account
    dies with the old hash.
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        user = password_reset.confirm_reset(
            data["uid"], data["token"], data["password"]
        )
    except password_reset.ResetTokenInvalid as exc:
        return Response(
            {"token": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
        )
    except DjangoValidationError as exc:
        return Response(
            {"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST
        )

    record_audit_event(
        actor=user,
        action="account.password_reset",
        target_type="user",
        target_id=str(user.pk),
    )
    return Response({"detail": "Your password has been reset. Sign in to continue."})


# -- Profile read/update (object-level permissions, brief Phase G) -------------


class MyProfileView(RetrieveUpdateAPIView):
    """A user reads and edits their own profile."""

    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile

    def update(self, request, *args, **kwargs):
        refused = _typed_institution_refused(request.user, request.data)
        if refused is not None:
            return refused
        return super().update(request, *args, **kwargs)


class LabProfileView(RetrieveUpdateAPIView):
    """Lab members read the lab profile; the lead PI / owner / admin edit it."""

    serializer_class = LabProfileSerializer

    def get_object(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_lab_access(user, lab):
                raise PermissionDenied("You do not have access to this lab.")
        elif not user_can_edit_lab_profile(user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this profile.")
        else:
            # Reading a lab you belong to is always fine; building one out is the
            # thing verification activates.
            require_verified_email(user)
        return lab.profile


#: Max lab-logo upload size (2 MB) and the raster/vector types we accept.
LAB_LOGO_MAX_BYTES = 2 * 1024 * 1024


def _lab_logo_payload(lab: Lab) -> dict[str, object]:
    """The write-response shape for the logo endpoint (also the serializer fields)."""
    return {"has_logo": lab.has_logo, "logo_version": lab.logo_version}


def sniff_image_content_type(data: bytes) -> str | None:
    """Return the image content type from magic bytes, or ``None`` if unknown.

    Dependency-free (no Pillow): recognises PNG/JPEG/GIF/WebP by signature and
    SVG by a leading ``<svg``/``<?xml`` marker. SVG is safe here because the logo
    is only ever rendered via ``<img src>`` (scripts inside it never execute) and
    served with ``X-Content-Type-Options: nosniff``.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:512].lstrip().lstrip(b"\xef\xbb\xbf").lstrip()
    if head[:5].lower() == b"<?xml" or head[:4].lower() == b"<svg":
        lowered = data[:4096].lower()
        if b"<svg" in lowered:
            return "image/svg+xml"
    return None


class LabLogoView(APIView):
    """Serve, replace, or clear a lab's logo — served through the API gateway.

    ``GET`` streams the stored file to any lab member. ``POST``/``PUT`` accept a
    multipart ``file`` upload (validated by size + magic bytes) from a lead PI /
    owner / admin. ``DELETE`` clears it. Kept off ``MEDIA_URL`` so no static
    media route or nginx location is needed — the existing ``/api`` gateway
    already reaches the backend.
    """

    parser_classes = [MultiPartParser, FormParser]

    def _lab(self) -> Lab:
        return get_object_or_404(Lab, slug=self.kwargs["slug"])

    def get(self, request: Request, slug: str) -> Response | FileResponse:
        lab = self._lab()
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        if not lab.logo:
            raise Http404("This lab has no logo.")
        response = FileResponse(
            lab.logo.open("rb"),
            content_type=lab.logo_content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response

    def _save(self, request: Request) -> Response:
        lab = self._lab()
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can change the logo.")
        upload = request.FILES.get("file") or request.FILES.get("logo")
        if upload is None:
            return Response(
                {"file": ["No file was uploaded."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > LAB_LOGO_MAX_BYTES:
            return Response(
                {"file": ["The logo must be 2 MB or smaller."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = sniff_image_content_type(upload.read(4096))
        upload.seek(0)
        if content_type is None:
            return Response(
                {"file": ["Use a PNG, JPG, GIF, WebP, or SVG image."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ext = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/svg+xml": "svg",
        }[content_type]
        if lab.logo:
            lab.logo.delete(save=False)
        lab.logo.save(f"{lab.slug}.{ext}", upload, save=False)
        lab.logo_content_type = content_type
        lab.save(update_fields=["logo", "logo_content_type", "updated_at"])
        record_audit_event(
            actor=request.user,
            action="lab.logo.update",
            target_type="lab",
            target_id=str(lab.id),
            metadata={"content_type": content_type},
        )
        return Response(_lab_logo_payload(lab))

    def post(self, request: Request, slug: str) -> Response:
        return self._save(request)

    def put(self, request: Request, slug: str) -> Response:
        return self._save(request)

    def delete(self, request: Request, slug: str) -> Response:
        lab = self._lab()
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can change the logo.")
        if lab.logo:
            lab.logo.delete(save=False)
        lab.logo_content_type = ""
        lab.save(update_fields=["logo", "logo_content_type", "updated_at"])
        return Response(_lab_logo_payload(lab))


class LabWatchView(RetrieveUpdateAPIView):
    """Lab members read what Mylo watches for the lab; the lead / owner / admin edit it.

    The row is auto-created with the lab, but ``get_or_create`` guards labs that
    predate the watch model so an old lab still gets sensible defaults.
    """

    serializer_class = LabWatchPreferenceSerializer

    def get_object(self) -> LabWatchPreference:
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_lab_access(user, lab):
                raise PermissionDenied("You do not have access to this lab.")
        elif not user_can_edit_lab_profile(user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this.")
        watch, _ = LabWatchPreference.objects.get_or_create(lab=lab)
        return watch


class DeptProfileView(RetrieveUpdateAPIView):
    """Department members read the dept profile; the owner / admin edit it."""

    serializer_class = DeptProfileSerializer

    def get_object(self):
        department = get_object_or_404(Department, id=self.kwargs["pk"])
        user = self.request.user
        if self.request.method in SAFE_METHODS:
            if not user_has_department_access(user, department):
                raise PermissionDenied("You do not have access to this department.")
        elif not user_can_edit_dept_profile(user, department):
            raise PermissionDenied("Only the owner or an admin can edit this profile.")
        else:
            require_verified_email(user)
        return department.profile


class MyWatchView(RetrieveUpdateAPIView):
    """Read or update what Mylo keeps an eye on for the caller (own only).

    The row is created on first access, so a user who never finished the watch
    step still gets sensible defaults (weekly cadence, no topics).
    """

    serializer_class = WatchPreferenceSerializer

    def get_object(self) -> WatchPreference:
        watch, _ = WatchPreference.objects.get_or_create(user=self.request.user)
        return watch


# -- Lab membership reads (workspace switcher + members list) ------------------


class MyLabsView(ListAPIView):
    """List the caller's labs, or create a new one with the caller as PI.

    ``GET`` returns the caller's memberships (workspace switcher). ``POST`` lets
    an existing user start another lab: it provisions the lab, makes them
    OWNER + PI lead, and returns the new membership in the same ``MyLab`` shape.
    """

    serializer_class = MyLabSerializer

    def get_queryset(self):
        return (
            LabMembership.objects.filter(user=self.request.user)
            .select_related("lab", "lab__department")
            .order_by("lab__name")
        )

    def post(self, request: Request) -> Response:
        # An unactivated account does not get to stand up an organization: a lab
        # exists to invite people into, and inviting from an address nobody has
        # answered is how Mycelium's mail becomes someone else's spam problem.
        require_verified_email(request.user)
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"name": ["A lab name is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = create_lab_workspace(request.user, name)
        record_audit_event(
            actor=request.user,
            action="lab.create",
            target_type="lab",
            target_id=str(result.lab.id),
            metadata={"name": name},
        )
        membership = (
            LabMembership.objects.select_related("lab", "lab__department")
            .get(user=request.user, lab=result.lab)
        )
        return Response(
            MyLabSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class LabMembersView(ListAPIView):
    """A lab's member roster: any member reads; a manager adds an existing user.

    ``GET`` lists members. ``POST {username, role}`` adds an existing user directly
    (distinct from an emailed invitation) and seats them on the lab's paying scope; a
    seat-ceiling breach returns 400.
    """

    serializer_class = LabMemberSerializer

    def get_queryset(self):
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_has_lab_access(self.request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        return (
            LabMembership.objects.filter(lab=lab)
            .select_related("user")
            .order_by("-is_lead", "user__username")
        )

    def post(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_manage_lab(request.user, lab):
            raise PermissionDenied("Only a lab owner or admin can add members.")
        username = str(request.data.get("username", "")).strip()
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "") or LabMembership.Role.MEMBER)
        membership = add_lab_member(lab, target, role=role, actor=request.user)
        return Response(
            LabMemberSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class LabMemberDetailView(APIView):
    """A lab manager changes a member's role or removes them (deferred seat removal)."""

    def _managed_lab(self, slug: str) -> Lab:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_manage_lab(self.request.user, lab):
            raise PermissionDenied("Only a lab owner or admin can manage members.")
        return lab

    def patch(self, request: Request, slug: str, username: str) -> Response:
        lab = self._managed_lab(slug)
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "")).strip()
        membership = set_lab_member_role(lab, target, role, actor=request.user)
        return Response(LabMemberSerializer(membership).data)

    def delete(self, request: Request, slug: str, username: str) -> Response:
        lab = self._managed_lab(slug)
        target = get_object_or_404(User, username=username)
        owners = LabMembership.objects.filter(lab=lab, role=LabMembership.Role.OWNER)
        if owners.filter(user=target).exists() and owners.count() == 1:
            return Response(
                {"detail": "A lab must keep at least one owner."},
                status=status.HTTP_409_CONFLICT,
            )
        remove_lab_member(lab, target, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- Lab invitations -----------------------------------------------------------


class LabInvitationsView(APIView):
    """A lab manager lists the lab's invitations and invites new people.

    Only a PI (lead) or owner/admin may invite or see the invitation roster.
    Invite by email (matched to an account, else kept pending) or by username.
    """

    def _get_lab(self) -> Lab:
        lab = get_object_or_404(Lab, slug=self.kwargs["slug"])
        if not user_can_invite_to_lab(self.request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        return lab

    def get(self, request: Request, slug: str) -> Response:
        lab = self._get_lab()
        invitations = lab.invitations.select_related(
            "lab", "invitee", "inviter"
        ).all()
        return Response(LabInvitationSerializer(invitations, many=True).data)

    def post(self, request: Request, slug: str) -> Response:
        lab = self._get_lab()
        # Sending an invitation puts Mycelium's name in a stranger's inbox on
        # this account's behalf. Answer your own mail first.
        require_verified_email(request.user)
        invitation = invite_to_lab(
            lab=lab,
            inviter=request.user,
            identifier=str(request.data.get("identifier", "")),
            role=str(request.data.get("role", "") or LabMembership.Role.MEMBER),
        )  # raises ValidationError -> 400 on bad input / duplicate / member
        return Response(
            LabInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class MyInvitationsView(ListAPIView):
    """The caller's pending lab invitations — the notifications-panel feed."""

    serializer_class = MyInvitationSerializer

    def get_queryset(self):
        return (
            LabInvitation.objects.filter(
                invitee=self.request.user,
                status=LabInvitation.Status.PENDING,
            )
            .select_related("lab", "inviter")
            .order_by("-created_at")
        )


class InvitationRespondView(APIView):
    """The invitee accepts, rejects, or ignores one of their invitations."""

    def post(self, request: Request, pk) -> Response:
        invitation = get_object_or_404(LabInvitation, pk=pk)
        if invitation.invitee_id != request.user.id:
            raise PermissionDenied("This invitation is not addressed to you.")
        if invitation.status != LabInvitation.Status.PENDING:
            return Response(
                {"detail": "This invitation has already been answered."},
                status=status.HTTP_409_CONFLICT,
            )

        action = str(request.data.get("action", "")).strip().lower()
        if action == "accept":
            accept_invitation(invitation, request.user)
        elif action == "reject":
            decline_invitation(invitation, request.user, ignore=False)
        elif action == "ignore":
            decline_invitation(invitation, request.user, ignore=True)
        else:
            return Response(
                {"action": ["Must be one of: accept, reject, ignore."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"id": str(invitation.id), "status": invitation.status})


class LabInvitationCancelView(APIView):
    """A lab manager withdraws a pending invitation they sent."""

    def post(self, request: Request, slug: str, pk) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_invite_to_lab(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        invitation = get_object_or_404(LabInvitation, pk=pk, lab=lab)
        cancel_invitation(invitation, actor=request.user)  # 400 if not pending
        return Response({"id": str(invitation.id), "status": invitation.status})


# -- Department members & labs -------------------------------------------------


class DeptMembersView(APIView):
    """Effective dept roster (any member reads); a manager adds a direct member."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        return Response(department_members_payload(department))

    def post(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can add members.")
        username = str(request.data.get("username", "")).strip()
        target = get_object_or_404(User, username=username)
        role = str(request.data.get("role", "") or DeptMembership.Role.MEMBER)
        add_dept_member(department, target, role=role, actor=request.user)
        return Response(
            department_members_payload(department), status=status.HTTP_201_CREATED
        )


class DeptMemberDetailView(APIView):
    """A department manager removes a direct member (deferred seat removal)."""

    def delete(self, request: Request, pk, username: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can remove members.")
        target = get_object_or_404(User, username=username)
        if department.owner_id == target.id:
            return Response(
                {"detail": "The department owner cannot be removed."},
                status=status.HTTP_409_CONFLICT,
            )
        remove_dept_member(department, target, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeptLabsView(APIView):
    """Labs under a department (any member reads); a manager attaches or creates one."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        return Response(department_labs_payload(department))

    def post(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can add labs.")
        require_verified_email(request.user)
        slug = str(request.data.get("slug", "")).strip()
        name = str(request.data.get("name", "")).strip()
        if slug:
            lab = get_object_or_404(Lab, slug=slug)
            attach_existing_lab_to_department(department, lab, actor=request.user)
        elif name:
            create_lab_in_department(department, name, request.user, actor=request.user)
        else:
            return Response(
                {"detail": ["Provide a lab name to create, or a slug to attach."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            department_labs_payload(department), status=status.HTTP_201_CREATED
        )


class DeptLabDetailView(APIView):
    """A department manager detaches a lab, or toggles its inclusion in the plan."""

    def patch(self, request: Request, pk, slug: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can change a lab's plan.")
        lab = get_object_or_404(Lab, slug=slug)
        if "included_in_plan" not in request.data:
            return Response(
                {"included_in_plan": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        set_lab_department_inclusion(
            department, lab, bool(request.data.get("included_in_plan")), actor=request.user
        )
        return Response(department_labs_payload(department))

    def delete(self, request: Request, pk, slug: str) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can detach labs.")
        lab = get_object_or_404(Lab, slug=slug)
        detach_lab_from_department(department, lab, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- Author import + intake session (brief Phase G) ---------------------------


class ImportAuthorView(APIView):
    """Build an interest-profile draft from an external author id (no save)."""

    def post(self, request: Request) -> Response:
        identifier = str(request.data.get("identifier", "")).strip()
        source = str(request.data.get("source", "")).strip()
        if not identifier or not source:
            return Response(
                {"non_field_errors": ["'identifier' and 'source' are required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            draft = import_author(identifier, source)
        except ResolutionError as exc:
            return Response(
                {"non_field_errors": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except AuthorImportError as exc:
            return Response(
                {"non_field_errors": [str(exc)]},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        # The draft is a preview and nothing here saves a profile. The *works*
        # are stored, because the import already read them and throwing them away
        # is what left the reports unable to tell a reader's own paper from a
        # discovery (plan M9). Keyed on (user, source, work id), so a re-import
        # updates in place rather than accumulating copies.
        store_author_works(request.user, draft, source=source)
        return Response(
            {
                "draft": _draft_payload(request.user, draft),
                "interests": draft.to_interests(),
            }
        )


class IntakeSessionView(APIView):
    """Drive one step of the bounded intake loop (stateless across requests).

    The client round-trips the accumulating ``interests``; the agent re-derives
    which fields are still thin each call, so no server-side session is stored.
    """

    def post(self, request: Request) -> Response:
        interests = request.data.get("interests") or {}
        free_text = str(request.data.get("free_text", ""))
        answer = request.data.get("answer")

        agent = IntakeAgent()
        state = agent.start(free_text=free_text, seed_interests=interests)
        if answer is not None and not state.done:
            state = agent.answer(state, str(answer))

        return Response(
            {
                "interests": state.interests,
                "question": agent.question(state),
                "summary": agent.summary(state),
                "done": state.done,
            }
        )


class ConfirmIntakeView(APIView):
    """Validate gathered interests against the contract and save the own profile."""

    def post(self, request: Request) -> Response:
        interests = request.data.get("interests") or {}
        validated = validate_interests(interests)  # 400 on contract violation
        profile = request.user.profile
        profile.interests = validated
        # Scope the write to interests + the columns the pre_save embed hook
        # re-derives, so a concurrent basics PATCH (onboarding fires both at
        # once) can't clobber interests and this can't clobber the basics.
        profile.save(
            update_fields=["interests", "embedding_text", "embedding", "updated_at"]
        )
        return Response(ProfileSerializer(profile).data)


class ProposeClustersView(APIView):
    """Propose (or re-sort) interest clusters for the "Organize your interests" step.

    Three modes on one POST:
      - **Instruct** ``{instruction, clusters?, areas?, keywords?, statement?,
        watch_topics?}`` → build theme→sub-topic clusters from a free-text
        description, refining the caller's current clusters (ids preserved for a
        persisting theme) — the "Build clusters with Mylo" box. May **invent**
        concrete sub-topics, so it returns a widened ``areas`` union too.
      - **Propose** ``{areas, keywords?, statement?}`` → group the areas into named
        clusters (LLM, geometric fallback) — the intake / "organize" affordance.
      - **Sort** ``{clusters, unsorted}`` → route the ``unsorted`` new areas into the
        existing clusters (ids preserved) — the profile-edit "sort these" affordance.

    Always returns ``{clusters: [{id, label, areas}], areas: [...],
    watch_topics: [...], source}`` where ``areas`` is the union the clusters
    partition (unchanged for propose/sort, widened for instruct) and
    ``watch_topics`` is the per-cluster seed the caller prefills for what Mylo
    watches. Pure per-user; no lab scope.
    """

    def post(self, request: Request) -> Response:
        from apps.billing.entitlements import (
            cluster_cap,
            cluster_topic_cap,
            topic_cap,
        )
        from apps.content.clustering import seed_watch_topics

        from .intake.clusters import (
            compose_clusters,
            propose_clusters,
            sort_into_clusters,
        )

        data = request.data or {}
        existing = data.get("clusters") or []
        unsorted = data.get("unsorted") or []
        instruction = str(data.get("instruction") or "").strip()
        if instruction:
            clusters, source = compose_clusters(
                instruction=instruction,
                areas=data.get("areas") or [],
                keywords=data.get("keywords") or [],
                statement=str(data.get("statement") or ""),
                existing_clusters=existing,
                watch_topics=data.get("watch_topics") or [],
                max_clusters=cluster_cap(request.user),
                max_areas_per_cluster=cluster_topic_cap(request.user),
            )
        elif existing and unsorted:
            clusters = sort_into_clusters(existing, unsorted)
            source = "sorted"
        else:
            clusters, source = propose_clusters(
                data.get("areas") or [],
                keywords=data.get("keywords") or [],
                statement=str(data.get("statement") or ""),
            )
        areas = [area for cluster in clusters for area in cluster["areas"]]
        # Seed only as many watch topics as the caller's tier can actually save,
        # so a proposal never prefills more than the watch step will accept.
        watch_topics = seed_watch_topics(
            {"areas": areas, "clusters": clusters}, cap=topic_cap(request.user)
        )
        return Response(
            {
                "clusters": clusters,
                "areas": areas,
                "watch_topics": watch_topics,
                "source": source,
            }
        )


# Sources the onboarding import box accepts. Exactly one site may be used per
# synthesize call (a single ``source`` field); a résumé is additive (brief D4).
SYNTHESIZE_SOURCES = {"openalex", "semantic", "scholar", "orcid"}


class SynthesizeView(APIView):
    """Build one interest draft from an optional author id and/or a résumé upload.

    Accepts ``multipart/form-data`` with optional ``source`` + ``identifier`` (at
    most one site) and an optional ``resume`` file; at least one source is
    required. Imports the site, parses the résumé, merges them, and drafts a
    natural-language statement — then returns ``{draft, interests}`` without
    saving (``confirm`` performs the save). Résumé bytes are parsed and discarded.
    """

    def post(self, request: Request) -> Response:
        source = str(request.data.get("source", "")).strip().lower()
        identifier = str(request.data.get("identifier", "")).strip()
        upload = request.FILES.get("resume")

        has_site = bool(source or identifier)
        if has_site and (not source or not identifier):
            return Response(
                {
                    "non_field_errors": [
                        "Provide both 'source' and 'identifier' to import from a site."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if source and source not in SYNTHESIZE_SOURCES:
            return Response(
                {"source": [f"unknown source {source!r}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not has_site and upload is None:
            return Response(
                {
                    "non_field_errors": [
                        "Provide an author id (source + identifier) and/or a "
                        "résumé file."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        site_draft = None
        resume_text = ""
        provenance: dict[str, str] = {}

        if has_site:
            try:
                site_draft = import_author(identifier, source)
            except ResolutionError as exc:
                return Response(
                    {"non_field_errors": [str(exc)]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except AuthorImportError as exc:
                return Response(
                    {"non_field_errors": [str(exc)]},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        if upload is not None:
            try:
                resume_text = extract_text(
                    upload.read(),
                    content_type=getattr(upload, "content_type", "") or "",
                    filename=getattr(upload, "name", "") or "",
                )
            except AuthorImportError as exc:
                # A bad upload is the caller's error, not an upstream failure.
                return Response(
                    {"resume": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )
            provenance["resume"] = "uploaded"

        # The LLM reads the gathered text and fills every field in one call; the
        # structured draft is the deterministic fallback when no model is up.
        # Clamp to the caller's plan so the organize step opens with a grouping
        # they can save outright rather than an overflowing Unsorted tray.
        from apps.billing.entitlements import cluster_cap, cluster_topic_cap

        draft, interests = synthesize_interests(
            site_draft=site_draft,
            resume_text=resume_text,
            provenance=provenance,
            max_clusters=cluster_cap(request.user),
            max_areas_per_cluster=cluster_topic_cap(request.user),
        )
        return Response(
            {"draft": _draft_payload(request.user, draft), "interests": interests}
        )


def _draft_payload(user: User, draft) -> dict:
    """A draft as the client sees it, carrying only the institution the account's
    verified email proves — an author record or résumé may name one, but naming
    is not proof (:mod:`apps.accounts.institution`)."""
    payload = dataclasses.asdict(draft)
    payload["institution"] = institution.sync(user)
    return payload


def _as_str_list(value) -> list[str]:
    """Normalize a field to a list of non-empty strings.

    Handles a real list, a JSON-encoded array string, or a plain string with
    newline/comma-separated items (how the multipart form sends areas + links).
    """
    if isinstance(value, (list, tuple)):
        items = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        else:
            items = [part for chunk in text.splitlines() for part in chunk.split(",")]
    else:
        return []
    return [s for s in (str(item).strip() for item in items) if s]


class LabIntakeSynthesizeView(APIView):
    """Draft a lab's ``{statement, areas, keywords}`` from the PI's own words.

    Accepts ``multipart/form-data`` (or JSON): the lab ``description``, any
    ``areas`` already typed, uploaded source ``files`` (résumés, papers — parsed
    to text and discarded), and pasted source ``links`` (Google Scholar /
    Semantic Scholar / OpenAlex / ORCID profiles, imported best-effort). The LLM
    reads it all and fills the fields; a deterministic fallback keeps the flow
    working with no model. Nothing is saved — the client reviews, then PATCHes.
    """

    def post(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can edit this profile.")

        description = str(request.data.get("description", "")).strip()
        areas_hint = _as_str_list(request.data.get("areas"))
        links = _as_str_list(request.data.get("links"))
        uploads = request.FILES.getlist("files")

        # Assemble source material: pasted-link imports + extracted file text.
        source_chunks: list[str] = []
        if links:
            link_text = source_text_from_links(links)
            if link_text:
                source_chunks.append(link_text)
        for upload in uploads:
            try:
                text = extract_text(
                    upload.read(),
                    content_type=getattr(upload, "content_type", "") or "",
                    filename=getattr(upload, "name", "") or "",
                )
            except AuthorImportError:
                continue  # skip an unreadable file rather than fail the draft
            if text.strip():
                source_chunks.append(text)
        source_text = "\n\n".join(source_chunks).strip()

        if not description and not source_text and not areas_hint:
            return Response(
                {
                    "non_field_errors": [
                        "Describe the lab or add focus areas / source material "
                        "to synthesize a profile."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = synthesize_lab_interests(
            description=description,
            areas_hint=areas_hint,
            source_text=source_text,
        )
        return Response(result)


# -- Standing up an organization, and inviting people into it ------------------
#
# Both live behind ``require_verified_email``. Sign-up no longer asks whether
# someone is a lab or a department, so this is where those exist now, and the
# gate is the same one for both: an account that has not answered its own mailbox
# does not get to stand up an org and start mailing strangers from it.


class MyDepartmentsView(APIView):
    """The caller's departments, and the endpoint that creates one.

    The department sibling of ``MyLabsView``. ``GET`` lists the departments the
    caller owns or is a direct member of — the ones they can act on, not the ones
    they are merely folded into through a lab, which would put a management page
    in front of someone with no authority over it.
    """

    def get(self, request: Request) -> Response:
        owned = Department.objects.filter(owner=request.user)
        joined = Department.objects.filter(memberships__user=request.user)
        departments = (owned | joined).distinct().order_by("name")
        return Response([_department_row(d, request.user) for d in departments])

    def post(self, request: Request) -> Response:
        require_verified_email(request.user)
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"name": ["A department name is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # A department sits at its creator's verified institution; a typed one
        # that differs is refused, the same rule as a person's own.
        refused = _typed_institution_refused(request.user, request.data)
        if refused is not None:
            return refused
        held = institution.sync(request.user)
        result = create_department_workspace(request.user, name, institution=held)
        record_audit_event(
            actor=request.user,
            action="department.create",
            target_type="department",
            target_id=str(result.department.id),
            metadata={"name": name, "institution": held},
        )
        return Response(
            _department_row(result.department, request.user),
            status=status.HTTP_201_CREATED,
        )


def _department_row(department: Department, user: User) -> dict[str, object]:
    """One department as the app's department list wants it."""
    role = DeptMembership.Role.OWNER if department.owner_id == user.id else None
    if role is None:
        membership = DeptMembership.objects.filter(
            department=department, user=user
        ).first()
        role = membership.role if membership else DeptMembership.Role.MEMBER
    return {
        "id": str(department.id),
        "name": department.name,
        "institution": department.institution,
        "role": role,
        "is_owner": department.owner_id == user.id,
        "can_manage": user_can_manage_department(user, department),
    }


class _OrgInvitesView(APIView):
    """Shared list/create behaviour for a lab's and a department's invitations.

    Subclasses resolve the org and say who may manage its invitations; everything
    else — the verification gate, the payload, the response shape — is identical,
    because from the invitee's side a lab invitation and a department invitation
    are the same object with a different name on it.
    """

    def _resolve(self, **kwargs):
        raise NotImplementedError

    def _target(self, org) -> dict:
        raise NotImplementedError

    def get(self, request: Request, **kwargs) -> Response:
        org = self._resolve(**kwargs)
        rows = org.join_invites.select_related("created_by").all()
        return Response([invites.invite_payload(row) for row in rows])

    def post(self, request: Request, **kwargs) -> Response:
        """Create one invitation, or a batch of emailed ones.

        Two payload shapes on one route rather than a second route beside it: an
        ``emails`` list takes the batch path, a bare ``email`` takes the original
        single-invite path unchanged. A second route would have had to repeat the
        org resolution and the authority check that ``_resolve`` already does.

        The verification gate runs before the payload is read at all, so an
        unactivated account cannot learn from an error message whether an address
        is already a member.
        """
        org = self._resolve(**kwargs)
        require_verified_email(request.user)
        target = self._target(org)

        if "emails" in request.data:
            batch = invites.create_invites(
                creator=request.user,
                emails=request.data.get("emails"),
                role=str(request.data.get("role", "") or OrgInvite.Role.MEMBER),
                message=str(request.data.get("message", "")),
                **target,
            )  # raises ValidationError -> 400 when the batch itself is wrong
            return Response(
                {
                    "created": [
                        invites.invite_payload(row) for row in batch.created
                    ],
                    "failed": batch.failed,
                    "requested": batch.requested,
                },
                status=status.HTTP_201_CREATED,
            )

        invite = invites.create_invite(
            creator=request.user,
            kind=str(request.data.get("kind", "")),
            email=str(request.data.get("email", "")),
            role=str(request.data.get("role", "") or OrgInvite.Role.MEMBER),
            max_uses=request.data.get("max_uses"),
            expires_in_days=request.data.get("expires_in_days"),
            message=str(request.data.get("message", "")),
            **target,
        )  # raises ValidationError -> 400 on anything the creator can fix
        return Response(
            invites.invite_payload(invite), status=status.HTTP_201_CREATED
        )


class LabInvitesView(_OrgInvitesView):
    """A lab's join invitations: `GET` lists them, `POST` creates one."""

    def _resolve(self, slug: str, **kwargs) -> Lab:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_invite_to_lab(self.request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        return lab

    def _target(self, org) -> dict:
        return {"lab": org}


class DeptInvitesView(_OrgInvitesView):
    """A department's join invitations: `GET` lists them, `POST` creates one."""

    def _resolve(self, pk, **kwargs) -> Department:
        department = get_object_or_404(Department, id=pk)
        if not user_can_invite_to_department(self.request.user, department):
            raise PermissionDenied(
                "Only the department owner or an admin can manage invitations."
            )
        return department

    def _target(self, org) -> dict:
        return {"department": org}


class LabInviteRevokeView(APIView):
    """Withdraw one of a lab's join invitations."""

    def post(self, request: Request, slug: str, pk) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_invite_to_lab(request.user, lab):
            raise PermissionDenied("Only a lab lead or admin can manage invitations.")
        invite = get_object_or_404(OrgInvite, pk=pk, lab=lab)
        invites.revoke_invite(invite, actor=request.user)
        return Response(invites.invite_payload(invite))


class DeptInviteRevokeView(APIView):
    """Withdraw one of a department's join invitations."""

    def post(self, request: Request, pk, invite_id) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_invite_to_department(request.user, department):
            raise PermissionDenied(
                "Only the department owner or an admin can manage invitations."
            )
        invite = get_object_or_404(OrgInvite, pk=invite_id, department=department)
        invites.revoke_invite(invite, actor=request.user)
        return Response(invites.invite_payload(invite))


@api_view(["GET"])
@permission_classes([AllowAny])
def invite_preview_view(request: Request, token: str) -> Response:
    """What the join page shows someone holding a link — signed in or not.

    Anonymous by necessity: the whole point is that the recipient may not have an
    account yet, and a page that will not say what it is inviting them to before
    they register is a page nobody registers from. What it discloses is bounded by
    what the token holder already has — the org's name, who invited them, and (for
    an email invite) the address it is spendable by.

    A dead link answers `410` with a machine-readable ``reason`` so the page can
    tell "withdrawn" from "expired" from "already used" instead of shrugging.
    """
    try:
        invite = invites.find_invite(token)
    except invites.InviteError as exc:
        return Response(
            {"detail": str(exc), "reason": exc.reason},
            status=status.HTTP_410_GONE,
        )
    payload = invites.preview_payload(invite)
    user = request.user
    if user.is_authenticated:
        payload["signed_in_as"] = user.email
        payload["email_matches"] = (
            invite.kind != OrgInvite.Kind.EMAIL
            or (user.email or "").strip().lower() == invite.email
        )
    return Response(payload)


class InviteAcceptView(APIView):
    """A signed-in account spends an invitation and joins the org.

    Deliberately *not* behind ``require_verified_email``. Verification gates
    standing an organization up and mailing from it; joining one you were invited
    to is the opposite direction, and refusing it would strand exactly the people
    an invitation exists to bring in.
    """

    def post(self, request: Request, token: str) -> Response:
        try:
            invite = invites.redeem_token(token, request.user)
        except invites.InviteError as exc:
            return Response(
                {"detail": str(exc), "reason": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "org_kind": invite.org_kind,
                "org_name": invite.org_name,
                "slug": invite.lab.slug if invite.lab_id else None,
                "department_id": (
                    str(invite.department_id) if invite.department_id else None
                ),
                "role": invite.role,
            }
        )
