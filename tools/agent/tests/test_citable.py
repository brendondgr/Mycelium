"""Every person and project a function returns carries a reference number on
a line of its own, so an answer that names one can cite it (C-043: Mylo named
the right people and projects without citing them)."""

from __future__ import annotations

import re

import pytest

from tools.agent import prompt, refs

from .test_kg_functions import item, lab_run, run, score

pytestmark = pytest.mark.django_db

REF = re.compile(r"#(\d+)")


def _kinds(user, kind, obj, out):
    """reference number → kind, for the numbers a result surfaced."""
    from tools.agent.models import AgentThread

    thread = AgentThread.objects.filter(user=user).order_by("-created_at").first()
    by_n = {e["n"]: e["kind"] for e in refs.thread_refs(thread)}
    return {n: by_n[n] for n in out["refs"]}


def test_every_lab_member_has_a_reference_on_their_own_line(world):
    out = run(world.member, "org_lab_members", {}, kind="lab", obj=world.lab)
    assert out["status"] == "ok"
    rows = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert len(rows) == 5
    numbers = [int(REF.match(r[2:]).group(1)) for r in rows]
    assert len(set(numbers)) == 5
    kinds = _kinds(world.member, "lab", world.lab, out)
    assert all(kinds[n] == "person" for n in numbers)


def test_a_project_lists_its_members_by_reference(world):
    from apps.research.models import ProjectMember

    ProjectMember.objects.create(project=world.lab_project, user=world.admin)
    out = run(
        world.member,
        "projects_get",
        {"project": f"project:{world.lab_project.pk}"},
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "ok"
    lines = out["content"].splitlines()
    assert lines[0] == f"#{out['refs'][0]} Segmentation"
    start = lines.index("Members:")
    members = lines[start + 1 :]
    assert sorted(m.split(" ", 2)[2] for m in members) == [
        "Admin (@admin)",
        "Member (@member)",
    ]
    numbers = [int(REF.match(m[2:]).group(1)) for m in members]
    kinds = _kinds(world.member, "lab", world.lab, out)
    assert kinds[out["refs"][0]] == "project"
    assert all(kinds[n] == "person" for n in numbers)
    # The names are not also given on one unreferenced line.
    assert not any(x.startswith("Members: ") for x in lines)


def test_every_listed_project_has_a_reference(world):
    out = run(world.member, "projects_list", {}, kind="lab", obj=world.lab)
    rows = [x for x in out["content"].splitlines() if x.startswith("- ")]
    assert rows and all(REF.match(r[2:]) for r in rows)
    kinds = _kinds(world.member, "lab", world.lab, out)
    assert set(kinds.values()) == {"project"}


def test_the_persons_own_labs_and_projects_come_with_references(world):
    out = run(world.member, "me_profile", {})
    lines = out["content"].splitlines()
    labs = lines[lines.index("Your labs, by reference:") + 1]
    assert REF.match(labs[2:]) and labs.endswith("Imaging Lab")
    after = lines[lines.index("Your projects, by reference:") + 1 :]
    assert sorted(x.split(" ", 2)[2] for x in after) == ["My thesis", "Segmentation"]
    kinds = _kinds(world.member, "personal", None, out)
    assert sorted(kinds.values()) == ["lab", "project", "project"]


def test_a_person_read_alone_has_a_reference(world):
    out = run(world.member, "org_person", {"person": "person:admin"})
    assert out["status"] == "ok"
    assert re.match(r"#\d+ Admin \(@admin\)", out["content"].splitlines()[0])


def test_who_should_look_is_not_referenced_for_someone_the_reply_cannot_show(world):
    """A lab-wide reply never gains a reference to a person outside the lab."""
    grant = item("Lab grant", "grant")
    score(
        grant,
        1,
        target_lab=world.lab,
        signals={"member_fit": [{"username": "othermember"}, {"username": "admin"}]},
    )
    out = lab_run(world.member, "feeds_slate", {}, world.lab)
    line = next(x for x in out["content"].splitlines() if "who should look" in x)
    assert re.search(r"#\d+ Admin", line)
    assert "Othermember" in line and not re.search(r"#\d+ Othermember", line)


def test_the_prompt_says_to_cite_people_and_projects_and_only_the_ones_meant():
    rules = " ".join(prompt.BASE_RULES.split())
    assert "Cite every item, person and project you name" in rules
    assert "a name without its number is not a citation" in rules
    assert "do not cite the rest of it for context" in rules
