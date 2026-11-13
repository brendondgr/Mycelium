"""Leaving, and a lab leaving its department (scoping plan, Phase 5).

Hooked on the rows themselves rather than on each view, so every path that
removes a lab member, deletes an account or moves a lab — a view, the admin, a
billing change — applies the same rules (:mod:`.lifecycle`).
"""

from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.accounts.models import Lab, LabMembership

#: Accounts being deleted right now: their lab rows cascade, and the project
#: hand-over already ran in :func:`account_deleting`.
_DELETING: set = set()


@receiver(post_delete, sender=LabMembership)
def lab_membership_ended(sender, instance, **kwargs) -> None:
    """Leaving or being removed from a lab ends membership in its projects."""
    from django.contrib.auth import get_user_model

    from . import lifecycle

    if instance.user_id in _DELETING:
        return
    user = get_user_model().objects.filter(pk=instance.user_id).first()
    if user is None:
        return
    lifecycle.end_lab_project_memberships(instance.lab_id, user)


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def account_deleting(sender, instance, **kwargs) -> None:
    """An owner deleting their account hands their projects over first."""
    from . import lifecycle

    _DELETING.add(instance.pk)
    lifecycle.account_leaving(instance)


@receiver(post_delete, sender=settings.AUTH_USER_MODEL)
def account_deleted(sender, instance, **kwargs) -> None:
    _DELETING.discard(instance.pk)


@receiver(pre_save, sender=Lab)
def lab_saving(sender, instance, **kwargs) -> None:
    instance._department_before = (
        Lab.objects.filter(pk=instance.pk)
        .values_list("department_id", flat=True)
        .first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=Lab)
def lab_saved(sender, instance, created=False, **kwargs) -> None:
    """A lab that left (or changed) its department: its ``department`` projects
    fall back to ``lab``."""
    before = getattr(instance, "_department_before", None)
    if created or before is None or before == instance.department_id:
        return
    from . import lifecycle

    lifecycle.lab_left_department(instance, before)
