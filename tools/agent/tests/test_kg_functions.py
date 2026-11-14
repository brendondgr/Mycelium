"""Phase 8: the org, feeds and knowledge groups, all through the gate.

Each function is checked visible, invisible (another lab's object is denied at
layer 6 with ``not_visible``) and, where its output is mixed, filtered for a
lab audience before the model reads anything.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from tools.agent import dispatch, registry
from tools.agent.caller import Audience, Caller, Scope

from .conftest import make_user, thread_for

pytestmark = pytest.mark.django_db


def run(
    user, name, args, *, kind="personal", obj=None, width="person", audience_obj=None
):
    thread = thread_for(user, kind, obj)
    c = Caller(
        user=user,
        surface="web",
        scope=Scope(kind, obj),
        audience=Audience(width, audience_obj),
        thread_id=thread.pk,
    )
    return dispatch.run(c, thread, name=name, args=args, call_id="c1")


def lab_run(user, name, args, lab, **kw):
    """A reply the whole lab reads (a Discord channel bound to ``lab``)."""
    return run(
        user,
        name,
        args,
        kind=kw.pop("kind", "lab"),
        obj=kw.pop("obj", lab),
        width="lab",
        audience_obj=lab,
        **kw,
    )


def item(title, type_="paper", **meta):
    from tools.retrieval.read import ContentItem

    return ContentItem.objects.create(
        type=type_,
        source="test",
        external_id=title[:20],
        metadata={"title": title, **meta},
    )


def edge(
    user,
    label,
    tier="declared",
    status="active",
    relation="interested_in",
    facet="area",
    **subject,
):
    from apps.knowledge.models import Concept, Edge

    concept = Concept.objects.filter(
        label=label, facet=facet
    ).first() or Concept.objects.create(label=label, facet=facet)
    return Edge.objects.create(
        concept=concept,
        relation=relation,
        tier=tier,
        status=status,
        surface=label,
        **({"user": user} if user else subject),
    )


def interests(user, *labels):
    user.profile.interests = {
        "clusters": [{"label": lbl, "areas": [lbl + " methods"]} for lbl in labels]
    }
    user.profile.save(update_fields=["interests"])


@pytest.fixture
def second(world):
    """A second lab the member also belongs to."""
    from apps.accounts.models import Lab, LabMembership

    lab = Lab.objects.create(name="Second Lab", slug="second")
    LabMembership.objects.create(user=world.member, lab=lab, role="member")
    return lab


def test_the_new_groups_are_registered():
    groups = registry.registry().groups()
    for group in ("org", "feeds", "knowledge", "fulltext"):
        assert group in groups, group
    assert registry.registry().refused == {}


# -- org ---------------------------------------------------------------------


def test_org_labs_lists_the_persons_labs_and_roles(world, second):
    out = run(world.member, "org_labs", {})
    assert out["status"] == "ok"
    assert (
        "Imaging Lab — you are member" in out["content"]
        and "Second Lab" in out["content"]
    )
    assert "Other Lab" not in out["content"]


def test_org_lab_visible_and_another_lab_denied(world):
    from apps.accounts.models import LabProfile

    LabProfile.objects.filter(lab=world.lab).update(
        statement="We image cells.",
        interests={"clusters": [{"label": "Microscopy", "areas": ["light sheet"]}]},
    )
    out = run(world.member, "org_lab", {"lab": "lab:imaging"})
    assert out["status"] == "ok"
    assert (
        "Your role: member" in out["content"]
        and "Microscopy: light sheet" in out["content"]
    )
    assert "Members: 5" in out["content"] and "Department: Biology" in out["content"]
    denied = run(world.member, "org_lab", {"lab": "lab:other"})
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"
    assert denied["decision"]["layer"] == 6


def test_org_lab_in_a_lab_channel_reads_only_that_lab(world, second):
    out = lab_run(world.member, "org_lab", {"lab": "lab:second"}, world.lab)
    # the gate refuses it (layer 9, which org); the handler would too
    assert out["status"] in ("denied", "error") and out["error"]["code"] == "audience"
    assert "Second Lab" not in out.get("content", "")
    assert lab_run(world.member, "org_lab", {}, world.lab)["status"] == "ok"


def test_org_lab_members_shows_declared_labels_only_and_is_audited(world):
    from apps.accounts.models import AuditEvent

    interests(world.admin, "Cell tracking")
    edge(world.admin, "secret hobby", tier="conversational")
    out = run(world.member, "org_lab_members", {}, kind="lab", obj=world.lab)
    assert out["status"] == "ok"
    content = out["content"]
    assert "@admin" in content and "Cell tracking" in content and "@owner" in content
    assert "secret hobby" not in content
    assert AuditEvent.objects.filter(action="agent.org_lab_members").exists()


def test_org_lab_members_needs_the_member_role(world):
    out = run(world.viewer, "org_lab_members", {}, kind="lab", obj=world.lab)
    assert out["status"] == "denied" and out["error"]["code"] == "role"
    # Named from a personal thread, the handler holds the same line.
    out = run(world.viewer, "org_lab_members", {"lab": "lab:imaging"})
    assert out["status"] == "error" and out["error"]["code"] == "role"
    out = run(world.member, "org_lab_members", {"lab": "lab:other"})
    assert out["status"] == "denied" and out["error"]["code"] == "not_visible"


def test_org_department(world):
    out = run(
        world.owner, "org_department", {"department": f"department:{world.dept.pk}"}
    )
    assert out["status"] == "ok"
    assert "Biology" in out["content"] and "Your role: owner" in out["content"]
    assert "Imaging Lab" in out["content"]
    out = run(
        world.outsider, "org_department", {"department": f"department:{world.dept.pk}"}
    )
    assert out["status"] == "denied" and out["error"]["code"] == "not_visible"


def test_org_person_visible_fields_only(world):
    interests(world.admin, "Cell tracking")
    edge(world.admin, "private worry", tier="conversational")
    out = run(world.member, "org_person", {"person": "person:admin"})
    assert out["status"] == "ok"
    assert "@admin" in out["content"] and "Imaging Lab" in out["content"]
    assert "Cell tracking" in out["content"] and "private worry" not in out["content"]
    denied = run(world.member, "org_person", {"person": "person:othermember"})
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"


def test_org_person_in_a_lab_channel_names_only_that_labs_people(world, second):
    from apps.accounts.models import LabMembership

    stranger = make_user("seconder")
    LabMembership.objects.create(user=stranger, lab=second, role="member")
    out = lab_run(world.member, "org_person", {"person": "person:seconder"}, world.lab)
    # the gate refuses it (layer 9, which org); the handler would too
    assert out["status"] in ("denied", "error") and out["error"]["code"] == "audience"
    LabMembership.objects.create(user=world.admin, lab=second, role="member")
    ok = lab_run(world.member, "org_person", {"person": "person:admin"}, world.lab)
    assert ok["status"] == "ok" and "Second Lab" not in ok["content"]


# -- feeds -------------------------------------------------------------------


def score(content, rank, **target):
    from tools.recommendation.read import RelevanceScore

    signals = {"top_rank": rank, "reason": f"reason {rank}"} if rank else {}
    signals.update(target.pop("signals", {}))
    return RelevanceScore.objects.create(
        content=content, score=0.5, signals=signals, **target
    )


def test_feeds_slate_personal_lab_and_project(world):
    mine, labs, outside = (
        item("Mine paper"),
        item("Lab grant", "grant"),
        item("Not ranked"),
    )
    score(mine, 1, target_user=world.member)
    score(outside, None, target_user=world.member)
    score(
        labs,
        1,
        target_lab=world.lab,
        signals={"member_fit": [{"username": "admin", "reason": "tracks cells"}]},
    )
    out = run(world.member, "feeds_slate", {})
    assert out["status"] == "ok" and "Mine paper" in out["content"]
    assert "Not ranked" not in out["content"] and "Lab grant" not in out["content"]
    out = run(world.member, "feeds_slate", {}, kind="lab", obj=world.lab)
    assert "Lab grant" in out["content"] and "who should look: Admin" in out["content"]
    assert "Mine paper" not in out["content"]
    denied = run(
        world.member, "feeds_slate", {"project": f"project:{world.other_project.pk}"}
    )
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"


def test_feeds_slate_in_a_lab_channel_never_shows_the_persons_own(world):
    score(item("Mine paper"), 1, target_user=world.member)
    score(item("Lab grant", "grant"), 1, target_lab=world.lab)
    out = lab_run(world.member, "feeds_slate", {}, world.lab, kind="personal", obj=None)
    # the gate refuses it (layer 9, which org); the handler would too
    assert out["status"] in ("denied", "error") and out["error"]["code"] == "audience"
    out = lab_run(world.member, "feeds_slate", {}, world.lab)
    assert out["status"] == "ok" and "Lab grant" in out["content"]
    assert "Mine paper" not in out["content"]
    # a personal project is narrower than the lab: refused before the handler
    out = lab_run(
        world.member,
        "feeds_slate",
        {"project": f"project:{world.personal.pk}"},
        world.lab,
    )
    assert out["status"] == "denied" and out["error"]["code"] == "audience"


def test_feeds_briefing_person_and_lab(world):
    from tools.delivery.read import DailyBriefing

    DailyBriefing.objects.create(
        user=world.member, body="Personal report body.", new_counts={"papers": 2}
    )
    DailyBriefing.objects.create(lab=world.lab, body="Lab report body.")
    out = run(world.member, "feeds_briefing", {})
    assert out["status"] == "ok" and "Personal report body." in out["content"]
    assert "papers 2" in out["content"]
    out = lab_run(world.member, "feeds_briefing", {}, world.lab)
    assert "Lab report body." in out["content"] and "Personal" not in out["content"]
    out = run(world.member, "feeds_briefing", {"kind": "weekly"})
    assert "not been written yet" in out["content"]
    denied = run(world.member, "feeds_briefing", {"lab": "lab:other"})
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"


def save(user, content, lab=None, **kw):
    from tools.delivery.read import SavedOpportunity

    return SavedOpportunity.objects.create(
        user=user,
        target_lab=lab,
        content=content,
        area=content.type,
        title=content.metadata["title"],
        **kw,
    )


def test_feeds_saved_is_the_persons_own(world):
    save(world.member, item("My saved grant", "grant"), note="ask PI")
    save(world.admin, item("Admin saved grant", "grant"))
    out = run(world.member, "feeds_saved", {})
    assert out["status"] == "ok"
    assert "My saved grant" in out["content"] and "ask PI" in out["content"]
    assert "Admin saved grant" not in out["content"]
    out = lab_run(world.member, "feeds_saved", {}, world.lab)
    assert out["status"] == "denied" and out["error"]["code"] == "audience"


def deadline(content, days):
    from tools.retrieval.read import ContentDeadline

    return ContentDeadline.objects.create(
        content=content,
        kind="application",
        confidence="confirmed",
        due_date=timezone.localdate() + timedelta(days=days),
    )


def test_feeds_deadlines_mixed_output(world):
    mine, labs, late = (
        item("My saved grant", "grant"),
        item("Lab slate grant", "grant"),
        item("Far grant", "grant"),
    )
    save(world.member, mine)
    save(world.member, late)
    score(labs, 1, target_lab=world.lab)
    deadline(mine, 10)
    deadline(labs, 20)
    deadline(late, 200)
    out = run(world.member, "feeds_deadlines", {}, kind="lab", obj=world.lab)
    assert out["status"] == "ok"
    content = out["content"]
    assert content.index("My saved grant") < content.index("Lab slate grant")
    assert "in 10 days" in content and "Far grant" not in content
    out = lab_run(world.member, "feeds_deadlines", {}, world.lab)
    assert (
        "Lab slate grant" in out["content"] and "My saved grant" not in out["content"]
    )


# -- knowledge ---------------------------------------------------------------


def test_knowledge_my_concepts_by_tier(world):
    edge(world.member, "segmentation")
    edge(world.member, "microscopy", tier="demonstrated")
    edge(world.member, "tracking", tier="conversational")
    edge(world.member, "maybe this", tier="conversational", status="pending")
    edge(world.admin, "not mine")
    out = run(world.member, "knowledge_my_concepts", {})
    content = out["content"]
    assert content.index("Declared") < content.index("segmentation")
    assert "Confirmed in conversation (1):\n- interested in tracking" in content
    assert "not confirmed" in content and "maybe this" in content
    assert "not mine" not in content
    assert (
        lab_run(world.member, "knowledge_my_concepts", {}, world.lab)["status"]
        == "denied"
    )


def test_knowledge_project_concepts_marks_undeclared(world):
    edge(
        None,
        "cell segmentation",
        relation="works_on",
        facet="problem",
        project=world.lab_project,
    )
    edge(
        None,
        "optogenetics",
        relation="uses_method",
        facet="method",
        project=world.lab_project,
    )
    edge(world.member, "cell segmentation", facet="problem")
    out = run(
        world.member,
        "knowledge_project_concepts",
        {},
        kind="project",
        obj=world.lab_project,
    )
    lines = out["content"].splitlines()
    assert any("optogenetics — none of its people" in line for line in lines)
    assert not any("cell segmentation —" in line for line in lines)
    denied = run(
        world.member,
        "knowledge_project_concepts",
        {"project": f"project:{world.other_project.pk}"},
    )
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"


def test_knowledge_backing(world):
    from apps.knowledge.models import Concept, Edge

    concept = Concept.objects.create(label="segmentation", facet="method")
    for tier in ("declared", "demonstrated"):
        Edge.objects.create(
            user=world.member,
            concept=concept,
            relation="uses_method",
            tier=tier,
            surface="segmentation",
            evidence=["work:W1"] if tier == "demonstrated" else [],
        )
    edge(world.member, "only said")
    out = run(world.member, "knowledge_backing", {})
    assert (
        "Declared and backed by your papers:\n- segmentation (1 works)"
        in out["content"]
    )
    assert "weaker evidence:\n- only said" in out["content"]


def test_knowledge_introduction_paths_only_through_visible_people(world):
    from apps.knowledge.models import Coauthorship

    def link(a, b):
        a, b = sorted((a, b), key=lambda u: u.pk)
        Coauthorship.objects.create(a=a, b=b)

    link(world.member, world.admin)
    link(world.admin, world.owner)
    out = run(world.member, "knowledge_introduction_paths", {"person": "person:owner"})
    assert out["status"] == "ok" and "you → #2 @admin → @owner" in out["content"]
    # the only route to the viewer runs through someone the member can't see
    link(world.member, world.outsider)
    link(world.outsider, world.viewer)
    out = run(world.member, "knowledge_introduction_paths", {"person": "person:viewer"})
    assert (
        "No co-authorship path" in out["content"] and "outsider" not in out["content"]
    )
    denied = run(
        world.member, "knowledge_introduction_paths", {"person": "person:othermember"}
    )
    assert denied["status"] == "denied" and denied["error"]["code"] == "not_visible"


@pytest.fixture
def call(world):
    """A grant with four slots; the member declares one and confirmed another in
    conversation, the admin declares a third and said the fourth only in chat."""
    from apps.collab.models import RequirementSlots

    from tools.delivery.read import MemberSuggestion

    grant = item("Reef imaging grant", "grant")
    RequirementSlots.objects.create(
        content=grant,
        status="ok",
        prompt_version="t",
        source_fingerprint="x",
        slots=[
            {"facet": "method", "text": "light sheet microscopy", "required": True},
            {"facet": "problem", "text": "cell tracking", "required": False},
            {"facet": "method", "text": "environmental health", "required": True},
            {"facet": "role", "text": "a park authority", "required": True},
        ],
    )
    edge(world.member, "light sheet microscopy", facet="method")
    edge(world.member, "environmental health", tier="conversational", facet="method")
    edge(world.admin, "cell tracking", facet="problem")
    edge(world.admin, "environmental health", tier="conversational", facet="method")
    score(
        grant,
        3,
        target_lab=world.lab,
        signals={"member_fit": [{"username": "viewer", "reason": "runs the scope"}]},
    )
    MemberSuggestion.objects.create(
        user=world.owner,
        project=world.lab_project,
        content=grant,
        score=0.8,
        suggested=True,
        floor_used=0.5,
    )
    return grant


def test_people_for_call_in_the_lab_with_evidence_tiers(world, call):
    out = run(
        world.member,
        "knowledge_people_for_call",
        {"call": f"item:{call.pk}"},
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "ok", out
    content = out["content"]
    you = next(line for line in content.splitlines() if line.startswith("- you covers"))
    assert "“light sheet microscopy” [declared: light sheet microscopy]" in you
    assert (
        "“environmental health” [confirmed in conversation: environmental health]"
        in you
    )
    admin = next(line for line in content.splitlines() if "@admin covers" in line)
    assert "cell tracking" in admin and "environmental health" not in admin
    assert "Gaps" not in content  # the member's own confirmed conversation covers it
    assert "Roles it asks for (never matched to a profile): a park authority" in content
    assert "@viewer — runs the scope" in content
    assert "@owner — already suggested" in content


def test_people_for_call_in_a_lab_channel_drops_conversation(world, call):
    out = lab_run(
        world.member,
        "knowledge_people_for_call",
        {"call": f"item:{call.pk}"},
        world.lab,
    )
    assert out["status"] == "ok"
    content = out["content"]
    assert "confirmed in conversation:" not in content.split("Evidence tiers")[0]
    assert "Gaps (no one here covers): environmental health" in content


def test_people_for_call_needs_a_visible_lab_and_member_role(world, call):
    out = run(
        world.member,
        "knowledge_people_for_call",
        {"call": f"item:{call.pk}", "lab": "lab:other"},
    )
    assert out["status"] == "denied" and out["error"]["code"] == "not_visible"
    out = run(
        world.viewer,
        "knowledge_people_for_call",
        {"call": f"item:{call.pk}"},
        kind="lab",
        obj=world.lab,
    )
    assert out["status"] == "denied" and out["error"]["code"] == "role"


def test_people_beyond_lab_needs_the_feature(world, call, settings):
    settings.COLLAB_SEARCH_ENABLED = False
    out = run(world.member, "knowledge_people_beyond_lab", {"call": f"item:{call.pk}"})
    assert out["status"] == "denied" and out["error"]["code"] == "feature_off"
    assert out["decision"]["layer"] == 3


def test_people_beyond_lab_refusal_has_a_plain_fix(world, call, settings, monkeypatch):
    from apps.collab import matcher

    settings.COLLAB_SEARCH_ENABLED = True
    monkeypatch.setattr(
        matcher,
        "query_for_call",
        lambda seeker, c: matcher.Query(
            "call", [{"facet": "method", "text": "x", "vector": [1.0]}]
        ),
    )

    def refuse(seeker, query):
        raise matcher.SearchRefused("verify your email to search", "unverified")

    monkeypatch.setattr(matcher, "search", refuse)
    out = run(world.member, "knowledge_people_beyond_lab", {"call": f"item:{call.pk}"})
    assert out["status"] == "error" and out["error"]["code"] == "search_unverified"
    assert "Verify your email" in out["error"]["fix"]


def test_people_beyond_lab_lists_lanes(world, call, settings, monkeypatch):
    from apps.collab import matcher

    settings.COLLAB_SEARCH_ENABLED = True
    monkeypatch.setattr(
        matcher,
        "query_for_call",
        lambda seeker, c: matcher.Query(
            "call", [{"facet": "method", "text": "x", "vector": [1.0]}]
        ),
    )
    row = {
        "username": "far",
        "name": "Far Away",
        "institution": "Elsewhere U",
        "lane": "method_bridge",
        "slot": "environmental health",
        "facet": "method",
        "matched": "exposure science",
        "tier": "demonstrated",
        "reason": "papers on it",
    }
    monkeypatch.setattr(
        matcher,
        "search",
        lambda seeker, query: matcher.SearchResult(
            lanes={"method_bridge": [row]}, search_id=1
        ),
    )
    out = run(world.member, "knowledge_people_beyond_lab", {"call": f"item:{call.pk}"})
    assert out["status"] == "ok"
    assert "Fills a gap:\n- Far Away (@far, Elsewhere U)" in out["content"]
    assert "[demonstrated by their papers: exposure science]" in out["content"]
    assert (
        lab_run(
            world.member,
            "knowledge_people_beyond_lab",
            {"call": f"item:{call.pk}"},
            world.lab,
        )["status"]
        == "denied"
    )


# -- fulltext, through the gate (the tool's own tests call its handlers directly)


@pytest.fixture
def stored_paper(tmp_path):
    """A stored full text, made without importing the (optional) fulltext tool."""
    from django.apps import apps
    from django.test import override_settings

    from tools._framework import host

    if not host.is_loaded("fulltext"):
        pytest.skip("the fulltext tool is not loaded")
    document = apps.get_model("fulltext", "FulltextDocument")
    md = tmp_path / "store" / "files" / "ab" / "abc.md"
    md.parent.mkdir(parents=True)
    md.write_text("# Stored paper\n\n## Methods\nWe did it.", encoding="utf-8")
    with override_settings(FULLTEXT_DATA_DIR=str(tmp_path / "store")):
        paper = item("Stored paper", doi="10.1/kg")
        doc = document.objects.create(
            content_item=paper,
            doi="10.1/kg",
            title="Stored paper",
            source="pmc",
            markdown_path="files/ab/abc.md",
            chars=40,
            sha256="abc",
        )
        yield paper, doc


def test_fulltext_functions_come_from_the_fulltext_tool(stored_paper):
    reg = registry.registry()
    assert reg.owner["fulltext_read_paper"] == "fulltext"
    assert reg.ref_owner["doc"] == "fulltext"


def test_fulltext_read_through_the_gate_numbers_the_document(world, stored_paper):
    paper, doc = stored_paper
    out = run(world.member, "fulltext_availability", {"item": f"item:{paper.pk}"})
    assert out["status"] == "ok" and out["refs"] == [1]
    out = run(world.member, "fulltext_read_paper", {"document": f"doc:{doc.pk}"})
    assert out["status"] == "ok" and out["untrusted"] is True
    assert "    4| We did it." in out["content"]


def test_fulltext_unknown_document_or_item_is_denied(world, stored_paper):
    import uuid

    for args in ({"document": f"doc:{uuid.uuid4()}"}, {"item": f"item:{uuid.uuid4()}"}):
        out = run(world.member, "fulltext_read_paper", args)
        assert out["status"] == "denied" and out["error"]["code"] == "not_visible"


def test_fulltext_text_is_not_offered_beyond_a_lab(world, stored_paper):
    paper, _ = stored_paper
    out = run(
        world.member,
        "fulltext_read_paper",
        {"item": f"item:{paper.pk}"},
        kind="department",
        obj=world.dept,
        width="department",
        audience_obj=world.dept,
    )
    assert out["status"] == "denied" and out["error"]["code"] == "audience"
