"""What Mylo records, per server and per project (settings plan, Phase 4).

Both halves must be on for anything to be recorded: the head's switch on the
server and the member's own. The head's off wins — a member cannot turn
recording back on in a server its lab or department switched off.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership
from apps.ambient.attribution import candidates_for
from apps.ambient.eligibility import observable
from apps.ambient.ingest import IncomingMessage, record
from apps.ambient.models import (
    ChannelHint,
    ListeningConsent,
    PlaceKind,
    Platform,
    RawMessageRef,
    RecordingExclusion,
    Source,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.testing import bind
from apps.research.models import Project, ProjectMember

GUILD = "900000000000000077"


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-recording-tests",
        },
    }
    caches["ambient"].clear()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def source(lab) -> Source:
    bind(lab=lab, guild_id=GUILD, guild_name="PULSE server")
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id=GUILD,
        label="PULSE",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


def _person(name: str, lab: Lab, role: str = LabMembership.Role.MEMBER) -> User:
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    LabMembership.objects.create(lab=lab, user=user, role=role)
    return user


@pytest.fixture
def ada(lab) -> User:
    return _person("ada", lab)


@pytest.fixture
def owner(lab) -> User:
    return _person("olu", lab, LabMembership.Role.OWNER)


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def _message(speaker, *, place_id="555", external_id="m1") -> IncomingMessage:
    return IncomingMessage(
        external_id=external_id,
        text="We should try conformal prediction on the imaging data",
        sent_at=timezone.now(),
        place_kind=PlaceKind.CHANNEL,
        place_id=place_id,
        place_label="methods",
        speaker=speaker,
        speaker_external_id="111",
    )


# -- the member's per-server switch -------------------------------------------


def test_a_member_can_keep_one_server_out(ada, source):
    assert observable(ada, source)
    response = _client(ada).post(
        "/api/ambient/recording/", {"server": source.pk, "record": False}, format="json"
    )
    assert response.status_code == 200, response.content
    row = response.json()["servers"][0]
    assert row["excluded"] and not row["recording"] and not row["locked"]
    assert observable(ada, source).reason == "person_excluded_server"
    assert not record(source, _message(ada)).stored


def test_keeping_a_server_out_discards_what_is_waiting_to_be_read(ada, source):
    assert record(source, _message(ada)).stored
    _client(ada).post(
        "/api/ambient/recording", {"server": source.pk, "record": False}, format="json"
    )
    assert not RawMessageRef.objects.filter(source=source, speaker=ada).exists()


def test_lifting_the_exclusion_records_again(ada, source):
    RecordingExclusion.objects.create(user=ada, source=source)
    response = _client(ada).post(
        "/api/ambient/recording/", {"server": source.pk, "record": True}, format="json"
    )
    assert response.status_code == 200
    assert observable(ada, source)


def test_someone_elses_server_is_not_listed_or_switchable(db, source):
    stranger = User.objects.create_user("zed", "zed@example.org", "pw")
    client = _client(stranger)
    assert client.get("/api/ambient/recording/").json()["servers"] == []
    response = client.post(
        "/api/ambient/recording/", {"server": source.pk, "record": False}, format="json"
    )
    assert response.status_code == 404


# -- the head's switch wins ---------------------------------------------------


def test_a_member_cannot_switch_listening_back_on_where_the_head_turned_it_off(
    ada, owner, source
):
    response = _client(owner).post(
        "/api/ambient/servers/lab/pulse/",
        {"guild_id": GUILD, "on": False},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["servers"][0]["listening"] is False

    state = _client(ada).get("/api/ambient/recording/").json()["servers"][0]
    assert state["locked"] and not state["recording"]
    assert "Only its lab or department" in state["locked_reason"]

    refused = _client(ada).post(
        "/api/ambient/recording/", {"server": source.pk, "record": True}, format="json"
    )
    assert refused.status_code == 403
    source.refresh_from_db()
    assert observable(ada, source).reason == "source_not_consented"

    # The head turns it back on; the member's own switch decides again.
    _client(owner).post(
        "/api/ambient/servers/lab/pulse", {"guild_id": GUILD, "on": True}, format="json"
    )
    source.refresh_from_db()
    assert observable(ada, source)


def test_only_a_server_manager_holds_the_heads_switch(ada, source):
    client = _client(ada)
    assert client.get("/api/ambient/servers/lab/pulse/").status_code == 403
    response = client.post(
        "/api/ambient/servers/lab/pulse/",
        {"guild_id": GUILD, "on": False},
        format="json",
    )
    assert response.status_code == 403
    source.refresh_from_db()
    assert source.listening


def test_the_head_cannot_switch_a_server_the_org_is_not_in(owner, source):
    response = _client(owner).post(
        "/api/ambient/servers/lab/pulse/",
        {"guild_id": "123456789012345678", "on": False},
        format="json",
    )
    assert response.status_code == 404


def test_a_department_head_switches_the_department_server(db):
    head = User.objects.create_user("hal", "hal@example.org", "pw")
    department = Department.objects.create(name="Physics", owner=head)
    bind(department=department, guild_id="900000000000000088", guild_name="Physics")
    client = _client(head)
    listed = client.get(f"/api/ambient/servers/department/{department.pk}/").json()
    assert [s["name"] for s in listed["servers"]] == ["Physics"]
    response = client.post(
        f"/api/ambient/servers/department/{department.pk}/",
        {"guild_id": "900000000000000088", "on": True},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert Source.objects.get(external_id="900000000000000088").listening


# -- the member's per-project switch ------------------------------------------


def test_a_project_kept_out_is_never_an_attribution_candidate(ada, lab, source):
    mine = Project.objects.create(name="Imaging", scope_user=ada)
    on = Project.objects.create(name="Shared", scope_lab=lab)
    ProjectMember.objects.create(project=on, user=ada)
    names = {c.name for c in candidates_for(ada, source, place_kind="channel")}
    assert names == {"Imaging", "Shared"}

    response = _client(ada).post(
        "/api/ambient/recording/",
        {"project": str(mine.pk), "record": False},
        format="json",
    )
    assert response.status_code == 200, response.content
    names = {c.name for c in candidates_for(ada, source, place_kind="channel")}
    assert names == {"Shared"}
    listed = {p["name"]: p["excluded"] for p in response.json()["projects"]}
    assert listed == {"Imaging": True, "Shared": False}


def test_a_channel_tied_to_an_excluded_project_does_not_record_the_person(
    ada, owner, source
):
    project = Project.objects.create(name="Imaging", scope_user=ada)
    ChannelHint.objects.create(source=source, place_id="777", project=project)
    RecordingExclusion.objects.create(user=ada, project=project)

    refused = record(source, _message(ada, place_id="777"))
    assert not refused.stored and refused.reason == "person_excluded_project"
    # Elsewhere in the server, and other people in that channel, are unaffected.
    assert record(source, _message(ada, place_id="555", external_id="m2")).stored
    assert record(source, _message(owner, place_id="777", external_id="m3")).stored


def test_a_project_the_person_cannot_see_is_refused(ada, db):
    other = User.objects.create_user("bo", "bo@example.org", "pw")
    theirs = Project.objects.create(name="Theirs", scope_user=other)
    response = _client(ada).post(
        "/api/ambient/recording/",
        {"project": str(theirs.pk), "record": False},
        format="json",
    )
    assert response.status_code == 404
    assert not RecordingExclusion.objects.exists()
