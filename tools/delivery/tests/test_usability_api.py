"""The "Can we use this?" strip on the feeds (plan Phase 2).

The lab feed judges an item against the lab's profile (institution type, country)
and its buffer, and names coverage from the same people its strip already shows;
a personal feed applies only the reader's own buffer. Fellowship eligibility is a
count, never a name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from apps.accounts.models import Lab, LabMembership, LabProfile
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "usability_records.json").read_text()
)


@pytest.fixture
def lab_and_member(db):
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    LabProfile.objects.filter(lab=lab).update(
        institution_type="higher_ed", country="GB"
    )
    member = User.objects.create_user("ana")
    member.profile.is_verified = True  # profile edits need an activated account
    member.profile.save(update_fields=["is_verified"])
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.OWNER)
    return lab, member


def _grant(key: str) -> ContentItem:
    meta = dict(RECORDS[key])
    meta["deadline_date"] = "2099-01-15"  # keep it open whatever day the suite runs
    meta["prune_after"] = "2099-01-15"
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="open-collector",
        external_id=key,
        metadata=meta,
    )


@pytest.mark.django_db
def test_the_lab_feed_judges_items_against_the_labs_profile(lab_and_member) -> None:
    lab, member = lab_and_member
    item = _grant("nsf_us_only")
    RelevanceScore.objects.create(
        content=item, target_lab=lab, score=0.8, signals={"suggested": True}
    )
    client = APIClient()
    client.force_authenticate(member)

    data = client.get(f"/api/labs/{lab.slug}/recommendations/").data
    usability = data["grants"][0]["usability"]
    checks = {c["key"]: c for c in usability["checks"]}

    assert usability["verdict"] == "block"
    assert checks["country"]["status"] == "block"  # a UK lab, a US-only call
    assert checks["country"]["field"] == "eligibility"
    assert checks["applicant"]["status"] == "ok"
    assert checks["team"]["status"] == "warn"  # nobody's profile was matched


@pytest.mark.django_db
def test_the_personal_feed_applies_only_the_readers_buffer(lab_and_member) -> None:
    _lab, member = lab_and_member
    item = _grant("eu_horizon")
    RelevanceScore.objects.create(
        content=item, target_user=member, score=0.8, signals={"suggested": True}
    )
    client = APIClient()
    client.force_authenticate(member)

    data = client.get("/api/opportunities/grants/").data
    keys = {c["key"] for c in data["items"][0]["usability"]["checks"]}

    assert {"open", "deadline", "feasible"} <= keys
    assert not keys & {"applicant", "country", "team"}


@pytest.mark.django_db
def test_lab_profile_takes_a_two_letter_country(lab_and_member) -> None:
    lab, member = lab_and_member
    client = APIClient()
    client.force_authenticate(member)
    url = f"/api/auth/labs/{lab.slug}/profile/"

    bad = client.patch(url, {"country": "USA"}, format="json")
    good = client.patch(
        url, {"country": "us", "institution_type": "higher_ed"}, format="json"
    )

    assert bad.status_code == 400
    assert good.status_code == 200, good.data
    assert good.data["country"] == "US"
