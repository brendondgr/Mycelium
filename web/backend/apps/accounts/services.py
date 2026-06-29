from django.contrib.auth.models import User
from django.db.models import QuerySet

from .models import AuditEvent, Department, DeptMembership, Lab, LabMembership


def record_audit_event(
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str = "",
    metadata: dict | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )


def is_onboarding_complete(user: User) -> bool:
    """True once the user has finished profile onboarding.

    The intake confirm step (``POST /api/auth/intake/confirm/``) persists
    ``Profile.interests`` with a required, non-empty ``areas`` list. Its presence
    is the canonical "onboarded" marker: a freshly registered user starts with an
    empty interests dict and only gains ``areas`` after completing onboarding.
    """
    profile = getattr(user, "profile", None)
    if profile is None:
        return False
    return bool((profile.interests or {}).get("areas"))


def get_lab_for_user(user: User, slug: str) -> Lab | None:
    if user.is_superuser:
        return Lab.objects.filter(slug=slug).first()

    return (
        Lab.objects.filter(slug=slug, memberships__user=user)
        .distinct()
        .first()
    )


def effective_member_ids(department: Department) -> set[int]:
    """Derive a department's effective membership (briefing §4, decision D4).

    The set is direct department members unioned with the members of every lab
    that belongs to the department, deduplicated by user. It is *computed*, not
    stored as redundant rows — a user in two labs of the same department counts
    once. Seats are issued against this set and department-wide routing uses it.
    """
    direct = DeptMembership.objects.filter(department=department).values_list(
        "user_id", flat=True
    )
    via_labs = LabMembership.objects.filter(
        lab__department=department
    ).values_list("user_id", flat=True)
    return set(direct) | set(via_labs)


def effective_members(department: Department) -> QuerySet[User]:
    """Return the users in a department's effective membership set."""
    return User.objects.filter(id__in=effective_member_ids(department))


def effective_member_count(department: Department) -> int:
    """Number of distinct effective members — the basis for Canopy seat sizing."""
    return len(effective_member_ids(department))


def lab_lead_count(lab: Lab) -> int:
    """Count PIs (lead memberships) of a lab — checked against per-tier PI caps."""
    return LabMembership.objects.filter(lab=lab, is_lead=True).count()
