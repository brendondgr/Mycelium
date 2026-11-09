"""The announcement engine, without Discord (plan Phase 3).

Selection is entrant-only and never repeats; activation posts exactly the seed
(kinds interleaved) and passes over the rest for good; ``-1`` means unlimited; a
moved date is a change and an identical re-scrape is not; the verifier rejects
what breaks its rules and the template takes over.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from apps.accounts.models import Lab, LabMembership
from django.contrib.auth.models import User
from django.utils import timezone

from tools.delivery import announce, announce_facts, announce_updates
from tools.delivery import announce_editor as editor
from tools.delivery.models import Announcement, AnnouncementSettings
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = date(2026, 11, 5)
FAR = "2099-01-15"
_n = iter(range(1, 10_000))


def _lab(slug="reef", *, seeded=True, **settings) -> announce.Target:
    lab = Lab.objects.create(name=f"Lab {slug}", slug=slug)
    row = AnnouncementSettings.objects.create(
        target_lab=lab,
        enabled=True,
        seeded_at=timezone.now() if seeded else None,
        **settings,
    )
    return announce.Target("lab", lab, row)


def _item(kind=ContentItem.Type.GRANT, *, deadline=FAR, title=None, **meta):
    n = next(_n)
    base = {"title": title or f"{kind} {n}", "status": "open", "funder": "NSF"}
    if kind == ContentItem.Type.FELLOWSHIP:
        base |= {
            "deadline": {"type": "true", "date": deadline},
            "deadline_date": deadline,
            "prune_after": deadline,
        }
    elif kind == ContentItem.Type.CONFERENCE:
        base = {
            "title": base["title"],
            "prune_after": deadline,
            "deadlines_structured": [
                {
                    "kind": "submission",
                    "instant": f"{deadline}T11:59:59Z",
                    "round_label": "Papers",
                    "is_estimated": False,
                }
            ]
            if deadline
            else [],
        }
    else:
        base |= {"deadline_date": deadline, "prune_after": deadline}
    base.update(meta)
    return ContentItem.objects.create(
        type=kind, source="open-collector", external_id=f"x{n}", metadata=base
    )


def _slate(target, item, rank, *, cluster="c1", label="Ocean forecasting", **signals):
    return RelevanceScore.objects.create(
        content=item,
        target_lab=target.obj,
        score=1 / rank,
        signals={
            "suggested": True,
            "cluster_slates": {
                cluster: {
                    "label": label,
                    "rank": rank,
                    "of": 10,
                    "entered_on": TODAY.isoformat(),
                    "is_new": True,
                }
            },
            **signals,
        },
    )


def _run(target, today=TODAY, complete=None):
    posted = []
    target.settings.refresh_from_db()
    outcome = announce.run_target(
        target, today, dry_run=False, complete=complete, poster=posted.append
    )
    return outcome, posted


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_only_slate_members_are_announced_and_never_twice() -> None:
    target = _lab()
    a, b, outside = _item(), _item(), _item()
    _slate(target, a, 1)
    _slate(target, b, 2)
    RelevanceScore.objects.create(
        content=outside, target_lab=target.obj, score=0.9, signals={"suggested": True}
    )

    _outcome, posted = _run(target)
    assert {p.content_id for p in posted} == {a.id, b.id}

    _outcome, again = _run(target)
    assert again == []
    assert Announcement.objects.filter(target_lab=target.obj).count() == 2


@pytest.mark.django_db
def test_a_new_entrant_the_next_night_is_the_only_post() -> None:
    target = _lab()
    _slate(target, _item(), 1)
    _run(target)
    late = _item()
    _slate(target, late, 2)

    _outcome, posted = _run(target)

    assert [p.content_id for p in posted] == [late.id]


@pytest.mark.django_db
def test_activation_posts_exactly_six_interleaved_and_passes_over_the_rest() -> None:
    target = _lab(seeded=False)
    grants = [_item(ContentItem.Type.GRANT) for _ in range(6)]
    fellows = [_item(ContentItem.Type.FELLOWSHIP) for _ in range(3)]
    confs = [_item(ContentItem.Type.CONFERENCE) for _ in range(2)]
    rank = 0
    for item in [*grants, *fellows, *confs]:
        rank += 1
        _slate(target, item, rank)

    outcome, posted = _run(target)

    assert outcome.seeding and len(posted) == 6
    kinds = [p.category for p in posted]
    assert kinds[:3] == ["grant", "fellowship", "conference"]  # interleaved by kind
    assert kinds.count("grant") == 2
    assert {p.label for p in posted} == {Announcement.Label.ALREADY_OPEN}
    seen = Announcement.objects.filter(state=Announcement.State.SEEDED_SEEN)
    assert seen.count() == 5

    # Passed over at activation means never announced later, even as the slate moves.
    _outcome, later = _run(target)
    assert later == []
    target.settings.refresh_from_db()
    assert target.settings.seeded_at is not None


@pytest.mark.django_db
def test_the_seed_skips_items_that_would_be_held_back() -> None:
    target = _lab(seeded=False, activation_seed=2)
    closed = _item(status="closed")
    open_a, open_b = _item(), _item()
    _slate(target, closed, 1)
    _slate(target, open_a, 2)
    _slate(target, open_b, 3)

    _outcome, posted = _run(target)

    assert {p.content_id for p in posted} == {open_a.id, open_b.id}


@pytest.mark.django_db
def test_minus_one_is_unlimited_and_a_cap_holds_the_rest_for_tomorrow() -> None:
    unlimited = _lab("u")
    for rank in range(1, 11):
        _slate(unlimited, _item(), rank)
    _outcome, posted = _run(unlimited)
    assert len(posted) == 10

    capped = _lab("c", daily_cap=3)
    items = [_item() for _ in range(7)]
    for rank, item in enumerate(items, start=1):
        _slate(capped, item, rank)
    outcome, first = _run(capped)
    assert [p.content_id for p in first] == [i.id for i in items[:3]]
    assert outcome.waiting == 4
    _outcome, second = _run(capped)
    assert [p.content_id for p in second] == [i.id for i in items[3:6]]


@pytest.mark.django_db
def test_held_back_items_are_recorded_with_their_reason() -> None:
    target = _lab()
    soon = _item(deadline="2026-11-10")  # inside the 14-day default buffer
    _slate(target, soon, 1)

    outcome, posted = _run(target)

    assert posted == []
    held = Announcement.objects.get(content=soon)
    assert held.state == Announcement.State.SKIPPED
    assert "inside your 14-day buffer" in held.skip_reason
    assert outcome.held[0].write_up.source == "template"


@pytest.mark.django_db
def test_a_conference_without_dates_waits_until_they_are_published() -> None:
    target = _lab()
    conf = _item(ContentItem.Type.CONFERENCE, deadline="")
    conf.metadata["prune_after"] = FAR  # still live, just undated
    conf.save()
    _slate(target, conf, 1)

    _outcome, posted = _run(target)
    assert posted == []
    assert not Announcement.objects.filter(content=conf).exists()

    conf.metadata["deadlines_structured"] = [
        {"kind": "abstract", "instant": f"{FAR}T00:00:00Z", "is_estimated": False}
    ]
    conf.save()
    _outcome, posted = _run(target)
    assert [p.content_id for p in posted] == [conf.id]


@pytest.mark.django_db
def test_dry_run_writes_nothing() -> None:
    target = _lab(seeded=False)
    _slate(target, _item(), 1)

    outcome = announce.run_target(target, TODAY, dry_run=True, complete=None)

    assert len(outcome.posted) == 1
    assert not Announcement.objects.exists()
    target.settings.refresh_from_db()
    assert target.settings.seeded_at is None


@pytest.mark.django_db
def test_labels_follow_how_new_the_call_is() -> None:
    target = _lab()
    fresh = _item(published_on="2026-11-01")
    older = _item(published_on="2026-01-01")
    _slate(target, fresh, 1)
    _slate(target, older, 2)

    _outcome, posted = _run(target)

    labels = {p.content_id: p.label for p in posted}
    assert labels[fresh.id] == Announcement.Label.NEW_CALL
    assert labels[older.id] == Announcement.Label.NEWLY_RELEVANT


# --------------------------------------------------------------------------- #
# The editor and its verifier
# --------------------------------------------------------------------------- #
def _packet() -> editor.Packet:
    return editor.Packet(
        item_id="i1",
        kind="grant",
        title="Ocean Tech",
        funder="NSF",
        summary="",
        target_name="Reef Lab",
        target_kind="lab",
        label="New call",
        theme="Ocean forecasting",
        people=[{"id": "p1", "name": "Ana R.", "why": "data assimilation"}],
        checks=[{"key": "open", "status": "ok", "label": "Open", "field": "status"}],
    )


def _reply(**over) -> str:
    body = {
        "announce": True,
        "headline": "Ocean technology money for the forecasting pipeline",
        "why_it_matters": "It funds instruments your forecasting work already needs.",
        "who_should_look": [{"id": "p1", "why": "runs the assimilation code"}],
        "next_step": "Ask the programme officer whether sensor work counts.",
        "skip_reason": "",
    }
    body.update(over)
    return json.dumps(body)


def test_a_valid_reply_is_used() -> None:
    write_up, note = editor.edit(_packet(), complete=lambda _p: _reply())
    assert note == "" and write_up.source == "editor"
    assert write_up.who_should_look[0]["name"] == "Ana R."


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"why_it_matters": "Closes on the 15th, worth it."}, "contains a digit"),
        ({"headline": "Up to $5M for ocean work"}, "contains a digit"),
        ({"who_should_look": [{"id": "p9", "why": "x"}]}, "not in the packet"),
        ({"next_step": ""}, "next_step is missing"),
        ({"announce": "yes"}, "true or false"),
    ],
)
def test_the_verifier_rejects_and_the_template_takes_over(override, reason) -> None:
    write_up, note = editor.edit(_packet(), complete=lambda _p: _reply(**override))
    assert reason in note
    assert write_up.source == "template"
    assert write_up.headline == "Ocean Tech"


def test_garbage_and_model_errors_fall_back_too() -> None:
    _w, note = editor.edit(_packet(), complete=lambda _p: "not json at all")
    assert note.startswith("rejected")

    def boom(_p):
        raise TimeoutError

    _w, note = editor.edit(_packet(), complete=boom)
    assert note == "model unavailable: TimeoutError"


def test_an_editor_skip_needs_a_reason_without_digits() -> None:
    write_up, note = editor.edit(
        _packet(),
        complete=lambda _p: _reply(
            announce=False, skip_reason="Too far from the theme"
        ),
    )
    assert not write_up.announce and note == ""
    _w, note = editor.edit(
        _packet(), complete=lambda _p: _reply(announce=False, skip_reason="")
    )
    assert "needs a reason" in note


@pytest.mark.django_db
def test_the_people_offered_come_from_member_fit_only() -> None:
    target = _lab()
    ana = User.objects.create_user("ana", first_name="Ana", last_name="R")
    LabMembership.objects.create(user=ana, lab=target.obj)
    item = _item()
    _slate(
        target,
        item,
        1,
        member_fit=[
            {"username": "ana", "reason": "assimilation", "fit": 0.7},
            {"username": "left-the-lab", "reason": "x", "fit": 0.9},
        ],
    )
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return _reply()

    _outcome, posted = _run(target, complete=capture)

    assert "left-the-lab" not in seen["prompt"]
    assert posted[0].write_up["who_should_look"][0]["name"] == "Ana R"


# --------------------------------------------------------------------------- #
# Changes and closing
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_moved_date_is_a_change_and_an_identical_rescrape_is_not() -> None:
    target = _lab()
    item = _item(deadline="2027-01-14")
    _slate(target, item, 1)
    _run(target)

    assert announce_updates.plan(target, TODAY).changed == []

    item.metadata = {**item.metadata}  # a re-scrape returning the same record
    item.save()
    assert announce_updates.plan(target, TODAY).changed == []

    item.metadata = {
        **item.metadata,
        "deadline_date": "2027-02-11",
        "prune_after": "2027-02-11",
    }
    item.save()
    changed = announce_updates.plan(target, TODAY).changed
    assert len(changed) == 1
    change = changed[0].changes[0]
    assert change.field == "deadline"
    assert change.line() == "Deadline: ~~Thu, Jan 14, 2027~~ → **Thu, Feb 11, 2027**"

    announce_updates.record_update(changed[0])
    assert announce_updates.plan(target, TODAY).changed == []


@pytest.mark.django_db
def test_time_passing_alone_is_not_a_change() -> None:
    item = _item(ContentItem.Type.CONFERENCE, deadline="2026-12-01")
    item.metadata["deadlines_structured"].append(
        {"kind": "submission", "instant": "2027-02-01T00:00:00Z", "is_estimated": False}
    )
    item.save()
    before = announce_facts.facts_for(item, TODAY)
    after = announce_facts.facts_for(item, date(2026, 12, 10))
    assert announce_facts.changes(before, after) == []


@pytest.mark.django_db
def test_finished_calls_are_planned_for_closing() -> None:
    target = _lab()
    item = _item(deadline="2026-12-01")
    _slate(target, item, 1)
    _run(target)

    plan = announce_updates.plan(target, date(2026, 12, 2))

    assert [a.content_id for a in plan.to_close] == [item.id]


@pytest.mark.django_db
def test_closing_soon_lists_the_next_fourteen_days_per_kind() -> None:
    target = _lab()
    near = _item(deadline="2026-11-12", title="Near grant")
    later = _item(deadline="2026-12-30", title="Later grant")
    fellow = _item(ContentItem.Type.FELLOWSHIP, deadline="2026-11-19", title="Fellow")
    for rank, item in enumerate([near, later, fellow], start=1):
        _slate(target, item, rank)

    plan = announce_updates.plan(target, TODAY)

    assert [r.title for r in plan.closing_soon["grant"]] == ["Near grant"]
    assert [r.title for r in plan.closing_soon["fellowship"]] == ["Fellow"]
    assert plan.closing_soon["grant"][0].days == 7


@pytest.mark.django_db
def test_a_legacy_ranked_kind_counts_only_within_its_slate_depth() -> None:
    target = _lab()
    fellows = [_item(ContentItem.Type.FELLOWSHIP) for _ in range(7)]
    for rank, item in enumerate(fellows, start=1):
        RelevanceScore.objects.create(
            content=item,
            target_lab=target.obj,
            score=1 / rank,
            signals={"suggested": True, "top_rank": rank},
        )

    _outcome, posted = _run(target)

    assert [p.content_id for p in posted] == [f.id for f in fellows[:5]]


def test_member_fit_reasons_never_carry_a_percentage() -> None:
    assert (
        announce._reason(
            {
                "reason": "Closest match to Ana's profile (49% profile match).",
                "source": "similarity",
            }
        )
        == "Closest match to their research profile"
    )
    assert (
        announce._reason(
            {
                "reason": "Builds the assimilation code (61% match) the call asks for",
                "source": "llm",
            }
        )
        == "Builds the assimilation code the call asks for"
    )


@pytest.mark.django_db
def test_the_implicit_grouping_is_not_called_a_theme() -> None:
    target = _lab()
    _slate(target, _item(), 1, cluster="c-all", label="All interests")

    _outcome, posted = _run(target)

    assert "All interests" not in posted[0].write_up["why_it_matters"]


@pytest.mark.django_db
def test_the_seed_skips_fellowships_nobody_is_eligible_for() -> None:
    from apps.accounts.models import Profile

    target = _lab(seeded=False, activation_seed=2)
    member = User.objects.create_user("intl")
    LabMembership.objects.create(user=member, lab=target.obj)
    Profile.objects.filter(user=member).update(
        interests={"eligibility": {"citizenship": "international"}}
    )
    us_only = _item(
        ContentItem.Type.FELLOWSHIP, flags={"requires_us_citizenship": True}
    )
    grant_a, grant_b = _item(), _item()
    _slate(target, us_only, 1)
    _slate(target, grant_a, 2)
    _slate(target, grant_b, 3)

    _outcome, posted = _run(target)

    assert {p.content_id for p in posted} == {grant_a.id, grant_b.id}


@pytest.mark.django_db
def test_a_saved_item_that_was_pruned_does_not_break_the_list() -> None:
    from tools.delivery.models import SavedOpportunity

    target = _lab()
    item = _item(deadline="2026-11-12", title="Near grant")
    _slate(target, item, 1)
    gone = _item(title="Pruned")
    SavedOpportunity.objects.create(
        target_lab=target.obj,
        content=gone,
        area="grant",
        title="Pruned",
        user=User.objects.create_user("saver"),
    )
    gone.delete()

    plan = announce_updates.plan(target, TODAY)

    assert [r.title for r in plan.closing_soon["grant"]] == ["Near grant"]


def test_conference_titles_use_the_name_and_a_new_acronym_only() -> None:
    from tools.delivery.announce_facts import item_title

    def conf(**meta):
        return ContentItem(type=ContentItem.Type.CONFERENCE, metadata=meta)

    trust = conf(name="Trustworthy Models (TrustFMI)", acronym="TrustFMI2026")
    assert item_title(trust) == "Trustworthy Models (TrustFMI)"
    assert (
        item_title(conf(name="Architectural Support for PL", acronym="ASPLOS"))
        == "ASPLOS: Architectural Support for PL"
    )
    assert item_title(conf(acronym="IGARSS")) == "IGARSS"


# --------------------------------------------------------------------------- #
# Who should look: project teams first, in plain words
# --------------------------------------------------------------------------- #
def _team_packet() -> editor.Packet:
    packet = _packet()
    packet.people = [
        {
            "id": "p1",
            "name": "Ana R.",
            "why": "data assimilation",
            "projects": ["Reef Twin"],
            "interests": "ocean forecasting",
        },
        {
            "id": "p2",
            "name": "Ben K.",
            "why": "sensor arrays",
            "projects": [],
            "interests": "acoustic sensing",
        },
    ]
    packet.project_teams = [
        {
            "id": "j1",
            "name": "Reef Twin",
            "focus": "A digital twin of the reef for forecasting bleaching.",
            "members": ["Ana R.", "Cy L."],
        },
    ]
    return packet


def test_the_prompt_offers_project_teams_and_peoples_interests() -> None:
    prompt = _team_packet().prompt()
    assert "j1: Reef Twin — focus: A digital twin" in prompt
    assert "Team: Ana R., Cy L." in prompt
    assert "p2: Ben K. — interests: acoustic sensing" in prompt
    assert "Never write \"X's research" in editor.SYSTEM_PROMPT


def test_a_project_entry_names_its_team() -> None:
    reply = _reply(
        who_should_look=[
            {
                "id": "j1",
                "why": "It would pay for the bleaching forecasts' next stage.",
            },
            {"id": "p2", "why": "Its sensor strand fits the arrays Ben builds."},
            {"id": "j1", "why": "said twice"},
        ]
    )
    write_up, note = editor.edit(_team_packet(), complete=lambda _p: reply)

    assert note == ""
    project, person = write_up.who_should_look
    assert project == {
        "id": "j1",
        "kind": "project",
        "name": "Reef Twin",
        "members": ["Ana R.", "Cy L."],
        "why": "It would pay for the bleaching forecasts' next stage.",
    }
    assert person["name"] == "Ben K." and "kind" not in person
    assert editor.looker_label(project) == "**Reef Twin** project (Ana R., Cy L.)"
    assert editor.looker_label(person, bold=False) == "Ben K."


def test_an_unknown_project_id_is_rejected() -> None:
    reply = _reply(who_should_look=[{"id": "j9", "why": "x"}])
    _w, note = editor.edit(_team_packet(), complete=lambda _p: reply)
    assert "not in the packet" in note


def test_the_fallback_lists_projects_first_and_skips_their_members() -> None:
    write_up = editor.template(_team_packet())
    names = [p["name"] for p in write_up.who_should_look]
    assert names == ["Reef Twin", "Ben K."]  # Ana is reached through Reef Twin
    assert (
        write_up.who_should_look[0]["why"] == "Mylo matched it to this project's work."
    )
    assert write_up.why_it_matters.startswith("Fits your **Ocean forecasting** theme")


def test_who_should_look_is_capped() -> None:
    packet = _team_packet()
    packet.people += [{"id": f"p{n}", "name": f"P{n}", "why": "x"} for n in range(3, 8)]
    reply = _reply(
        who_should_look=[{"id": f"p{n}", "why": "fits"} for n in range(2, 8)]
    )
    write_up, _ = editor.edit(packet, complete=lambda _p: reply)
    assert len(write_up.who_should_look) == editor.MAX_LOOKERS


@pytest.mark.django_db
def test_only_shared_live_projects_reach_the_editor() -> None:
    from apps.research.models import Project, ProjectMember

    target = _lab()
    ana = User.objects.create_user("ana", first_name="Ana", last_name="R")
    LabMembership.objects.create(user=ana, lab=target.obj)
    item = _item()
    _slate(
        target,
        item,
        1,
        member_fit=[{"username": "ana", "reason": "assimilation", "fit": 0.7}],
    )
    for name, shared, archived in [
        ("Reef Twin", True, False),
        ("Secret Grant Bid", False, False),
        ("Old Survey", True, True),
    ]:
        project = Project.objects.create(
            scope_lab=target.obj,
            name=name,
            share_in_lab_reports=shared,
            is_archived=archived,
            goals={"description": f"{name} focus."},
        )
        ProjectMember.objects.create(project=project, user=ana)
        RelevanceScore.objects.create(
            content=item, target_project=project, score=0.8, signals={"suggested": True}
        )
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return _reply(who_should_look=[{"id": "j1", "why": "It serves the twin."}])

    _outcome, posted = _run(target, complete=capture)

    assert "Reef Twin focus." in seen["prompt"]
    assert "Secret Grant Bid" not in seen["prompt"]
    assert "Old Survey" not in seen["prompt"]
    assert "on projects: Reef Twin" in seen["prompt"]
    alignment = posted[0].alignment
    assert alignment["projects"] == ["Reef Twin"]
    entry = posted[0].write_up["who_should_look"][0]
    assert (entry["kind"], entry["members"]) == ("project", ["Ana R"])


def test_a_headline_may_repeat_digits_from_the_title_but_nothing_else() -> None:
    packet = _team_packet()
    packet.title = "AACL-IJCNLP 2026 Workshop NORA"
    ok, note = editor.edit(
        packet, complete=lambda _p: _reply(headline="NORA at AACL-IJCNLP 2026 fits")
    )
    assert note == "" and ok.headline == "NORA at AACL-IJCNLP 2026 fits"

    for over in (
        {"headline": "NORA closes on the 15th"},
        {"why_it_matters": "The 2026 workshop suits the twin."},
    ):
        _w, note = editor.edit(packet, complete=lambda _p, o=over: _reply(**o))
        assert "contains a digit" in note


def test_a_person_on_a_named_project_is_not_listed_again() -> None:
    reply = _reply(
        who_should_look=[
            {"id": "j1", "why": "A venue for the twin's forecasts."},
            {"id": "p1", "why": "Ana's interests fit too."},  # Ana is on Reef Twin
            {"id": "p2", "why": "Its sensor strand fits Ben's arrays."},
        ]
    )
    write_up, _ = editor.edit(_team_packet(), complete=lambda _p: reply)
    assert [p["name"] for p in write_up.who_should_look] == ["Reef Twin", "Ben K."]
