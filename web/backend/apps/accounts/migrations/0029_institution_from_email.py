"""Retire typed institutions: every profile's is re-derived from its email.

From here on ``Profile.institution`` is written only by
``apps.accounts.institution.sync`` — the institution a *verified* address
belongs to in the affiliation directory, or nothing. This pass brings existing
rows under the same rule and writes each value it replaces to the audit log, so
no typed institution disappears without a record.
"""

from django.db import migrations


def rederive(apps, schema_editor):
    from apps.accounts.institution import resolve_email

    Profile = apps.get_model("accounts", "Profile")
    AuditEvent = apps.get_model("accounts", "AuditEvent")
    rows = Profile.objects.select_related("user").only(
        "pk", "institution", "is_verified", "user__email"
    )
    for profile in rows.iterator():
        found = resolve_email(profile.user.email) if profile.is_verified else None
        after = found.name if found else ""
        if profile.institution == after:
            continue
        AuditEvent.objects.create(
            actor=None,
            action="profile.institution_rederived",
            target_type="user",
            target_id=str(profile.user_id),
            metadata={"before": profile.institution, "after": after},
        )
        Profile.objects.filter(pk=profile.pk).update(institution=after)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0028_work_facets"),
    ]

    operations = [
        migrations.RunPython(rederive, migrations.RunPython.noop),
    ]
