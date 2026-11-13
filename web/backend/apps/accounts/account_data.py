"""A person's own data: a copy of it on request, and erasure on request.

University deployments are asked for both — "send me what you hold about me"
and "delete my account" — so they are first-class routes rather than an
operator running SQL.

**Export** walks every model that hangs off the account with ``CASCADE`` — the
rows that exist *because* this person does (their profile, interests, saved
items, personal projects, ambient observations of what they said, Mylo threads,
reminders, notifications) — and writes them out as JSON. Rows the person only
*touched* on someone else's object (``SET_NULL`` links: a collection they
created in a lab, a project state they edited) are not theirs alone and are
left out, and so is anything secret (password and code hashes, tokens, the
embedding vectors). Memberships are listed with the org's name so the file is
readable on its own.

**Deletion** is the same set, removed: deleting the ``User`` cascades to every
one of those rows. What it must not do is strand other people, so it refuses
while the person is the only owner of a lab or department that has anybody
else in it — ownership has to be handed over first. A lab or department that
is theirs alone goes with them.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from django.contrib.auth.models import User
from django.db import models, transaction

from .models import AuditEvent, Department, DeptMembership, Lab, LabMembership

#: Never exported: bookkeeping that is about the account rather than the person,
#: or that holds secrets.
_SKIPPED_MODELS = frozenset(
    {
        "admin.LogEntry",
        "accounts.EmailVerification",
        "integrations.DiscordActivationCode",
        "integrations.DiscordOutboxMessage",
        "integrations.SlackOutboxMessage",
        "integrations.TeamsOutboxMessage",
    }
)

#: Children exported with their parent, because the parent alone is an empty
#: shell: a Mylo thread is its messages.
_CHILDREN = {"agent.AgentThread": ("events", "queued")}

#: Field names never written out, whatever model they are on.
_SECRET_NAME_PARTS = ("password", "hash", "token", "secret", "embedding")


def _is_secret(field) -> bool:
    name = field.name.lower()
    if any(part in name for part in _SECRET_NAME_PARTS):
        return True
    if isinstance(field, models.BinaryField):
        return True
    return field.get_internal_type() == "VectorField" or type(field).__name__ in {
        "VectorField",
        "HalfVectorField",
        "SparseVectorField",
    }


def _value(value):
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID | decimal.Decimal):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return None
    if isinstance(value, list | tuple):
        return [_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _value(v) for k, v in value.items()}
    if hasattr(value, "tolist"):  # a numpy array that slipped past the filter
        return None
    return value


def _row(obj) -> dict:
    out: dict = {}
    for field in obj._meta.concrete_fields:
        if _is_secret(field):
            continue
        out[field.attname] = _value(getattr(obj, field.attname))
    return out


def _rows_with_children(label: str, queryset) -> list[dict]:
    children = _CHILDREN.get(label, ())
    rows = []
    for obj in queryset:
        row = _row(obj)
        for accessor in children:
            related = getattr(obj, accessor, None)
            if related is not None and hasattr(related, "all"):
                row[accessor] = [_row(child) for child in related.all()]
        rows.append(row)
    return rows


def export(user: User) -> dict:
    """Everything this account owns, as a JSON-ready dict. Never other people's."""
    data: dict = {
        "format": "mycelium-account-export/1",
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "account": {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_joined": _value(user.date_joined),
            "last_login": _value(user.last_login),
        },
        "memberships": {
            "labs": [
                {
                    "lab": m.lab.name,
                    "slug": m.lab.slug,
                    "role": m.role,
                    "is_lead": m.is_lead,
                }
                for m in LabMembership.objects.filter(user=user).select_related("lab")
            ],
            "departments": [
                {"department": m.department.name, "role": m.role}
                for m in DeptMembership.objects.filter(user=user).select_related(
                    "department"
                )
            ]
            + [
                {"department": d.name, "role": "owner"}
                for d in Department.objects.filter(owner=user)
            ],
        },
        "records": {},
    }
    for rel in User._meta.related_objects:
        if rel.many_to_many or rel.on_delete is not models.CASCADE:
            continue
        model = rel.related_model
        label = model._meta.label
        if label in _SKIPPED_MODELS:
            continue
        queryset = model._default_manager.filter(**{rel.field.name: user})
        rows = _rows_with_children(label, queryset)
        if rows:
            key = f"{label}.{rel.field.name}"
            data["records"][key] = rows
    return data


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #


def deletion_blockers(user: User) -> list[str]:
    """Why the account cannot be deleted yet; empty when it can.

    Only one reason exists: the person is the sole owner of an org that has
    other people in it. Deleting them would leave a lab or department nobody can
    manage, so they hand it over (or remove the others) first.
    """
    reasons: list[str] = []
    for membership in LabMembership.objects.filter(
        user=user, role=LabMembership.Role.OWNER
    ).select_related("lab"):
        lab = membership.lab
        other_owners = (
            LabMembership.objects.filter(lab=lab, role=LabMembership.Role.OWNER)
            .exclude(user=user)
            .exists()
        )
        others = LabMembership.objects.filter(lab=lab).exclude(user=user).exists()
        if others and not other_owners:
            reasons.append(
                f"You are the only owner of {lab.name}. Hand it to another member "
                "before deleting your account."
            )
    for department in Department.objects.filter(owner=user):
        if _department_has_others(department, user):
            reasons.append(
                f"You own the department {department.name}. Ask an administrator "
                "to give it a new owner before deleting your account."
            )
    return reasons


def _department_has_others(department: Department, user: User) -> bool:
    return (
        DeptMembership.objects.filter(department=department).exclude(user=user).exists()
        or Lab.objects.filter(department=department).exists()
    )


@transaction.atomic
def delete_account(user: User) -> dict:
    """Erase ``user`` and everything that cascades from them.

    Labs and departments that were theirs alone go with them (a ``Department``
    is ``PROTECT``-ed from its owner, so it must be removed first). Returns a
    small summary for the audit record — counts and ids, never content.
    """
    solo_labs = [
        membership.lab
        for membership in LabMembership.objects.filter(
            user=user, role=LabMembership.Role.OWNER
        ).select_related("lab")
        if not LabMembership.objects.filter(lab=membership.lab)
        .exclude(user=user)
        .exists()
    ]
    solo_departments = [
        d
        for d in Department.objects.filter(owner=user)
        if not _department_has_others(d, user)
    ]
    summary = {
        "labs_removed": [str(lab.id) for lab in solo_labs],
        "departments_removed": [str(d.id) for d in solo_departments],
    }
    for lab in solo_labs:
        lab.delete()
    for department in solo_departments:
        department.delete()
    user_id = user.pk
    user.delete()
    AuditEvent.objects.create(
        actor=None,
        action="account.delete",
        target_type="user",
        target_id=str(user_id),
        metadata=summary,
    )
    return summary
