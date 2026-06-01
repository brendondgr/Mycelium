from django.contrib.auth.models import AnonymousUser, User

from .models import Lab, LabMembership


def user_has_lab_access(user: User | AnonymousUser, lab: Lab) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return LabMembership.objects.filter(user=user, lab=lab).exists()


def user_can_manage_lab(user: User | AnonymousUser, lab: Lab) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return LabMembership.objects.filter(
        user=user,
        lab=lab,
        role__in=[LabMembership.Role.OWNER, LabMembership.Role.ADMIN],
    ).exists()
