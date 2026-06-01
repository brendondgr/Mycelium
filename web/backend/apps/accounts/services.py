from django.contrib.auth.models import User

from .models import AuditEvent, Lab


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


def get_lab_for_user(user: User, slug: str) -> Lab | None:
    if user.is_superuser:
        return Lab.objects.filter(slug=slug).first()

    return (
        Lab.objects.filter(slug=slug, memberships__user=user)
        .distinct()
        .first()
    )
