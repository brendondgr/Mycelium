"""Mylo and stored files, reached the way the agent reaches them: through
``services.get("files")``, never an import (the agent does not depend on the
files tool)."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from tools._framework import services
from tools.agent import dispatch, service, store
from tools.agent.caller import Caller, Scope, for_thread

from .conftest import thread_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def store_dir(tmp_path):
    with override_settings(FILES_DATA_DIR=str(tmp_path / "files")):
        yield


@pytest.fixture
def files():
    module = services.get("files")
    assert module is not None, "the files tool is not loaded"
    return module


def test_mylo_reads_and_searches_a_project_file_with_line_citations(world, files):
    from apps.research.models import ProjectMember

    ProjectMember.objects.get_or_create(project=world.lab_project, user=world.owner)
    text = b"Intro text\n\nThe pilot used conformal prediction on 40 plates.\n"
    row = files.store_upload(
        world.owner,
        SimpleUploadedFile("pilot.txt", text),
        owner_kind="project",
        owner_id=world.lab_project.pk,
    )
    thread = thread_for(world.member, "project", world.lab_project)
    c = Caller(
        user=world.member,
        surface="web",
        scope=Scope("project", world.lab_project),
        thread_id=thread.pk,
    )
    listed = dispatch.run(c, thread, name="files_list", args={}, call_id="a")
    assert "pilot.txt" in listed["content"]
    found = dispatch.run(
        c,
        thread,
        name="files_search",
        args={"file": f"file:{row.pk}", "query": "conformal"},
        call_id="b",
    )
    assert found["status"] == "ok" and found["untrusted"]
    assert "3: The pilot used conformal" in found["content"]
    outsider = Caller(
        user=world.outsider, surface="web", thread_id=thread_for(world.outsider).pk
    )
    denied = dispatch.run(
        outsider,
        thread,
        name="files_read",
        args={"file": f"file:{row.pk}"},
        call_id="c",
    )
    assert denied["status"] == "denied"


def test_a_chat_attachment_lands_under_the_project(world, files):
    StoredFile = apps.get_model("files", "StoredFile")
    thread = thread_for(world.owner, "project", world.lab_project)
    service.send(
        for_thread(thread),
        thread,
        "what does this say?",
        attachments=[SimpleUploadedFile("note.txt", b"line one\nline two")],
        start=lambda t: None,
    )
    row = StoredFile.objects.get()
    assert row.owner_project_id == world.lab_project.pk
    assert row.origin == "chat" and row.thread_id == thread.pk
    user_event = [e for e in store.events(thread) if e.type == "user"][0]
    assert user_event.payload["inline"][0]["text"].startswith("1: line one")
    assert user_event.payload["cards"][0].startswith("#1 file: note.txt")


def test_a_lab_channel_cannot_reach_another_labs_project(world):
    """Width alone is not enough: lab B's lab-wide project is not for lab A's
    channel (the gate checks which org, not only how wide)."""
    from apps.accounts.models import LabMembership
    from apps.research.models import Project

    other = Project.objects.create(
        scope_lab=world.other_lab, name="B shared", share_in_lab_reports=True
    )
    from apps.research.models import ProjectMember

    LabMembership.objects.create(user=world.member, lab=world.other_lab, role="member")
    ProjectMember.objects.create(project=other, user=world.member)
    thread = thread_for(world.member, "lab", world.lab)
    from tools.agent.caller import Audience

    c = Caller(
        user=world.member,
        surface="discord",
        scope=Scope("lab", world.lab),
        audience=Audience("lab", world.lab),
        thread_id=thread.pk,
    )
    out = dispatch.run(
        c,
        thread,
        name="projects_get",
        args={"project": f"project:{other.pk}"},
        call_id="x",
    )
    assert out["status"] == "denied" and out["error"]["code"] == "audience"
