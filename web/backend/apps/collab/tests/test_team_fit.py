"""The team-fit line is stored with each grant a target was shown.

And the team-gap alert reads a call's required slots once they exist, falling
back to the verified extraction until then.
"""

import pytest
from tools.delivery.matchers import team_gap
from tools.recommendation.models import RelevanceScore
from tools.recommendation.targets import target_for_lab, target_for_user
from tools.retrieval.models import ContentItem

from apps.collab import team_fit
from apps.collab.models import RequirementSlots


def _score(call, **target):
    return RelevanceScore.objects.create(content=call, score=0.5, **target)


def test_a_readers_grants_carry_their_team_fit(world):
    lab, ada, _, call = world
    row = _score(call, target_user=ada)
    paper = ContentItem.objects.create(
        type="paper", source="openalex", external_id="P1"
    )
    other = _score(paper, target_user=ada)
    assert team_fit.annotate_target(target_for_user(ada)) == 1
    row.refresh_from_db()
    fit = row.signals["team_fit"]
    assert (fit["covered"], fit["total"]) == (1, 3)
    assert fit["roles"] == ["local marine park authority"]
    other.refresh_from_db()
    assert "team_fit" not in (other.signals or {})
    assert team_fit.annotate_target(target_for_user(ada)) == 0  # unchanged


def test_a_labs_grants_name_who_covers_each_slot(world):
    lab, _, _, call = world
    row = _score(call, target_lab=lab)
    team_fit.annotate_target(target_for_lab(lab))
    row.refresh_from_db()
    people = {s["text"]: s["people"] for s in row.signals["team_fit"]["slots"]}
    assert people["satellite remote sensing"] == ["ada"]
    assert people["coral reef ecology"] == ["bo"]


def test_a_call_that_loses_its_slots_loses_its_line(world):
    lab, _, _, call = world
    row = _score(call, target_lab=lab)
    team_fit.annotate_target(target_for_lab(lab))
    RequirementSlots.objects.filter(content=call).update(
        status=RequirementSlots.Status.NONE, slots=[]
    )
    team_fit.annotate_target(target_for_lab(lab))
    row.refresh_from_db()
    assert "team_fit" not in row.signals


def test_team_gap_reads_required_slots_once_they_exist(world):
    _, _, _, call = world
    call.metadata = {"ai_fields": {"required_expertise": ["something older"]}}
    call.save()
    assert team_gap.required_expertise(call) == [
        "satellite remote sensing",
        "environmental health",
        "local marine park authority",
    ]


@pytest.mark.django_db
def test_team_gap_falls_back_to_the_extraction_until_then():
    call = ContentItem.objects.create(
        type="grant",
        source="grants",
        external_id="G9",
        metadata={"ai_fields": {"required_expertise": ["clinical trials"]}},
    )
    assert team_gap.required_expertise(call) == ["clinical trials"]
    RequirementSlots.objects.create(
        content=call,
        status=RequirementSlots.Status.THIN,
        prompt_version="s1",
        source_fingerprint="x",
    )
    assert team_gap.required_expertise(call) == ["clinical trials"]


def test_the_backfill_command_annotates_every_target(world, capsys):
    import json

    from django.core.management import call_command

    lab, ada, _, call = world
    _score(call, target_user=ada)
    _score(call, target_lab=lab)
    call_command("annotate_team_fit")
    assert json.loads(capsys.readouterr().out)["rows_changed"] == 2
