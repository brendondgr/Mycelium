"""An ordinary lab member finds no ``invite_only`` project through its files
(scoping plan, acceptance: "by any route … files")."""

from __future__ import annotations

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.research import visibility
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from tools.files import access, service

pytestmark = pytest.mark.django_db


def test_an_invite_only_projects_files_reach_only_its_people(tmp_path):
    on = User.objects.create_user("on", "on@example.org", "pw")
    off = User.objects.create_user("off", "off@example.org", "pw")
    lab = Lab.objects.create(name="Reef", slug="reef-files-scope")
    for user in (on, off):
        LabMembership.objects.create(user=user, lab=lab)
    hidden = Project.objects.create(name="Hidden", scope_lab=lab)
    ProjectMember.objects.create(project=hidden, user=on, role=ProjectMember.Role.OWNER)
    assert hidden.visibility == "invite_only"

    with override_settings(FILES_DATA_DIR=str(tmp_path / "files")):
        stored = service.store_upload(
            on,
            SimpleUploadedFile("notes.txt", b"secret notes"),
            owner_kind="project",
            owner_id=hidden.pk,
        )
        assert access.can_see(on, stored)
        assert not access.can_see(off, stored)
        client = APIClient()
        client.force_authenticate(off)
        assert client.get(f"/api/tools/files/files/{stored.pk}/").status_code == 404
    # Nor may Mylo name it in the lab's room, and it is in no directory of theirs.
    assert visibility.output_width(hidden) == "project"
    assert not visibility.may_surface(hidden, "lab")
    assert hidden not in visibility.directory(off)
