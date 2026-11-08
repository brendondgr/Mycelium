"""The department path (plan Phase 7, "What a department sees").

A department hears only about calls a lab could not take on alone; its post says
why (the reason and the quoted sentence), names labs (never people), never tags
anyone, and carries kind and reason tags in its one forum. A department fellowship
shows counts only and tells each eligible member by DM. A lab in the same server
keeps its own channels, and neither changes when the other is switched off.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.recommendation.fellowships import US_FACET
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import (
    Announcement,
    AnnouncementPost,
    AnnouncementSettings,
    ContentItem,
)

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    LabProfile,
    Profile,
)
from apps.content import (
    announce,
    announcement_setup,
    discord_announcements,
    lab_fit,
)
from apps.integrations.models import DiscordIdentity, DiscordOutboxMessage
from apps.integrations.testing import add_route, bind

TODAY = timezone.localdate()
FAR = (TODAY + timedelta(days=90)).isoformat()
VEC_A = [1.0, 0.0, 0.0]
VEC_B = [0.0, 1.0, 0.0]
LIMITED = "Limited submission: each university may submit only two proposals."
_n = iter(range(1, 10_000))


def _department(*, seeded=True):
    owner = User.objects.create_user(f"head{next(_n)}")
    dept = Department.objects.create(owner=owner, name="Earth Sciences")
    row = AnnouncementSettings.objects.create(
        target_department=dept,
        enabled=True,
        seeded_at=timezone.now() if seeded else None,
    )
    return announce.Target("department", dept, row)


def _lab(dept, name, vector, areas=()):
    lab = Lab.objects.create(name=name, slug=name.lower().replace(" ", "-"))
    lab.department = dept
    lab.save(update_fields=["department"])
    profile, _ = LabProfile.objects.get_or_create(lab=lab)
    profile.embedding = vector
    profile.areas = list(areas)
    profile.save()
    return lab


def _item(kind=ContentItem.Type.GRANT, *, vector=VEC_A, **meta):
    n = next(_n)
    base = {
        "title": f"Call {n}",
        "status": "open",
        "funder": "NSF",
        "deadline_date": FAR,
        "prune_after": FAR,
    }
    if kind == ContentItem.Type.FELLOWSHIP:
        base["deadline"] = {"type": "true", "date": FAR}
    base.update(meta)
    return ContentItem.objects.create(
        type=kind,
        source="open-collector",
        external_id=f"d{n}",
        source_url="https://example.org/call",
        metadata=base,
        embedding=vector,
    )


def _slate(target, item, rank=1):
    return RelevanceScore.objects.create(
        content=item,
        target_department=target.obj,
        score=1 / rank,
        signals={
            "suggested": True,
            "cluster_slates": {
                "c1": {
                    "label": "Ocean forecasting",
                    "rank": rank,
                    "of": 10,
                    "entered_on": TODAY.isoformat(),
                    "is_new": True,
                }
            },
        },
    )


def _run(target, poster=None):
    target.settings.refresh_from_db()
    posted = []
    announce.run_target(
        target,
        TODAY,
        dry_run=False,
        complete=None,
        poster=poster or posted.append,
    )
    return posted


# --------------------------------------------------------------------------- #
# Selection and alignment
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_department_hears_only_department_level_calls() -> None:
    target = _department()
    lab_level = _item(eligibility="Any investigator at an eligible institution.")
    limited = _item(eligibility=LIMITED)
    training = _item(activity_codes=["T32"])
    for rank, item in enumerate((lab_level, limited, training), start=1):
        _slate(target, item, rank)

    posted = _run(target)

    assert {a.content_id for a in posted} == {limited.id, training.id}
    reasons = {
        a.content_id: [r["key"] for r in a.alignment["dept_reasons"]] for a in posted
    }
    assert reasons[limited.id] == ["institutional_selection"]
    assert reasons[training.id] == ["department_programme"]
    evidence = Announcement.objects.get(content=limited).alignment["dept_reasons"][0]
    assert evidence["evidence"] == LIMITED
    assert not Announcement.objects.filter(content=lab_level).exists()


@pytest.mark.django_db
def test_the_department_seed_spends_its_places_only_on_department_level_calls() -> (
    None
):
    target = _department(seeded=False)
    lab_level = [_item() for _ in range(3)]
    dept_level = [_item(eligibility=LIMITED) for _ in range(2)]
    for rank, item in enumerate([*lab_level, *dept_level], start=1):
        _slate(target, item, rank)

    posted = _run(target)

    assert {a.content_id for a in posted} == {i.id for i in dept_level}
    # A lab-level call is not "seen" by the department: it was never a candidate.
    assert not Announcement.objects.filter(content__in=lab_level).exists()


@pytest.mark.django_db
def test_the_post_names_labs_that_could_lead_never_people() -> None:
    target = _department()
    _lab(target.obj, "Ocean ML", VEC_A, areas=["ocean forecasting"])
    _lab(target.obj, "Soil Lab", VEC_B)
    item = _item(eligibility=LIMITED, description="Advances in ocean forecasting.")
    _slate(target, item)

    (ann,) = _run(target)

    people = ann.alignment["people"]
    assert [p["name"] for p in people] == ["Ocean ML"]  # Soil Lab is below the floor
    assert people[0]["why"] == "ocean forecasting"
    assert "user_id" not in people[0]
    team = next(c for c in ann.checks if c["key"] == "team")
    assert team["label"] == "Ocean ML could lead" and team["field"] == "lab_fit"
    assert [p["name"] for p in ann.write_up["who_should_look"]] == ["Ocean ML"]


@pytest.mark.django_db
def test_lab_fit_ranks_by_cosine_above_the_floor() -> None:
    target = _department()
    _lab(target.obj, "Near", [0.9, 0.1, 0.0])
    _lab(target.obj, "Exact", VEC_A)
    _lab(target.obj, "Far", VEC_B)
    Lab.objects.create(name="No profile", slug="no-profile", department=target.obj)
    item = _item()

    ranked = lab_fit.rank(item, lab_fit.candidates(target.obj))

    assert [r["name"] for r in ranked] == ["Exact", "Near"]
    assert ranked[0]["why"] == "closest to the lab's profile"


@pytest.mark.django_db
def test_department_members_include_its_labs_members() -> None:
    target = _department()
    lab = _lab(target.obj, "Ocean ML", VEC_A)
    direct = User.objects.create_user("direct")
    DeptMembership.objects.create(user=direct, department=target.obj)
    via_lab = User.objects.create_user("vialab")
    LabMembership.objects.create(user=via_lab, lab=lab)
    User.objects.create_user("stranger")

    names = {u.username for u in announce._members(target)}

    assert names == {"direct", "vialab"}


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #
DEPT_TAGS = {
    name: f"t-{name}" for name, _emoji in discord_announcements.DEPT_FORUM_TAGS
}


def _dept_binding(target, guild="g1"):
    binding = bind(department=target.obj, guild_id=guild)
    for purpose in ("grants", "fellowships", "conferences"):
        add_route(
            binding,
            purpose,
            f"dept-forum-{guild}",
            forum_tag_ids=DEPT_TAGS,
            channel_name="dept-opportunities",
        )
    return binding


def _identity(user, snowflake):
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_ok=True,
    )


@pytest.mark.django_db
def test_the_department_post_says_why_and_carries_kind_and_reason_tags(fake) -> None:
    target = _department()
    _dept_binding(target)
    _lab(target.obj, "Ocean ML", VEC_A)
    item = _item(eligibility=LIMITED, activity_codes=["T32"])
    _slate(target, item)
    settings = target.settings
    settings.strong_match_tagging = True  # never applies to a department
    settings.save()

    _run(target, poster=discord_announcements.post)

    body = next(b for m, p, b in fake.calls if m == "POST" and p.endswith("/threads"))
    assert body["applied_tags"] == [
        "t-Grant",
        "t-Institutional selection",
        "t-Department-scale programme",
    ]
    fields = {f["name"]: f["value"] for f in body["message"]["embeds"][0]["fields"]}
    assert "Who should look" not in fields
    assert fields["Labs that could lead"].startswith("**Ocean ML**")
    assert "**Institutional selection**\n> " + LIMITED in fields["Why it's here"]
    assert body["message"].get("content", "") == ""
    assert body["message"]["allowed_mentions"] == {"parse": []}


@pytest.mark.django_db
def test_a_department_fellowship_shows_counts_and_dms_each_eligible_member(
    fake,
) -> None:
    target = _department()
    _dept_binding(target)
    lab = _lab(target.obj, "Ocean ML", VEC_A)
    citizen = User.objects.create_user("citizen")
    LabMembership.objects.create(user=citizen, lab=lab)
    _identity(citizen, "111")
    foreign = User.objects.create_user("foreign")
    DeptMembership.objects.create(user=foreign, department=target.obj)
    Profile.objects.filter(user=foreign).update(
        interests={"eligibility": {"citizenship": "international"}}
    )
    _identity(foreign, "222")
    item = _item(
        ContentItem.Type.FELLOWSHIP,
        eligibility="Each university may nominate two candidates.",
        facets={"citizenship": [US_FACET]},
        flags={"requires_us_citizenship": True},
    )
    _slate(target, item)

    _run(target, poster=discord_announcements.post)

    ann = Announcement.objects.get(content=item)
    eligibility = next(c for c in ann.checks if c["key"] == "eligibility")
    assert eligibility["label"] == "1 person may be eligible"
    thread = next(b for m, p, b in fake.calls if m == "POST" and p.endswith("/threads"))
    assert "citizen" not in str(thread) and "foreign" not in str(thread)
    dms = DiscordOutboxMessage.objects.filter(kind="announcement_eligible")
    assert [d.dedupe_key for d in dms] == [f"ann-eligible:{ann.id}:{citizen.id}"]

    # Re-posting (a manual announce, a resend) never DMs anyone twice.
    discord_announcements.post(ann)
    eligible = DiscordOutboxMessage.objects.filter(kind="announcement_eligible")
    assert eligible.count() == 1


@pytest.mark.django_db
def test_create_them_for_me_makes_one_department_forum_for_every_kind(fake) -> None:
    target = _department()
    binding = bind(department=target.obj, guild_id="g1")

    ok, message = announcement_setup.create_forums(binding)

    assert ok, message
    forums = [
        b for m, p, b in fake.calls if p == "/guilds/g1/channels" and b["type"] == 15
    ]
    assert [f["name"] for f in forums] == ["dept-opportunities"]
    assert {t["name"] for t in forums[0]["available_tags"]} >= {
        "Grant",
        "Institutional selection",
        "Department applicant",
        "Department-scale programme",
    }
    routes = announcement_setup.state(binding)["routes"]
    assert set(routes) == {"grants", "fellowships", "conferences"}
    assert len(set(routes.values())) == 1


@pytest.mark.django_db
def test_a_lab_and_its_department_in_one_server_stay_separate(fake) -> None:
    target = _department()
    dept_binding = _dept_binding(target, guild="g1")
    lab = _lab(target.obj, "Ocean ML", VEC_A)
    lab_settings = AnnouncementSettings.objects.create(
        target_lab=lab, enabled=True, seeded_at=timezone.now()
    )
    lab_target = announce.Target("lab", lab, lab_settings)
    lab_binding = bind(lab=lab, guild_id="g1")
    add_route(lab_binding, "grants", "lab-grants")
    item = _item(eligibility=LIMITED)
    _slate(target, item)
    RelevanceScore.objects.create(
        content=item,
        target_lab=lab,
        score=0.9,
        signals={
            "suggested": True,
            "cluster_slates": {
                "c1": {"label": "Ocean", "rank": 1, "of": 10, "is_new": True}
            },
        },
    )

    _run(target, poster=discord_announcements.post)
    _run(lab_target, poster=discord_announcements.post)

    channels = {
        p.binding_id: p.channel_id for p in AnnouncementPost.objects.all()
    }
    assert channels == {dept_binding.id: "dept-forum-g1", lab_binding.id: "lab-grants"}

    # Switching the department off leaves the lab on, and the reverse.
    announcement_setup.switch(dept_binding, on=False)
    lab_settings.refresh_from_db()
    assert lab_settings.enabled
    announcement_setup.switch(dept_binding, on=True)
    announcement_setup.switch(lab_binding, on=False)
    target.settings.refresh_from_db()
    assert target.settings.enabled


# --------------------------------------------------------------------------- #
# The department's Opportunities page
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_department_page_lists_only_department_level_items_with_reasons(
    fake,
) -> None:
    from rest_framework.test import APIClient

    target = _department()
    _dept_binding(target)
    _lab(target.obj, "Ocean ML", VEC_A)
    lab_level = _item(title="Lab call")
    limited = _item(title="Limited call", eligibility=LIMITED)
    _slate(target, lab_level, 1)
    _slate(target, limited, 2)
    _run(target, poster=discord_announcements.post)
    member = User.objects.create_user("member")
    DeptMembership.objects.create(user=member, department=target.obj)
    client = APIClient()
    client.force_authenticate(member)

    resp = client.get(
        "/api/announcements/department-opportunities/",
        {"department": str(target.obj.pk)},
    )

    assert resp.status_code == 200
    (row,) = resp.json()["items"]
    assert row["title"] == "Limited call"
    assert [r["key"] for r in row["reasons"]] == ["institutional_selection"]
    assert row["reasons"][0]["evidence"] == LIMITED
    assert row["labs"] == [{"name": "Ocean ML", "why": "closest to the lab's profile"}]
    assert row["announced"] is True
    assert row["discord"][0]["channel_name"] == "dept-opportunities"
    team = next(c for c in row["checks"] if c["key"] == "team")
    assert team["label"] == "Ocean ML could lead"

    # A closed department-level call on the slate is listed as held back, and a
    # call a manager announced off the slate is listed too.
    # The shape a real record had (Apple PhD Fellowship): a past "anticipated"
    # round keeps it live, but its last deadline has passed.
    closed = _item(
        ContentItem.Type.FELLOWSHIP,
        title="Closed call",
        eligibility=LIMITED,
        deadline={
            "type": "anticipated",
            "date": "2020-08",
            "previous_date": "2019-08-25",
        },
        deadline_date="",
        prune_after="",
    )
    _slate(target, closed, 3)
    off_slate = _item(title="Off-slate call", eligibility=LIMITED)
    Announcement.objects.create(
        target_department=target.obj,
        content=off_slate,
        category=off_slate.type,
        state=Announcement.State.POSTED,
        snapshot={"title": "Off-slate call"},
    )
    rows = client.get(
        "/api/announcements/department-opportunities/",
        {"department": str(target.obj.pk)},
    ).json()["items"]
    by_title = {r["title"]: r for r in rows}
    assert set(by_title) == {"Limited call", "Off-slate call", "Closed call"}
    assert by_title["Closed call"]["held"] == "The last deadline has passed"
    assert rows[-1]["title"] == "Closed call"
    assert by_title["Limited call"]["held"] == ""

    listed = client.get("/api/announcements/", {"department": str(target.obj.pk)})
    limited_row = next(
        r for r in listed.json()["announced"] if r["title"] == "Limited call"
    )
    assert limited_row["dept_reasons"][0]["evidence"] == LIMITED

    outsider = APIClient()
    outsider.force_authenticate(User.objects.create_user("outsider"))
    denied = outsider.get(
        "/api/announcements/department-opportunities",
        {"department": str(target.obj.pk)},
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_a_test_post_goes_once_to_the_department_forum(fake) -> None:
    from rest_framework.test import APIClient

    target = _department()
    _dept_binding(target)
    client = APIClient()
    client.force_authenticate(target.obj.owner)

    resp = client.post(
        f"/api/announcements/test?department={target.obj.pk}", format="json"
    )

    assert resp.status_code == 200
    (result,) = resp.json()["results"]
    assert result["channel_name"] == "dept-opportunities" and result["ok"]
    (body,) = [b for m, p, b in fake.calls if m == "POST" and p.endswith("/threads")]
    assert "grants, fellowships and conferences" in body["message"]["embeds"][0][
        "description"
    ]


@pytest.mark.django_db
def test_a_manager_can_announce_only_department_level_calls_to_the_department(
    fake, monkeypatch
) -> None:
    from apps.content import announcement_links

    monkeypatch.setattr(
        "apps.integrations.services.gate._department_entitled",
        lambda department, feature: (True, ""),
    )
    target = _department()
    binding = _dept_binding(target)
    _identity(target.obj.owner, "900")
    lab_level = _item(title="Lab call")
    limited = _item(title="Limited call", eligibility=LIMITED)

    options = announcement_links.announce_options(
        target.obj.owner, "g1", [lab_level, limited]
    )
    assert set(options) == {str(limited.id)}

    status, payload = announcement_links.manual_announce(
        "900", "g1", binding.id, str(lab_level.id)
    )
    assert status == "not_department_level", payload
    assert not Announcement.objects.filter(content=lab_level).exists()

    status, payload = announcement_links.manual_announce(
        "900", "g1", binding.id, str(limited.id)
    )
    assert status in ("ok", "queued"), payload
    ann = Announcement.objects.get(content=limited)
    assert ann.origin == Announcement.Origin.MANUAL
    assert ann.alignment["dept_reasons"][0]["evidence"] == LIMITED


@pytest.mark.django_db
def test_a_lab_without_a_stored_vector_is_embedded_from_its_profile_text() -> None:
    """Nothing writes a stored lab vector, so lab-fit embeds the lab's canonical
    text with the item model; a lab with no profile text is left out."""
    from tools.retrieval import embeddings

    target = _department()
    lab = Lab.objects.create(name="Ocean ML", slug="ocean-ml", department=target.obj)
    lab.profile.statement = "Ocean forecasting with machine learning."
    lab.profile.save()
    Lab.objects.create(name="Empty", slug="empty", department=target.obj)
    seen = []

    def fake_embed(texts):
        seen.extend(texts)
        return [VEC_A for _ in texts]

    embeddings.set_embedder(fake_embed)
    try:
        labs = lab_fit.candidates(target.obj)
    finally:
        embeddings.reset_embedder()

    assert [c.name for c in labs] == ["Ocean ML"]
    assert len(seen) == 1 and "Ocean forecasting" in seen[0]
    assert [r["name"] for r in lab_fit.rank(_item(), labs)] == ["Ocean ML"]


@pytest.mark.django_db
def test_department_closing_soon_lists_name_their_kind_in_the_shared_forum(
    fake,
) -> None:
    from apps.content import announce_facts

    target = _department()
    _dept_binding(target)
    soon = (TODAY + timedelta(days=5)).isoformat()
    lab_level = _item(title="Lab call", deadline_date=soon, prune_after=soon)
    limited = _item(
        title="Limited call", eligibility=LIMITED, deadline_date=soon, prune_after=soon
    )
    _slate(target, lab_level, 1)
    _slate(target, limited, 2)

    items = announce.list_items(target, TODAY)
    assert [i.id for i in items] == [limited.id]  # the list is department-level too
    rows = announce_facts.closing_soon(items, TODAY)
    discord_announcements._closing_soon(target, ContentItem.Type.GRANT, rows, TODAY)
    discord_announcements.flush()

    (body,) = [b for m, p, b in fake.calls if m == "POST" and p.endswith("/threads")]
    assert body["name"].startswith("⏳ Closing soon · Grants: next 14 days")
    assert body["applied_tags"] == ["t-Daily list"]
