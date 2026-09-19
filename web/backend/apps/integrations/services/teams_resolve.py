"""Teams' one door to the ORM (ambient Plan 11), like ``slack_resolve``."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from ..models import TeamsIdentity, TeamsOutboxMessage, TeamsTeamLink

ACTIVE = TeamsIdentity.State.ACTIVE
OUTBOX_PENDING = TeamsOutboxMessage.Status.PENDING
OUTBOX_SENDING = TeamsOutboxMessage.Status.SENDING
OUTBOX_SENT = TeamsOutboxMessage.Status.SENT
OUTBOX_FAILED = TeamsOutboxMessage.Status.FAILED
OUTBOX_DEAD = TeamsOutboxMessage.Status.DEAD


def resolve_user(tenant_id: str, aad_object_id: str) -> User | None:
    identity = (
        TeamsIdentity.objects.filter(
            tenant_id=str(tenant_id), aad_object_id=str(aad_object_id), state=ACTIVE
        )
        .select_related("user")
        .first()
    )
    if identity is None or not identity.user.is_active:
        return None
    return identity.user


def resolve_by_object_id(aad_object_id: str) -> User | None:
    """The one active identity with this object id, or None (also when, by
    any chance, two tenants' identities shared it)."""
    rows = list(
        TeamsIdentity.objects.filter(
            aad_object_id=str(aad_object_id), state=ACTIVE
        ).select_related("user")[:2]
    )
    if len(rows) != 1 or not rows[0].user.is_active:
        return None
    return rows[0].user


def identity_for(user) -> TeamsIdentity | None:
    return (
        TeamsIdentity.objects.filter(user=user, state=ACTIVE)
        .order_by("-linked_at")
        .first()
    )


def identities_for(user) -> list[TeamsIdentity]:
    return list(TeamsIdentity.objects.filter(user=user, state=ACTIVE))


def linked_elsewhere(tenant_id: str, aad_object_id: str, *, not_user) -> bool:
    return (
        TeamsIdentity.objects.filter(
            tenant_id=tenant_id, aad_object_id=aad_object_id, state=ACTIVE
        )
        .exclude(user=not_user)
        .exists()
    )


def bind_identity(
    user, *, tenant_id: str, aad_object_id: str, service_url: str, conversation_id: str
) -> TeamsIdentity:
    TeamsIdentity.objects.filter(user=user, tenant_id=tenant_id, state=ACTIVE).exclude(
        aad_object_id=aad_object_id
    ).update(state=TeamsIdentity.State.REVOKED, revoked_at=timezone.now())
    identity, _ = TeamsIdentity.objects.update_or_create(
        user=user,
        tenant_id=tenant_id,
        aad_object_id=aad_object_id,
        state=ACTIVE,
        defaults={"service_url": service_url, "conversation_id": conversation_id},
    )
    return identity


def unlink(user, tenant_id: str) -> int:
    return TeamsIdentity.objects.filter(
        user=user, tenant_id=str(tenant_id), state=ACTIVE
    ).update(state=TeamsIdentity.State.REVOKED, revoked_at=timezone.now())


def team_link(team_id: str) -> TeamsTeamLink | None:
    return TeamsTeamLink.objects.filter(team_id=str(team_id), active=True).first()


def link_for_lab(lab) -> TeamsTeamLink | None:
    return TeamsTeamLink.objects.filter(lab=lab, active=True).first()


def install_team(*, team_id: str, tenant_id: str, name: str, service_url: str):
    link, _ = TeamsTeamLink.objects.update_or_create(
        team_id=team_id,
        defaults={
            "tenant_id": tenant_id,
            "name": name[:120],
            "service_url": service_url,
            "active": True,
        },
    )
    return link


def deactivate_team(link: TeamsTeamLink) -> None:
    link.active = False
    link.save(update_fields=["active", "updated_at"])


def bind_team_lab(link: TeamsTeamLink, lab_id, conversation_id: str) -> None:
    link.lab_id = lab_id
    link.updates_conversation_id = conversation_id
    link.save(update_fields=["lab", "updates_conversation_id", "updated_at"])


def set_reports_primary(link: TeamsTeamLink, primary) -> None:
    link.reports_primary = bool(primary)
    link.save(update_fields=["reports_primary", "updated_at"])


def outbox_by_key(dedupe_key: str):
    return TeamsOutboxMessage.objects.filter(dedupe_key=dedupe_key).first()


def outbox_create(**fields):
    return TeamsOutboxMessage.objects.create(**fields)


def outbox_claim(limit: int, now) -> list[int]:
    """Due pending rows, marked sending. Call inside a transaction."""
    ids = list(
        TeamsOutboxMessage.objects.select_for_update(skip_locked=True)
        .filter(status=OUTBOX_PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    TeamsOutboxMessage.objects.filter(pk__in=ids).update(status=OUTBOX_SENDING)
    return ids


def outbox_row(pk: int):
    return TeamsOutboxMessage.objects.get(pk=pk)
