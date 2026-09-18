"""The sandbox harness itself: a deterministic world, and a guard that holds.

The harness writes hundreds of fake people, so the one thing it must never get
wrong is where. These tests pin the database rewrite and the refusal, and that
the world it builds is the same every time and has its gaps where they belong.
"""

import pytest

from sandbox.collab import bootstrap, corpus, world


def test_the_url_is_rewritten_to_the_sandbox_database():
    assert bootstrap.sandbox_url("postgres://u:p@postgres:5432/mycelium") == (
        "postgres://u:p@postgres:5432/mycelium_sandbox"
    )
    assert bootstrap.sandbox_url("postgres://u:p@h/db?sslmode=require") == (
        "postgres://u:p@h/mycelium_sandbox?sslmode=require"
    )
    with pytest.raises(bootstrap.NotSandboxed):
        bootstrap.sandbox_url("")


@pytest.mark.django_db
def test_the_guard_refuses_any_other_database():
    # The suite runs on the test database, which is exactly what must refuse.
    with pytest.raises(bootstrap.NotSandboxed):
        bootstrap.assert_sandboxed()


def test_the_world_is_the_same_every_time():
    assert (
        world.build(seed=7, people=40).as_dict()
        == world.build(seed=7, people=40).as_dict()
    )
    assert (
        world.build(seed=7, people=40).as_dict()
        != world.build(seed=8, people=40).as_dict()
    )


def test_every_person_has_a_declared_only_topic_and_an_undeclared_method():
    built = world.build(people=64)
    for person in built.people:
        assert person.declared_only in person.declared_areas
        assert person.declared_only not in world.PROBLEMS[person.field]
        declared = {
            m.lower() for m in person.declared_keywords + person.declared_skills
        }
        assert world.method(person.undeclared_method).names[0].lower() not in declared
        assert {paper.method for paper in person.papers} <= set(person.methods)


def test_no_project_member_declares_the_uncovered_need():
    built = world.build(people=96)
    people = {p.key: p for p in built.people}
    assert built.projects
    for project in built.projects:
        declared = {
            k.lower()
            for key in project.members
            for k in people[key].declared_keywords + people[key].declared_skills
        }
        assert project.uncovered_need.lower() not in declared


def test_methods_cross_fields_and_near_misses_are_planted():
    crossing = [m for m in world.METHODS if len(m.fields) > 1]
    assert len(crossing) >= 10
    assert {m.near_miss_of for m in world.METHODS} >= {"kalman", "rf"}
    assert all(m.signature for m in world.METHODS)


def test_a_generated_abstract_is_checked_for_its_method():
    paper = world.build(people=8).papers[0]
    name = paper.method_name
    assert corpus.check(paper, f"We use {name} on data.") == []
    assert corpus.check(paper, "We use a method on data.") == [
        "does not name its method"
    ]
