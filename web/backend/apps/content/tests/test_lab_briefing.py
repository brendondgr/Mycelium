"""The lab "Mylo Report": a lab-scoped daily briefing over its aggregate matches."""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.content.briefing import generate_briefing_for_lab
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.content.tests.entitle import entitle_lab

RUN = "2026-07-11T06:00:00"
# The report shows only what first surfaced on the run date and cleared its
# relevance floor, so a lab row that is meant to reach the prose carries both.
TODAY = timezone.now().date().isoformat()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    """A lab on an active plan — Mylo's prose is a paid layer (plan §18)."""
    created = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    entitle_lab(created)
    return created


@pytest.fixture
def member(db, lab: Lab) -> User:
    user = User.objects.create_user(username="jordan", password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    return user


def _content(ctype: str, title: str, **metadata) -> ContentItem:
    metadata.setdefault("title", title)
    return ContentItem.objects.create(
        type=ctype, source="test", external_id=title, metadata=metadata
    )


def _lab_score(lab: Lab, content: ContentItem, *, rank=1) -> RelevanceScore:
    return RelevanceScore.objects.create(
        content=content,
        target_lab=lab,
        score=0.8,
        signals={
            "suggested": True,
            "run_at": RUN,
            "rank": rank,
            "headline": f"Headline {content.metadata['title']}",
            "reason": f"Why {content.metadata['title']} fits the lab.",
            "verdict": "read",
            "first_seen": TODAY,
            "embedding_match": 0.8,
            "top_rank": rank,
            "entered_top_on": TODAY,
            "is_new_top": True,
            # A lab declares no clusters in these fixtures, so its rows sit in the
            # single implicit grouping every unclustered profile falls into.
            "cluster_slates": {
                "c-all": {
                    "label": "",
                    "rank": rank,
                    "entered_on": TODAY,
                    "is_new": True,
                }
            },
        },
    )


def _llm(text: str):
    return lambda system, user: text


@pytest.mark.django_db
def test_lab_briefing_is_keyed_to_the_lab_and_covers_its_matches(lab: Lab) -> None:
    _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)
    _lab_score(lab, _content(ContentItem.Type.GRANT, "Lab Grant"), rank=1)

    briefing = generate_briefing_for_lab(lab, complete=_llm("lab body"))

    assert briefing.lab_id == lab.id
    assert briefing.user_id is None
    assert briefing.counts == {
        "papers": 1,
        "grants": 1,
        "conferences": 0,
        "fellowships": 0,
    }
    assert "### Papers" in briefing.body
    assert "lab body" in briefing.body
    assert DailyBriefing.objects.filter(lab=lab).count() == 1


@pytest.mark.django_db
def test_lab_briefing_covers_the_labs_own_fellowships(lab: Lab) -> None:
    """A lab is scored for fellowships now, so its report covers them too."""
    lab.watch.categories = ["papers", "fellowships"]
    lab.watch.save()
    _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)
    _lab_score(lab, _content(ContentItem.Type.FELLOWSHIP, "Lab Fellowship"), rank=1)

    briefing = generate_briefing_for_lab(lab, complete=_llm("body"))

    assert set(briefing.categories) == {"papers", "fellowships"}
    assert briefing.counts["fellowships"] == 1
    assert "### Fellowships" in briefing.body


@pytest.mark.django_db
def test_lab_briefing_watch_config_still_narrows_it(lab: Lab) -> None:
    """Fellowships being available doesn't mean an unwatching lab gets them."""
    lab.watch.categories = ["papers"]
    lab.watch.save()
    _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)
    _lab_score(lab, _content(ContentItem.Type.FELLOWSHIP, "Lab Fellowship"), rank=1)

    briefing = generate_briefing_for_lab(lab, complete=_llm("body"))

    assert set(briefing.categories) == {"papers"}
    assert "### Fellowships" not in briefing.body


@pytest.mark.django_db
def test_lab_briefing_replaces_in_place(lab: Lab) -> None:
    _lab_score(lab, _content(ContentItem.Type.PAPER, "P"), rank=1)
    generate_briefing_for_lab(lab, complete=_llm("first"))
    generate_briefing_for_lab(lab, complete=_llm("second"))

    assert DailyBriefing.objects.filter(lab=lab).count() == 1
    assert "second" in DailyBriefing.objects.get(lab=lab).body


