"""Project.visibility replaces share_in_lab_reports; ProjectMember gains a role.

Backfill:

* ``share_in_lab_reports=True`` becomes ``lab``; everything else, department
  projects included, becomes ``invite_only``.
* The owner role goes to the project's creator where it is known (the actor of
  its ``project.create`` audit event, or a personal project's own user), else to
  the lab's PI — but only onto a membership row that already exists. The
  migration never adds anyone to a project: seeing is not belonging, and a new
  row would put the project into that person's own reports. A project with no
  owner row keeps being run by its lab's (or department's) managers, as before.
"""

from django.db import migrations, models


def forwards(apps, schema_editor):
    Project = apps.get_model("research", "Project")
    ProjectMember = apps.get_model("research", "ProjectMember")
    AuditEvent = apps.get_model("accounts", "AuditEvent")
    LabMembership = apps.get_model("accounts", "LabMembership")

    Project.objects.filter(share_in_lab_reports=True, scope_lab__isnull=False).update(
        visibility="lab"
    )

    creators = {}
    for target_id, actor_id in (
        AuditEvent.objects.filter(action="project.create", actor__isnull=False)
        .order_by("created_at")
        .values_list("target_id", "actor_id")
    ):
        creators.setdefault(target_id, actor_id)

    for project in Project.objects.all().only("id", "scope_user_id", "scope_lab_id"):
        member_ids = set(
            ProjectMember.objects.filter(project_id=project.id).values_list(
                "user_id", flat=True
            )
        )
        if not member_ids:
            continue
        candidates = [project.scope_user_id, creators.get(str(project.id))]
        if project.scope_lab_id is not None:
            candidates.extend(
                LabMembership.objects.filter(lab_id=project.scope_lab_id, is_lead=True)
                .order_by("id")
                .values_list("user_id", flat=True)
            )
        owner = next((c for c in candidates if c is not None and c in member_ids), None)
        if owner is not None:
            ProjectMember.objects.filter(project_id=project.id, user_id=owner).update(
                role="owner"
            )


def backwards(apps, schema_editor):
    Project = apps.get_model("research", "Project")
    Project.objects.filter(visibility__in=("lab", "department", "public")).update(
        share_in_lab_reports=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("research", "0006_project_aliases"),
        ("accounts", "0035_lab_department_sees"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("invite_only", "Invite only"),
                    ("lab", "Lab"),
                    ("department", "Department"),
                    ("public", "Public"),
                ],
                db_index=True,
                default="invite_only",
                help_text=(
                    "Who may see this project and where Mylo may mention it. "
                    "invite_only: its members (and the lab's or department's "
                    "overseers); lab: the owning lab's members; department: the "
                    "lab's department too; public: any verified account on this "
                    "instance. Read only through apps.research.visibility."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="projectmember",
            name="role",
            field=models.CharField(
                choices=[("owner", "Owner"), ("editor", "Editor"), ("member", "Member")],
                default="member",
                max_length=10,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
