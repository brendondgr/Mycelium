"""The team-fit line in the grant payload, and slot feedback."""

import pytest
from rest_framework.test import APIClient
from tools.recommendation.models import RelevanceScore
from tools.recommendation.targets import target_for_lab

from apps.collab import team_fit
from apps.collab.models import SlotFeedback
from apps.content.serializers import GrantSerializer


def test_the_grant_payload_names_who_covers_each_slot(world):
    lab, ada, bo, call = world
    score = RelevanceScore.objects.create(content=call, score=0.5, target_lab=lab)
    team_fit.annotate_target(target_for_lab(lab))
    score.refresh_from_db()
    data = GrantSerializer(score, context={"today": "2026-09-18"}).data["team_fit"]
    assert (data["covered"], data["total"]) == (2, 3)
    people = {s["text"]: s["people"] for s in data["slots"]}
    assert people["satellite remote sensing"] == [{"username": "ada", "name": "ada"}]


def test_a_renamed_lab_mate_shows_their_new_name_and_a_deleted_one_vanishes(world):
    lab, ada, bo, call = world
    score = RelevanceScore.objects.create(content=call, score=0.5, target_lab=lab)
    team_fit.annotate_target(target_for_lab(lab))
    ada.first_name, ada.last_name = "Ada", "Okafor"
    ada.save()
    bo.delete()
    score.refresh_from_db()
    people = {
        s["text"]: s["people"]
        for s in GrantSerializer(score, context={}).data["team_fit"]["slots"]
    }
    assert people["satellite remote sensing"][0]["name"] == "Ada Okafor"
    assert people["coral reef ecology"] == []


def test_a_grant_without_a_line_says_none(world):
    lab, _, _, call = world
    score = RelevanceScore.objects.create(content=call, score=0.5, target_lab=lab)
    assert GrantSerializer(score, context={}).data["team_fit"] is None


@pytest.fixture
def client_for(world):
    def make(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return make


def test_slot_feedback_is_recorded(world, client_for):
    _, ada, _, call = world
    url = f"/api/collab/calls/{call.pk}/slot-feedback/"
    response = client_for(ada).post(
        url, {"kind": "not_a_requirement", "slot_text": "environmental health"}
    )
    assert response.status_code == 201
    response = client_for(ada).post(url, {"kind": "missed_one", "note": "a clinician"})
    assert response.status_code == 201
    assert SlotFeedback.objects.filter(content=call).count() == 2


def test_slot_feedback_is_validated(world, client_for):
    _, ada, _, call = world
    url = f"/api/collab/calls/{call.pk}/slot-feedback/"
    assert client_for(ada).post(url, {"kind": "missed_one"}).status_code == 400
    assert client_for(ada).post(url, {"kind": "we_cover_this"}).status_code == 400
    assert (
        client_for(ada).post(url, {"kind": "love_it", "slot_text": "x"}).status_code
        == 400
    )


def test_slot_feedback_needs_a_signed_in_reader_and_a_grant(world):
    _, _, _, call = world
    url = f"/api/collab/calls/{call.pk}/slot-feedback/"
    assert APIClient().post(
        url, {"kind": "we_cover_this", "slot_text": "x"}
    ).status_code in (401, 403)