@pytest.mark.django_db
def test_lab_briefing_api_member_reads(
    client: APIClient, lab: Lab, member: User
) -> None:
    _lab_score(lab, _content(ContentItem.Type.PAPER, "Mine"), rank=1)
    generate_briefing_for_lab(lab, complete=_llm("hello lab"))

    client.force_authenticate(member)
    resp = client.get(f"/api/labs/{lab.slug}/daily-briefing/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] is not None
    assert resp.data["counts"] == {
        "papers": 1,
        "grants": 0,
        "conferences": 0,
        "fellowships": 0,
    }
    assert "hello lab" in resp.data["briefing"]["body"]


@pytest.mark.django_db
def test_lab_briefing_api_empty_envelope(
    client: APIClient, lab: Lab, member: User
) -> None:
    client.force_authenticate(member)
    resp = client.get(f"/api/labs/{lab.slug}/daily-briefing/")
    assert resp.status_code == 200
    assert resp.data["briefing"] is None
    assert resp.data["generated_at"] is None


@pytest.mark.django_db
def test_lab_briefing_api_non_member_forbidden(client: APIClient, lab: Lab) -> None:
    outsider = User.objects.create_user(username="out", password="p")
    client.force_authenticate(outsider)
    assert client.get(f"/api/labs/{lab.slug}/daily-briefing/").status_code == 403


@pytest.mark.django_db
def test_the_report_never_says_who_an_item_is_best_suited_to(
    lab: Lab, member: User
) -> None:
    """"Best suited to" is gone from the report — prompt, prose, and fallback.

    The member-fit layer is still computed and still on the row; what it stopped
    doing is interrupting a ranked list with a sentence about staffing. It broke the
    one shape every other part of the report shares, and it is the feeds, not the
    daily read, where "who should pick this up" belongs.
    """
    member.first_name = "Jordan"
    member.last_name = "Reyes"
    member.save(update_fields=["first_name", "last_name"])
    score = _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)
    score.signals["member_fit"] = [
        {"username": "jordan", "fit": 88, "reason": "Squarely theirs.", "source": "llm"}
    ]
    score.save(update_fields=["signals"])

    # Every agent call, since the summary editor runs after the specialists.
    calls: list[tuple[str, str]] = []

    def capture(system: str, user: str) -> str:
        calls.append((system, user))
        return "body"

    generate_briefing_for_lab(lab, complete=capture)

    assert not any("Best suited to" in user for _system, user in calls)
    assert not any("ONLY the names given" in system for system, _user in calls)

    # And the deterministic body, which is what a lab gets when the model is down.
    briefing = generate_briefing_for_lab(lab, complete=lambda system, user: None)
    assert "Best suited to" not in briefing.body
    assert "Jordan Reyes" not in briefing.body


@pytest.mark.django_db
def test_the_labs_own_section_is_named_after_the_lab(lab: Lab, member: User) -> None:
    """A lab's aggregate part is the lab, so it carries the lab's name.

    It used to be headed "Personal" — on a document addressed to a whole lab, that
    heading named nobody, and the contents page built from it offered the reader a
    section that did not exist.
    """
    _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)

    briefing = generate_briefing_for_lab(lab, complete=lambda system, user: None)

    assert "## Reyes Lab" in briefing.body
    assert "## Personal" not in briefing.body
    assert briefing.project_summary[0]["label"] == "Reyes Lab"


@pytest.mark.django_db
def test_a_departed_members_stale_signal_never_reaches_the_prose(
    lab: Lab, member: User
) -> None:
    score = _lab_score(lab, _content(ContentItem.Type.PAPER, "Lab Paper"), rank=1)
    score.signals["member_fit"] = [
        {"username": "ghost", "fit": 90, "reason": "r", "source": "llm"}
    ]
    score.save(update_fields=["signals"])

    briefing = generate_briefing_for_lab(lab, complete=lambda system, user: None)

    assert "ghost" not in briefing.body
    assert "Best suited to" not in briefing.body
