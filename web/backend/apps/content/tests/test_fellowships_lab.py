"""Lab fellowships: the lab's own feed, plus the eligibility disclosure gate.

Two invariants live here.

**Parity.** A lab's Fellowships page is the lab's own matched feed — the same
``RelevanceScore`` rows, the same serializer, the same card as the personal page —
because a lab has no citizenship or career stage and so ranks fellowships on
research fit alone. It is emphatically *not* a union of whatever its members
happen to personally qualify for.

**Privacy (D-11).** Personal eligibility did not stop being personal. Where it
appears at all — as one basis inside ``recommended_for`` — it names only members
who are eligible AND opted into lab-visible eligibility. An ineligible member, or
an eligible member who has not consented, is never named as eligible, so
citizenship or career stage can't be inferred from the lab surface.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership, Profile
from apps.content.models import ContentItem, RelevanceScore
from apps.content.views import _consented_eligibility


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="Lab", slug="lab")


def _member(lab, username, *, consented, role=LabMembership.Role.MEMBER):
    user = User.objects.create_user(username)
    LabMembership.objects.create(user=user, lab=lab, role=role)
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


def _lab_score(lab, fellowship, *, verdict="skim", member_fit=None):
    signals = {"suggested": True, "verdict": verdict, "source": "llm"}
    if member_fit is not None:
        signals["member_fit"] = member_fit
    return RelevanceScore.objects.create(
        content=fellowship, target_lab=lab, score=0.7, signals=signals
    )


# --------------------------------------------------------------------------- #
# The disclosure gate
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_eligibility_names_only_eligible_consenting_members(lab) -> None:
    fellowship = _fellowship()
    a = _member(lab, "qualified-yes", consented=True)
    b = _member(lab, "conditional-yes", consented=True)
    c = _member(lab, "ineligible-yes", consented=True)
    d = _member(lab, "qualified-no", consented=False)
    _score(a, fellowship, "qualified")
    _score(b, fellowship, "conditional")
    _score(c, fellowship, "not_eligible")
    _score(d, fellowship, "qualified")

    named = _consented_eligibility(
        [a.id, b.id, c.id, d.id], [fellowship.id]
    )[str(fellowship.id)]
    assert named == {"qualified-yes": "qualified", "conditional-yes": "conditional"}
    # The ineligible member and the non-consenting member are never named.
    assert "ineligible-yes" not in named
    assert "qualified-no" not in named


@pytest.mark.django_db
def test_no_eligibility_named_when_nobody_consents(lab) -> None:
    fellowship = _fellowship()
    eligible_no_consent = _member(lab, "qualified-no", consented=False)
    _score(eligible_no_consent, fellowship, "qualified")
    assert _consented_eligibility([eligible_no_consent.id], [fellowship.id]) == {}


@pytest.mark.django_db
def test_no_eligibility_named_when_only_ineligible_consent(lab) -> None:
    fellowship = _fellowship()
    ineligible = _member(lab, "ineligible-yes", consented=True)
    _score(ineligible, fellowship, "not_eligible")
    assert _consented_eligibility([ineligible.id], [fellowship.id]) == {}


# --------------------------------------------------------------------------- #
# The feed itself
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lab_fellowship_feed_is_the_labs_own_matches(lab) -> None:
    """The feed is what the lab matched — not what its members qualify for."""
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    matched = _fellowship("matched")
    _lab_score(lab, matched)
    # A fellowship only a member personally qualifies for is *not* the lab's feed.
    personal_only = _fellowship("personal-only")
    _score(owner, personal_only, "qualified")

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    assert resp.status_code == 200
    assert resp.data["counts"]["fellowships"] == 1
    row = resp.data["fellowships"][0]
    # The personal fellowship serializer shape, same as the personal page.
    assert row["title"] == "Fellowship matched"
    assert row["verdict"] == "skim"
    assert row["award_class"] == "fellowship"
    assert "eligibility" in row and "stages" in row and "citizenship" in row


@pytest.mark.django_db
def test_lab_fellowship_carries_eligibility_as_a_recommendation_basis(lab) -> None:
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    quiet = _member(lab, "quiet", consented=False)
    fellowship = _fellowship()
    _lab_score(
        lab,
        fellowship,
        member_fit=[
            {
                "username": "owner",
                "fit": 81,
                "reason": "Mylo's line.",
                "source": "llm",
            },
            {
                "username": "quiet",
                "fit": 64,
                "reason": "Overlap line.",
                "source": "similarity",
            },
        ],
    )
    _score(owner, fellowship, "qualified")
    _score(quiet, fellowship, "qualified")

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    rows = {r["username"]: r for r in resp.data["recommended_for"][str(fellowship.id)]}
    # Both members are recommended on research fit …
    assert set(rows) == {"owner", "quiet"}
    assert rows["owner"]["reason"] == "Mylo's line."
    # … but only the consenting one has their eligibility disclosed.
    assert rows["owner"]["basis"] == ["profile_fit", "eligible"]
    assert rows["owner"]["tier"] == "qualified"
    assert rows["quiet"]["basis"] == ["profile_fit"]
    assert "tier" not in rows["quiet"]


# --------------------------------------------------------------------------- #
# Eligibility subtracts: who a lab fellowship must never be recommended to
# --------------------------------------------------------------------------- #


def _staged_member(lab, username, *, stage, consented=False):
    """A member placed on the career ladder, for the subtractive gate."""
    user = User.objects.create_user(username)
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    Profile.objects.filter(user=user).update(
        interests={
            "eligibility": {
                "citizenship": "us",
                "stage": stage,
                "lab_visible": consented,
            }
        }
    )
    return user


def _postdoc_only(ext="postdoc-award"):
    """An award the Illinois facets mark postdoctoral — the reported case."""
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id=ext,
        metadata={
            "title": "NSF Postdoctoral Research Fellowship",
            "award_class": "fellowship",
            "deadline": {"type": "true", "date": "2026-12-01"},
            "facets": {
                "citizenship": ["US Citizens, Nationals, or Permanent Residents"],
                "stage": ["Postdoctoral/Post-graduate"],
                "field": ["Sciences/Engineering/Math"],
                "award_type": ["Fellowship/Grant"],
                "limits": [],
                "other": [],
            },
            "flags": {},
        },
    )


@pytest.mark.django_db
def test_lab_strip_never_names_a_member_the_award_excludes(lab) -> None:
    """The lab feed has no eligibility gate — a lab has no career stage — so a
    postdoc-only award in a student's exact subfield ranks high and names them on
    topical cosine alone. Eligibility has to subtract at the recommendation layer.
    """
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    _staged_member(lab, "student", stage="doctoral_early")
    _staged_member(lab, "postdoc", stage="postdoc")
    fellowship = _postdoc_only()
    _lab_score(
        lab,
        fellowship,
        member_fit=[
            {"username": "student", "fit": 88, "reason": "Exact subfield.",
             "source": "llm"},
            {"username": "postdoc", "fit": 61, "reason": "Adjacent work.",
             "source": "llm"},
        ],
    )

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    named = {r["username"] for r in resp.data["recommended_for"][str(fellowship.id)]}
    assert named == {"postdoc"}


@pytest.mark.django_db
def test_the_exclusion_discloses_nothing(lab) -> None:
    """A dropped member leaves no trace — no name, no tier, no basis entry. That is
    why it needs no lab_visible consent: it publishes less, not more."""
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    student = _staged_member(lab, "student", stage="doctoral_early", consented=True)
    fellowship = _postdoc_only()

    _lab_score(
        lab,
        fellowship,
        member_fit=[
            {"username": "student", "fit": 88, "reason": "Exact subfield.",
             "source": "llm"},
        ],
    )
    _score(student, fellowship, "qualified")  # a stale personal row still naming them

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    assert str(fellowship.id) not in resp.data["recommended_for"]


# --------------------------------------------------------------------------- #
# One scale per label
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_two_member_signals_are_separate_fields(lab) -> None:
    """A cosine and a verdict are different claims about the same member.

    Merging them into one ``fit`` made a single card show one person twice, in two
    scales. They stay two fields, and only the cosine is still a number — the
    member's own feed now carries a verdict rather than a percent."""
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    fellowship = _fellowship()
    _lab_score(
        lab,
        fellowship,
        member_fit=[
            {"username": "owner", "fit": 66, "reason": "Mylo's line.",
             "source": "llm"},
        ],
    )
    RelevanceScore.objects.create(
        content=fellowship,
        target_user=owner,
        score=0.9,
        signals={"tier": "qualified", "suggested": True, "verdict": "read"},
    )

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    row = resp.data["recommended_for"][str(fellowship.id)][0]
    assert row["profile_cosine"] == 66
    assert row["own_feed_verdict"] == "read"
    assert "fit" not in row
    assert "own_feed_percent" not in row


@pytest.mark.django_db
def test_the_explained_member_leads_the_strip(lab) -> None:
    """Sorting a mixed-scale column ranked own-feed-only members above the ones
    Mylo wrote a rationale for, purely because the model's scale runs hotter — and
    the card opens the first member's reason by default."""
    from rest_framework.test import APIClient

    owner = _member(lab, "owner", consented=True, role=LabMembership.Role.OWNER)
    other = _member(lab, "other", consented=False)
    fellowship = _fellowship()
    _lab_score(
        lab,
        fellowship,
        member_fit=[
            {"username": "owner", "fit": 66, "reason": "Mylo's line.",
             "source": "llm"},
        ],
    )
    # `other` has no member_fit row at all, only a hot personal score.
    RelevanceScore.objects.create(
        content=fellowship,
        target_user=other,
        score=0.9,
        signals={"tier": "qualified", "suggested": True, "verdict": "read"},
    )

    client = APIClient()
    client.force_authenticate(owner)
    resp = client.get(f"/api/labs/{lab.slug}/recommendations/")
    rows = resp.data["recommended_for"][str(fellowship.id)]
    assert [r["username"] for r in rows] == ["owner", "other"]
