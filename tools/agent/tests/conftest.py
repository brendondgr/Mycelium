"""Fixtures for the agent's tests: a scripted model, an in-memory stream bus,
sequential calls, and a small world of people, labs and projects."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from apps.core.llm import LLMResponse, ToolCall
from django.contrib.auth.models import User


@pytest.fixture(autouse=True)
def _agent_env(settings):
    from tools.agent import registry, stream

    settings.AGENT_PARALLEL_CALLS = False
    settings.LLM_MODEL = "test-model"
    # A stated window: 0 would ask the (absent) model server on every turn.
    settings.AGENT_CONTEXT_WINDOW = 32768
    stream.use_memory_bus()
    registry.reset()
    yield
    registry.reset()


class ScriptedModel:
    """A model port that replays scripted replies and records every request.

    A step is a string (a final answer), a list of ``(name, args)`` calls, a
    dict ``{"text": ..., "calls": [...]}``, or an ``LLMResponse``. When the
    script runs out it raises ``IndexError`` (title generation falls back).
    """

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests: list[dict] = []
        self._n = 0

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        self.requests.append(
            {"messages": messages, "tools": tools, "tool_choice": tool_choice}
        )
        if not self.steps:
            raise IndexError("script exhausted")
        step = self.steps.pop(0)
        if isinstance(step, LLMResponse):
            return step
        if isinstance(step, str):
            if on_delta:
                on_delta("text", step)
            return LLMResponse(
                content=step, finish_reason="stop", usage={"total_tokens": 10}
            )
        if isinstance(step, dict):
            text, calls = step.get("text", ""), step.get("calls", [])
        else:
            text, calls = "", step
        tool_calls = []
        for name, args in calls:
            self._n += 1
            tool_calls.append(
                ToolCall(id=f"c{self._n}", name=name, arguments=json.dumps(args))
            )
        return LLMResponse(
            content=text,
            finish_reason="tool_calls",
            tool_calls=tuple(tool_calls),
            usage={"total_tokens": 10},
        )


@pytest.fixture
def scripted():
    return ScriptedModel


def make_user(username: str, *, paid: bool = True, verified: bool = True) -> User:
    from apps.billing.testing import paid_plan

    user = User.objects.create_user(
        username=username, password="x", first_name=username.title()
    )
    profile = getattr(user, "profile", None)
    if profile is not None and verified:
        profile.is_verified = True
        profile.save(update_fields=["is_verified"])
    if paid:
        paid_plan(user)
    return user


@pytest.fixture
def world(db):
    """Two labs in one department, projects of each kind, and every persona."""
    from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
    from apps.research.models import Project, ProjectMember

    w = SimpleNamespace()
    w.owner = make_user("owner")
    w.admin = make_user("admin")
    w.member = make_user("member")
    w.viewer = make_user("viewer")
    w.outsider = make_user("outsider")
    w.other_lab_member = make_user("othermember")
    w.dept_member = make_user("deptmember")
    w.free = make_user("freeuser", paid=False)
    w.dept = Department.objects.create(owner=w.owner, name="Biology")
    w.lab = Lab.objects.create(name="Imaging Lab", slug="imaging", department=w.dept)
    w.other_lab = Lab.objects.create(name="Other Lab", slug="other")
    for user, role in (
        (w.owner, "owner"),
        (w.admin, "admin"),
        (w.member, "member"),
        (w.viewer, "viewer"),
        (w.free, "member"),
    ):
        LabMembership.objects.create(user=user, lab=w.lab, role=role)
    LabMembership.objects.create(
        user=w.other_lab_member, lab=w.other_lab, role="member"
    )
    DeptMembership.objects.create(user=w.dept_member, department=w.dept, role="member")
    w.lab_project = Project.objects.create(
        scope_lab=w.lab,
        name="Segmentation",
        goals={"summary": "segment cells"},
        aliases=["IMG-seg"],
    )
    ProjectMember.objects.create(project=w.lab_project, user=w.member)
    w.archived = Project.objects.create(
        scope_lab=w.lab, name="Old work", is_archived=True
    )
    w.personal = Project.objects.create(scope_user=w.member, name="My thesis")
    ProjectMember.objects.create(project=w.personal, user=w.member)
    w.other_project = Project.objects.create(scope_lab=w.other_lab, name="Secret")
    return w


def thread_for(user, kind="personal", obj=None, surface="web"):
    from tools.agent import service
    from tools.agent.caller import Scope

    return service.create_thread(user, scope=Scope(kind, obj), surface=surface)
