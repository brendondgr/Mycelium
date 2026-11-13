from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver

from .embedding import apply_embedding
from .models import (
    Department,
    DeptMembership,
    DeptProfile,
    Lab,
    LabProfile,
    LabWatchPreference,
    Profile,
)

#: Sent (with ``user=``) after an address is proved and the account's
#: institution re-derived — by a verification code or an emailed invitation.
email_verified = Signal()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs) -> None:
    """Guarantee one profile per user (briefing §3 PROFILE, decision D5)."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(pre_save, sender=Profile)
@receiver(pre_save, sender=LabProfile)
@receiver(pre_save, sender=DeptProfile)
def embed_interest_surface(sender, instance, **kwargs) -> None:
    """Build the canonical text and (re)embed before each save (brief Phase F)."""
    apply_embedding(instance)


@receiver(post_save, sender=Lab)
def ensure_lab_profile(sender, instance, created, **kwargs) -> None:
    """One interest profile + watch row per lab, mirroring Profile/WatchPreference."""
    if created:
        LabProfile.objects.get_or_create(lab=instance)
        LabWatchPreference.objects.get_or_create(lab=instance)


@receiver(post_save, sender=Department)
def ensure_dept_profile(sender, instance, created, **kwargs) -> None:
    """One interest profile per department (brief Phase D)."""
    if created:
        DeptProfile.objects.get_or_create(department=instance)


@receiver(pre_save, sender=Department)
def remember_department_head(sender, instance, **kwargs) -> None:
    """Note the head before a save, so the row can follow a change of ``owner``."""
    if instance.pk is None or kwargs.get("raw"):
        instance._previous_owner_id = None
        return
    instance._previous_owner_id = (
        Department.objects.filter(pk=instance.pk)
        .values_list("owner_id", flat=True)
        .first()
    )


@receiver(post_save, sender=Department)
def keep_head_membership_in_step(sender, instance, created, **kwargs) -> None:
    """The head's OWNER ``DeptMembership`` row follows ``Department.owner``.

    Capabilities resolve from membership rows, and the head is a foreign key, so
    whatever changes the head — the transfer route, Django admin, a shell —
    leaves exactly one OWNER row, on the head. A new department's founding row
    is written by whoever creates it (``create_department_workspace``), so this
    only acts when an existing department's head changes.
    """
    previous = getattr(instance, "_previous_owner_id", None)
    if created or kwargs.get("raw") or previous in (None, instance.owner_id):
        return
    row, made = DeptMembership.objects.get_or_create(
        department=instance,
        user_id=instance.owner_id,
        defaults={"role": DeptMembership.Role.OWNER},
    )
    if not made and row.role != DeptMembership.Role.OWNER:
        row.role = DeptMembership.Role.OWNER
        row.save(update_fields=["role"])
    DeptMembership.objects.filter(
        department=instance, role=DeptMembership.Role.OWNER
    ).exclude(pk=row.pk).update(role=DeptMembership.Role.ADMIN)
