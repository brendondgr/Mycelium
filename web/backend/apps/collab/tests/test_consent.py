"""Consent to be found: verified scope, mutual visibility, expiry, the cap, the preview.

Plan CN-04's acceptance: no row means not findable; a typed institution has no
effect; an expired setting reads as off without a job; the preview lists no
conversational and no project edge; no response carries an appearance count.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuthorWork
from apps.collab import affiliation, consent, preview, tasks
from apps.collab.models import Appearance, Audience, CollaborationSetting
from apps.content.models import Notification
from apps.knowledge import demonstrated, service
from apps.knowledge.models import Edge, Relation, Tier, WorkFacets
from apps.research.models import Project


def _person(username, email, *, verified=True, **interests):
    user = User.objects.create_user(username, email, "pw")
    user.profile.is_verified = verified
    user.profile.interests = interests
    user.profile.save()
    return user


@pytest.fixture
def ada(db):
    return _person("ada", "ada@cs.ox.ac.uk", areas=["Kelp forests"])


# --- verified scope ---------------------------------------------------------


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("fsu.edu", ("fsu.edu", "US")),
        ("med.umich.edu", ("umich.edu", "US")),
        ("cs.ox.ac.uk", ("oxford.ac.uk", "GB")),  # an alternate domain, a subdomain
        ("gmail.com", None),
        ("ac.uk", None),
    ],
)
def test_a_domain_resolves_to_its_institution(domain, expected):
    found = affiliation.resolve_domain(domain)
    assert (found and (found.domain, found.country)) == expected or (
        found is None and expected is None
    )


def test_only_a_verified_email_places_a_person(db):
    user = _person("bo", "bo@fsu.edu", verified=False)
    assert affiliation.refresh(user) is None
    user.profile.is_verified = True
    user.profile.save()
    row = affiliation.refresh(user)
    assert (row.domain, row.country) == ("fsu.edu", "US")


def test_a_typed_institution_changes_nothing(db):
    user = _person("cy", "cy@gmail.com")
    user.profile.institution = "Florida State University"
    user.profile.save()
    row = affiliation.refresh(user)
    assert row.domain == "" and row.country == ""
    # A personal address places nobody, so there is no audience to offer.
    assert consent.allowed_audiences(consent.place_of(user)) == []


def test_unverified_email_loses_its_scope(db):
    user = _person("dee", "dee@fsu.edu")
    affiliation.refresh(user)
    user.profile.is_verified = False
    user.profile.save()
    assert affiliation.refresh(user) is None
    assert not hasattr(User.objects.get(pk=user.pk), "verified_affiliation")


# --- the setting ------------------------------------------------------------


def test_no_row_means_not_findable(ada):
    assert not consent.is_open(ada)


def test_turning_it_on_lasts_six_months_and_lapses_by_itself(ada, settings):
    setting = consent.update(ada, open=True, audience=Audience.INSTITUTION)
    months = (setting.expires_at - timezone.now()).days
    assert (
        30 * settings.COLLAB_OPEN_MONTHS - 1
        <= months
        <= 30 * settings.COLLAB_OPEN_MONTHS
    )
    later = setting.expires_at + timedelta(seconds=1)
    assert consent.is_open(ada) and not consent.is_open(ada, now=later)


def test_changing_the_audience_keeps_the_expiry_and_renewing_restarts_it(ada):
    first = consent.update(ada, open=True, audience=Audience.INSTITUTION).expires_at
    same = consent.update(ada, open=True, audience=Audience.COUNTRY).expires_at
    assert same == first
    renewed = consent.update(ada, open=True, audience=Audience.COUNTRY, renew=True)
    assert renewed.expires_at > first


def test_turning_it_off_is_immediate(ada):
    consent.update(ada, open=True, audience=Audience.ANYWHERE)
    consent.update(ada, open=False, audience=Audience.ANYWHERE)
    assert not consent.is_open(ada)


def test_refusals(db):
    unverified = _person("eve", "eve@fsu.edu", verified=False)
    with pytest.raises(consent.ConsentRefused):
        consent.update(unverified, open=True, audience=Audience.ANYWHERE)
    personal = _person("fay", "fay@gmail.com")
    for audience in Audience.values:
        with pytest.raises(consent.ConsentRefused):
            consent.update(personal, open=True, audience=audience)
    assert not consent.is_open(personal)
    with pytest.raises(consent.ConsentRefused):
        consent.update(unverified, open=True, audience="galaxy")
    with pytest.raises(consent.ConsentRefused):
        consent.update(unverified, open=True, audience=Audience.ANYWHERE, open_to=["x"])


# --- mutual visibility ------------------------------------------------------


FSU = consent.Place("fsu.edu", "US")
UFL = consent.Place("ufl.edu", "US")
OXF = consent.Place("oxford.ac.uk", "GB")
NOWHERE = consent.Place("", "")


@pytest.mark.parametrize(
    ("candidate", "audience", "seeker", "scope", "visible"),
    [
        (FSU, "institution", FSU, "institution", True),
        (FSU, "institution", UFL, "anywhere", False),  # the audience says no
        (FSU, "country", UFL, "country", True),
        (FSU, "country", OXF, "anywhere", False),
        (FSU, "anywhere", OXF, "institution", False),  # the seeker's scope says no
        (FSU, "anywhere", OXF, "anywhere", True),
        (NOWHERE, "anywhere", FSU, "anywhere", True),
        (NOWHERE, "anywhere", FSU, "country", False),  # no country to be inside
        (FSU, "anywhere", None, "anywhere", False),  # an unverified seeker
    ],
)
def test_both_sides_must_allow_it(candidate, audience, seeker, scope, visible):
    assert consent.mutually_visible(candidate, audience, seeker, scope) is visible


# --- the appearance cap ------------------------------------------------------


def test_the_cap_lets_known_seekers_keep_seeing_and_stops_new_ones(ada, settings):
    settings.COLLAB_APPEARANCE_CAP = 3
    seekers = [_person(f"s{i}", f"s{i}@fsu.edu") for i in range(5)]
    for seeker in seekers[:3]:
        assert consent.may_appear(ada, seeker)
        consent.record_appearance(ada, seeker)
    assert not consent.may_appear(ada, seekers[3])
    assert consent.may_appear(ada, seekers[0])
    next_week = timezone.now() + timedelta(days=7)
    assert consent.may_appear(ada, seekers[3], now=next_week)


def test_old_appearances_are_pruned(ada):
    seeker = _person("s", "s@fsu.edu")
    consent.record_appearance(ada, seeker)
    Appearance.objects.update(created_at=timezone.now() - timedelta(weeks=9))
    assert consent.prune_appearances() == 1


# --- the preview ------------------------------------------------------------


def test_the_preview_shows_only_what_a_search_could_match(ada, embedder):
    service.project_declared(ada)
    work = AuthorWork.objects.create(
        user=ada, source="openalex", source_id="W1", title="x"
    )
    WorkFacets.objects.create(author_work=work, terms={"method": ["kriging"]})
    demonstrated.record_person(ada)
    view = service.record_conversational(
        ada, surface="causal inference", relation=Relation.INTERESTED_IN
    )
    service.confirm(ada, view.concept_id, Relation.INTERESTED_IN)
    project = Project.objects.create(name="Secret", scope_user=ada)
    project.members.add(ada)
    from apps.research.models import ProjectState

    ProjectState.objects.create(project=project, slow={"method": ["unpublished trick"]})
    service.project_declared(project)
    assert Edge.objects.filter(project=project).exists()

    shown = preview.preview(ada)
    labels = {
        item["label"]: item["sources"]
        for items in shown["facets"].values()
        for item in items
    }
    assert labels["Kelp forests"] == ["from your profile"]
    assert labels["kriging"] == ["from your papers"]
    assert "causal inference" not in labels
    assert "unpublished trick" not in labels
    assert shown["institution"] == "University of Oxford"
    assert set(shown) == {"name", "institution", "facets"}
    assert Edge.objects.filter(user=ada, tier=Tier.CONVERSATIONAL).exists()


# --- the API ---------------------------------------------------------------


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_the_settings_api(ada):
    client = _client(ada)
    body = client.get("/api/collab/settings/").json()
    assert body["open"] is False and body["verified"] is True
    assert body["allowed_audiences"] == ["institution", "country", "anywhere"]
    body = client.put(
        "/api/collab/settings/",
        {"open": True, "audience": "country", "open_to": ["co_authoring"]},
        format="json",
    ).json()
    assert body["open"] and body["audience"] == "country" and body["expires_at"]
    assert body["institution"] == "University of Oxford"
    assert not {"appearances", "seen_by", "searches"} & set(body)


def test_the_settings_api_refuses_a_bad_choice(db):
    user = _person("gus", "gus@gmail.com")
    response = _client(user).put(
        "/api/collab/settings/",
        {"open": True, "audience": "institution"},
        format="json",
    )
    assert response.status_code == 400


def test_the_preview_api(ada, embedder):
    service.project_declared(ada)
    body = _client(ada).get("/api/collab/preview/").json()
    assert body["facets"]["area"][0]["label"] == "Kelp forests"


def test_the_api_needs_a_signed_in_person(db):
    assert APIClient().get("/api/collab/settings/").status_code in (401, 403)


# --- renewal ----------------------------------------------------------------


def test_people_are_reminded_once_before_it_ends(ada, settings):
    consent.update(ada, open=True, audience=Audience.INSTITUTION)
    CollaborationSetting.objects.filter(user=ada).update(
        expires_at=timezone.now() + timedelta(days=5)
    )
    assert tasks.notify_renewals() == 1
    assert tasks.notify_renewals() == 0
    note = Notification.objects.get(user=ada, kind=Notification.Kind.COLLAB_RENEWAL)
    assert "ends soon" in note.title
    assert "search" not in note.title.lower()
