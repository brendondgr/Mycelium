"""Phase 2: the permission core (docs/plans/mylo-agent/permissions.md)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from tools._framework.agentspec import AgentFunction
from tools.agent import permissions, registry, service
from tools.agent.caller import Audience, Caller, Scope
from tools.agent.models import AgentOrgPolicy

from .conftest import thread_for

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden" / "catalog.txt"


def caller(
    user,
    kind="personal",
    obj=None,
    *,
    surface="web",
    width="person",
    via=None,
    thread=None,
):
    return Caller(
        user=user,
        surface=surface,
        scope=Scope(kind, obj),
        audience=Audience(width),
        via=via or {},
        thread_id=thread.pk if thread else None,
    )


def allowed(c):
    return sorted(fn.name for fn in permissions.allowed_functions(c))


def fn(name):
    return registry.registry().get(name)


# -- declarations ------------------------------------------------------------


def test_every_loaded_function_is_fully_declared():
    reg = registry.registry()
    assert reg.functions, "no functions registered"
    assert reg.refused == {}
    for f in reg.functions.values():
        assert registry.declaration_problems(f) == [], f.name
        assert f.risk == "read"


def test_incomplete_or_non_read_functions_refuse_to_load(monkeypatch):
    import sys
    import types

    module = types.ModuleType("fake_agent_module")
    base = dict(
        summary="s",
        description="d",
        handler="x:y",
        output="person",
        scopes=("personal",),
        min_role={},
    )
    module.FUNCTIONS = (
        AgentFunction(
            name="fake_write",
            parameters={"type": "object", "properties": {}},
            risk="write",
            **base,
        ),
        AgentFunction(
            name="fake_noref",
            risk="read",
            parameters={
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
            },
            **base,
        ),
        AgentFunction(
            name="fake_badout",
            risk="read",
            parameters={"type": "object", "properties": {}},
            **{**base, "output": "everyone"},
        ),
    )
    monkeypatch.setitem(sys.modules, "fake_agent_module", module)
    from tools._framework import services

    real = services.agent_contributions
    monkeypatch.setattr(
        services,
        "agent_contributions",
        lambda: [*real(), ("agent", "fake_agent_module")],
    )
    reg = registry.build()
    assert "fake_write" in reg.refused and "write" in reg.refused["fake_write"]
    assert "x-ref" in reg.refused["fake_noref"]
    assert "output" in reg.refused["fake_badout"]
    assert not {"fake_write", "fake_noref", "fake_badout"} & set(reg.functions)


def test_services_lookup_returns_none_when_the_tool_is_not_loaded(
    settings, monkeypatch
):
    from tools._framework import loader, services

    assert services.get("agent") is not None
    report = settings.TOOLS_REPORT
    monkeypatch.setattr(report.tools["agent"], "state", loader.DISABLED)
    assert services.get("agent") is None
    assert "agent" not in [name for name, _ in services.agent_contributions()]


# -- the whole-agent gate (D-5) ---------------------------------------------


def test_free_tier_is_refused_at_layer_3(world):
    d = permissions.may_chat(caller(world.free))
    assert (d.verdict, d.layer, d.code) == ("deny", 3, "not_entitled")


def test_billing_off_lets_everyone_chat(world, settings):
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    assert permissions.may_chat(caller(world.free)).allowed


def test_the_person_switch(world):
    service.set_preferences(world.member, chat_enabled=False)
    d = permissions.may_chat(caller(world.member))
    assert (d.layer, d.code) == (7, "chat_off")
    service.set_preferences(world.member, chat_enabled=True)
    assert permissions.may_chat(caller(world.member)).allowed


def test_no_org_row_narrows_nothing_and_an_org_cannot_switch_the_agent_on_or_off(world):
    c = caller(world.member, "lab", world.lab)
    assert permissions.may_chat(c).allowed
    service.set_org_policy(world.owner, "lab", world.lab, groups_off=["corpus"])
    assert permissions.may_chat(c).allowed  # narrowing is per group, never the agent
    assert "corpus_search" not in allowed(c)
    assert "me_profile" in allowed(c)


def test_scope_the_caller_cannot_see_is_refused(world):
    d = permissions.may_chat(caller(world.outsider, "lab", world.lab))
    assert (d.layer, d.code) == (5, "scope_not_visible")
    with pytest.raises(service.ServiceError):
        service.scope_from(world.outsider, "lab", "imaging")
    with pytest.raises(service.ServiceError):
        service.scope_from(world.member, "project", str(world.other_project.pk))


# -- layers ------------------------------------------------------------------


def test_instance_groups_off_and_surface_groups_off(world, settings):
    settings.AGENT_GROUPS_OFF = ["corpus"]
    d = permissions.decide(caller(world.member), fn("corpus_search"))
    assert (d.layer, d.code) == (2, "group_off")
    settings.AGENT_GROUPS_OFF = []
    settings.AGENT_SURFACE_GROUPS_OFF = ["discord:corpus"]
    d = permissions.decide(caller(world.member, surface="discord"), fn("corpus_search"))
    assert (d.layer, d.code) == (2, "surface_group_off")
    assert permissions.decide(caller(world.member), fn("corpus_search")).allowed


def test_org_policy_narrows_and_cannot_widen(world):
    with pytest.raises(service.ServiceError) as exc:
        service.set_org_policy(world.owner, "lab", world.lab, max_risk="write")
    assert exc.value.code == "too_wide"
    with pytest.raises(service.ServiceError):
        service.set_org_policy(world.member, "lab", world.lab, groups_off=["corpus"])
    service.set_org_policy(world.admin, "lab", world.lab, groups_off=["projects"])
    d = permissions.decide(caller(world.member, "lab", world.lab), fn("projects_list"))
    assert (d.layer, d.code) == (4, "org_group_off")
    # a personal thread is not governed by the lab's policy
    assert permissions.decide(caller(world.member), fn("projects_list")).allowed
    from apps.accounts.models import AuditEvent

    assert AuditEvent.objects.filter(action="agent.org_policy").count() == 1


def test_person_can_narrow_their_own_groups(world):
    service.set_preferences(world.member, groups_off=["corpus"])
    d = permissions.decide(caller(world.member), fn("corpus_search"))
    assert (d.layer, d.code) == (7, "person_group_off")


def test_discord_switch_and_channel_exclusion(world):
    service.set_preferences(world.member, discord_allowed=False)
    d = permissions.may_chat(caller(world.member, surface="discord"))
    assert d.code == "discord_off"
    service.set_preferences(world.member, discord_allowed=True)
    AgentOrgPolicy.objects.create(lab=world.lab, discord_channels_off=["123"])
    d = permissions.may_chat(
        caller(
            world.member,
            "lab",
            world.lab,
            surface="discord",
            width="lab",
            via={"channel_id": 123},
        )
    )
    assert (d.layer, d.code) == (4, "channel_off")


def test_role_removed_mid_turn_fails_the_next_call_at_layer_5(world):
    from apps.accounts.models import LabMembership

    c = caller(world.member, "lab", world.lab)
    assert permissions.decide(c, fn("projects_list"), {}).allowed
    LabMembership.objects.filter(user=world.member, lab=world.lab).delete()
    d = permissions.decide(c, fn("projects_list"), {})
    assert (d.layer, d.code) == (5, "scope_not_visible")


@pytest.mark.parametrize(
    "which", ["visible", "invisible", "archived", "other_lab", "guess"]
)
def test_object_arguments_are_checked_one_by_one(world, which):
    thread = thread_for(world.member)
    c = caller(world.member, thread=thread)
    target = {
        "visible": world.lab_project.pk,
        "invisible": world.other_project.pk,
        "archived": world.archived.pk,
        "other_lab": world.other_project.pk,
        "guess": uuid.uuid4(),
    }[which]
    d = permissions.decide(c, fn("projects_get"), {"project": f"project:{target}"})
    if which == "visible":
        assert d.allowed
    else:
        assert (d.layer, d.code) == (6, "not_visible")
        # the same words whether or not it exists
        assert d.detail == f"project:{target} is not something you can open."


def test_audience_lab_channel_offers_nothing_personal(world):
    c = caller(world.member, "lab", world.lab, surface="discord", width="lab")
    names = allowed(c)
    assert names, "a lab channel still gets lab-wide functions"
    for name in names:
        assert fn(name).output in ("lab", "department", "public", "instance"), name
    assert "me_profile" not in names and "read_result" not in names


def test_mixed_output_is_filtered_in_the_handler(world):
    from tools.agent.functions import projects

    world.lab_project.visibility = "invite_only"
    world.lab_project.save()
    shared = type(world.lab_project).objects.create(
        scope_lab=world.lab, name="Shared one", visibility="lab"
    )
    lab_view = projects.projects_list(
        caller(world.owner, "lab", world.lab, width="lab")
    )
    assert "Shared one" in lab_view.content and "Segmentation" not in lab_view.content
    own_view = projects.projects_list(caller(world.owner, "lab", world.lab))
    assert "Segmentation" in own_view.content and shared.name in own_view.content


def test_an_object_narrower_than_the_audience_is_refused(world):
    thread = thread_for(world.member, "lab", world.lab)
    c = caller(
        world.member, "lab", world.lab, surface="discord", width="lab", thread=thread
    )
    d = permissions.decide(
        c, fn("projects_get"), {"project": f"project:{world.lab_project.pk}"}
    )
    assert (d.layer, d.code) == (9, "audience")


def test_decide_reads_only_the_caller_and_arguments(world):
    """Injection: text a paper or file contains cannot change a decision, because
    decide never sees it. The same caller and arguments decide the same way."""
    c = caller(world.outsider)
    args = {"project": f"project:{world.lab_project.pk}"}
    first = permissions.decide(c, fn("projects_get"), args)
    second = permissions.decide(c, fn("projects_get"), args)
    assert first == second and not first.allowed


# -- the matrix and its golden ------------------------------------------------


def _matrix(world) -> str:
    personas = {
        "outsider": world.outsider,
        "lab_viewer": world.viewer,
        "lab_member": world.member,
        "lab_admin": world.admin,
        "lab_owner": world.owner,
        "dept_member": world.dept_member,
        "other_lab": world.other_lab_member,
        "free": world.free,
    }
    surfaces = {
        "web": ("web", "person", {}),
        "cli": ("cli", "person", {}),
        "discord_dm": ("discord", "person", {}),
        "discord_lab": ("discord", "lab", {"channel_id": "1"}),
        "discord_unbound": ("discord", "instance", {"channel_id": "2"}),
    }
    scopes = {
        "personal": ("personal", None),
        "lab": ("lab", world.lab),
        "project": ("project", world.lab_project),
    }
    lines = []
    for pname, user in personas.items():
        for sname, (surface, width, via) in surfaces.items():
            for scname, (kind, obj) in scopes.items():
                c = caller(user, kind, obj, surface=surface, width=width, via=via)
                gate = permissions.may_chat(c)
                names = (
                    allowed(c) if gate.allowed else [f"DENY:{gate.layer}:{gate.code}"]
                )
                lines.append(f"{pname:<12} {sname:<16} {scname:<9} {' '.join(names)}")
    lines += _discord_places(world)
    return "\n".join(lines) + "\n"


def _discord_places(world) -> list[str]:
    """Plan D: who asks in which Discord place, and what each is offered."""
    from tools.agent.caller import Guest

    guest = Guest("4242", "Visitor")
    lab_room = {"channel_id": "10", "thread_id": "11"}
    rows = (
        # persona, place, scope, user, guest, scope obj, width, audience obj, level
        ("member", "discord_thread", "lab", world.member, None, world.lab, "lab"),
        ("guest", "discord_thread", "lab", None, guest, world.lab, "lab"),
        ("guest_nopeople", "discord_thread", "lab", None, guest, world.lab, "lab"),
        ("guest_public", "discord_thread", "lab", None, guest, world.lab, "lab"),
        ("guest_off", "discord_thread", "lab", None, guest, world.lab, "lab"),
        ("member", "discord_channel", "lab", world.member, None, world.lab, "lab"),
        (
            "member",
            "discord_ambiguous",
            "personal",
            world.member,
            None,
            None,
            "instance",
        ),
        ("guest", "discord_ambiguous", "personal", None, guest, None, "instance"),
    )
    levels = {
        "guest_nopeople": "no_people",
        "guest_public": "public",
        "guest_off": "off",
    }
    out = []
    for pname, place, scname, user, g, obj, width in rows:
        AgentOrgPolicy.objects.filter(lab=world.lab).delete()
        if pname in levels:
            AgentOrgPolicy.objects.create(lab=world.lab, discord_guests=levels[pname])
        c = Caller(
            user=user,
            guest=g,
            surface="discord",
            scope=Scope(scname, obj),
            audience=Audience(width, obj),
            via=lab_room if place != "discord_ambiguous" else {"channel_id": "12"},
        )
        gate = permissions.may_chat(c)
        names = allowed(c) if gate.allowed else [f"DENY:{gate.layer}:{gate.code}"]
        out.append(f"{pname:<12} {place:<16} {scname:<9} {' '.join(names)}")
    AgentOrgPolicy.objects.filter(lab=world.lab).delete()
    return out


def test_permission_matrix_matches_the_golden(world):
    text = _matrix(world)
    if os.environ.get("AGENT_GOLDEN_WRITE") or not GOLDEN.exists():
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(text)
    assert text == GOLDEN.read_text(), (
        "The per-persona catalog changed. If intended, rerun with AGENT_GOLDEN_WRITE=1 "
        "and review the diff."
    )


def test_matrix_expectations(world):
    text = _matrix(world)
    rows = {tuple(line.split()[:3]): line.split()[3:] for line in text.splitlines()}
    assert rows[("outsider", "web", "lab")] == ["DENY:5:scope_not_visible"]
    assert rows[("free", "web", "personal")] == ["DENY:3:not_entitled"]
    assert rows[("other_lab", "web", "project")] == ["DENY:5:scope_not_visible"]
    member_web = rows[("lab_member", "web", "personal")]
    assert {"me_profile", "corpus_search", "projects_get"} <= set(member_web)
    lab_channel = rows[("lab_member", "discord_lab", "lab")]
    assert "me_profile" not in lab_channel and "corpus_search" in lab_channel
    unbound = rows[("lab_member", "discord_unbound", "personal")]
    assert set(unbound) <= {
        fn.name
        for fn in registry.registry().functions.values()
        if fn.output == "instance"
    }
