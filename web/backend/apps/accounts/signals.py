from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Department, DeptProfile, Lab, LabProfile, Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs) -> None:
    """Guarantee one profile per user (briefing §3 PROFILE, decision D5)."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Lab)
def ensure_lab_profile(sender, instance, created, **kwargs) -> None:
    """One interest profile per lab (brief Phase D), mirroring Profile."""
    if created:
        LabProfile.objects.get_or_create(lab=instance)


@receiver(post_save, sender=Department)
def ensure_dept_profile(sender, instance, created, **kwargs) -> None:
    """One interest profile per department (brief Phase D)."""
    if created:
        DeptProfile.objects.get_or_create(department=instance)
