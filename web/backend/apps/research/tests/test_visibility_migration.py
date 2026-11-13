"""The 0007 backfill: ``share_in_lab_reports`` becomes a scope, and the owner
role lands on the creator (else the lab's PI) — never on a new row."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ACCOUNTS = [("accounts", "0035_lab_department_sees")]
# Accounts is held at 0033 too, so the historical Lab matches its table.
BEFORE = [("research", "0006_project_aliases"), *ACCOUNTS]
AFTER = [("research", "0008_remove_project_share_in_lab_reports")]


@pytest.fixture
def back_to_latest():
    """Leave the database fully migrated for the tests that run after."""
    yield
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    # The state at the research target alone carries an older accounts; read the
    # models against the accounts every migration here already depends on.
    return executor.loader.project_state(targets + ACCOUNTS).apps


@pytest.mark.django_db(transaction=True)
def test_backfill_maps_sharing_to_scope_and_assigns_owners(back_to_latest):
    old = _migrate(BEFORE)
    User = old.get_model("auth", "User")
    Lab = old.get_model("accounts", "Lab")
    Department = old.get_model("accounts", "Department")
    LabMembership = old.get_model("accounts", "LabMembership")
    AuditEvent = old.get_model("accounts", "AuditEvent")
    Project = old.get_model("research", "Project")
    ProjectMember = old.get_model("research", "ProjectMember")

    pi = User.objects.create(username="pi")
    creator = User.objects.create(username="creator")
    other = User.objects.create(username="other")
    lab = Lab.objects.create(name="Reef", slug="reef")
    LabMembership.objects.create(user=pi, lab=lab, role="owner", is_lead=True)
    dept = Department.objects.create(owner=pi, name="Bio")

    shared = Project.objects.create(
        name="Shared", scope_lab=lab, share_in_lab_reports=True
    )
    private = Project.objects.create(name="Private", scope_lab=lab)
    by_pi = Project.objects.create(name="ByPI", scope_lab=lab)
    nobody = Project.objects.create(name="Nobody", scope_lab=lab)
    dproj = Project.objects.create(name="Dept", scope_department=dept)
    personal = Project.objects.create(name="Mine", scope_user=other)

    AuditEvent.objects.create(
        actor=creator, action="project.create", target_type="project",
        target_id=str(shared.id),
    )
    for project, user in (
        (shared, creator), (shared, other), (by_pi, pi), (by_pi, other),
        (nobody, other), (personal, other),
    ):
        ProjectMember.objects.create(project=project, user=user)

    new = _migrate(AFTER)
    Project = new.get_model("research", "Project")
    ProjectMember = new.get_model("research", "ProjectMember")

    scopes = dict(Project.objects.values_list("name", "visibility"))
    assert scopes == {
        "Shared": "lab", "Private": "invite_only", "ByPI": "invite_only",
        "Nobody": "invite_only", "Dept": "invite_only", "Mine": "invite_only",
    }
    owners = {
        (row.project.name, row.user.username)
        for row in ProjectMember.objects.filter(role="owner").select_related(
            "project", "user"
        )
    }
    # Creator where known; else the lab's PI if already a member; nobody is added.
    assert owners == {("Shared", "creator"), ("ByPI", "pi"), ("Mine", "other")}
    assert ProjectMember.objects.count() == 6
    assert not ProjectMember.objects.filter(project__name="Private").exists()
    assert dproj and private
