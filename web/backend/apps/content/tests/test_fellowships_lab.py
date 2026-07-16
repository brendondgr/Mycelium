"""R8 — fellowships for labs: eligible-only, opt-in, never reveal the ineligible.

The load-bearing privacy invariant (D-11): a lab fellowship surface names only
members who are eligible AND have opted into lab-visible eligibility. An ineligible
member — or an eligible member who hasn't consented — is never named, so citizenship
or career stage can't be inferred.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership, Profile
from apps.content.models import ContentItem, RelevanceScore
from apps.content.views import _lab_eligible_fellowships


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="Lab", slug="lab")


def _member(lab, username, *, consented):
    user = User.objects.create_user(username)
    LabMembership.objects.create(user=user, lab=lab)
    Profile.objects.filter(user=user).update(
        interests={"eligibility": {"lab_visible": consented, "citizenship": "us"}}
    )
    return user


def _fellowship(ext="f1"):
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id=ext,
        metadata={
            "title": f"Fellowship {ext}",
            "amount_raw": "$30,000",
            "deadline_date": "2026-12-01",
            "award_class": "fellowship",
            "deadline": {"type": "true"},
        },
    )


def _score(user, fellowship, tier):
    return RelevanceScore.objects.create(
        content=fellowship,
        target_user=user,
        score=0.8,
        signals={"tier": tier, "suggested": True, "reason": "personal detail"},
    )


@pytest.mark.django_db
def test_lab_fellowship_names_only_eligible_consenting_members(lab) -> None:
    fellowship = _fellowship()
    a = _member(lab, "qualified-yes", consented=True)
    b = _member(lab, "conditional-yes", consented=True)
    c = _member(lab, "ineligible-yes", consented=True)
    d = _member(lab, "qualified-no", consented=False)
    _score(a, fellowship, "qualified")
    _score(b, fellowship, "conditional")
    _score(c, fellowship, "not_eligible")
    _score(d, fellowship, "qualified")

    cards = _lab_eligible_fellowships([a.id, b.id, c.id, d.id])
    assert len(cards) == 1
    named = {m["username"]: m["tier"] for m in cards[0]["eligible"]}
    assert named == {"qualified-yes": "qualified", "conditional-yes": "conditional"}
    # The ineligible member and the non-consenting member are never named.
    assert "ineligible-yes" not in named
    assert "qualified-no" not in named


@pytest.mark.django_db
def test_fellowship_hidden_when_no_eligible_member_consents(lab) -> None:
    fellowship = _fellowship()
    eligible_no_consent = _member(lab, "qualified-no", consented=False)
    _score(eligible_no_consent, fellowship, "qualified")
    assert _lab_eligible_fellowships([eligible_no_consent.id]) == []


@pytest.mark.django_db
def test_fellowship_hidden_when_only_ineligible_consent(lab) -> None:
    fellowship = _fellowship()
    ineligible = _member(lab, "ineligible-yes", consented=True)
    _score(ineligible, fellowship, "not_eligible")
    assert _lab_eligible_fellowships([ineligible.id]) == []


@pytest.mark.django_db
def test_lab_fellowship_card_leaks_no_personal_reasoning(lab) -> None:
    fellowship = _fellowship()
    a = _member(lab, "a", consented=True)
    _score(a, fellowship, "qualified")
    card = _lab_eligible_fellowships([a.id])[0]
    # Public fellowship fields + the eligible list only — no member's match reason.
    assert card["title"] == "Fellowship f1"
    assert card["amount"] == "$30,000"
    assert "reason" not in card
    assert "gates_failed" not in card
    assert set(card["eligible"][0]) == {"username", "name", "initials", "tier"}


@pytest.mark.django_db
def test_lab_recommendations_api_includes_fellowships(lab) -> None:
    from rest_framework.test import APIClient

    fellowship = _fellowship()
    owner = User.objects.create_user("owner")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    Profile.objects.filter(user=owner).update(
        interests={"eligibility": {"lab_visible": True}}
    )
    _score(owner, fellowship, "qualified")

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    assert resp.status_code == 200
    assert resp.data["counts"]["fellowships"] == 1
    assert resp.data["fellowships"][0]["eligible"][0]["username"] == "owner"
