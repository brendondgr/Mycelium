from django.contrib.auth.models import AnonymousUser, User

from .models import Department, DeptMembership, Lab, LabMembership
from .services import effective_member_ids

UserOrAnon = User | AnonymousUser


def user_has_lab_access(user: UserOrAnon, lab: Lab) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return LabMembership.objects.filter(user=user, lab=lab).exists()


def user_can_manage_lab(user: UserOrAnon, lab: Lab) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return LabMembership.objects.filter(
        user=user,
        lab=lab,
        role__in=[LabMembership.Role.OWNER, LabMembership.Role.ADMIN],
    ).exists()


def user_can_edit_lab_profile(user: UserOrAnon, lab: Lab) -> bool:
    """A lab's interest profile is edited by its lead PI or owner/admin (brief G)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return LabMembership.objects.filter(
        user=user, lab=lab, is_lead=True
    ).exists() or user_can_manage_lab(user, lab)


def user_can_invite_to_lab(user: UserOrAnon, lab: Lab) -> bool:
    """A lab's PI (lead) or owner/admin may invite people to it."""
    return user_can_edit_lab_profile(user, lab)


def user_has_department_access(user: UserOrAnon, department: Department) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or department.owner_id == user.id:
        return True
    return user.id in effective_member_ids(department)


def user_can_edit_dept_profile(user: UserOrAnon, department: Department) -> bool:
    """A department's interest profile is edited by its owner or an admin (brief G)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or department.owner_id == user.id:
        return True
    return DeptMembership.objects.filter(
        user=user,
        department=department,
        role__in=[DeptMembership.Role.OWNER, DeptMembership.Role.ADMIN],
    ).exists()


def user_can_manage_department(user: UserOrAnon, department: Department) -> bool:
    """Manage a department's members, labs, and subscription: owner or admin only.

    Same authority as editing the department profile — the head (owner) plus any
    ``DeptMembership`` with an OWNER/ADMIN role — surfaced under a management-intent
    name so the member/lab/billing endpoints read clearly.
    """
    return user_can_edit_dept_profile(user, department)
