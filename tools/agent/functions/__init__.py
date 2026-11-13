"""The agent's own functions and reference kinds, declared the same way any
other tool contributes them (``AgentTool.agent = "tools.agent.functions"``).

Every function states ``risk``, ``output``, ``scopes`` and ``min_role``; a test
fails one that does not. Object arguments carry ``x-ref``.
"""

from __future__ import annotations

from tools._framework.agentspec import AgentFunction, RefKind
from tools._framework.discovery import REPO_ROOT

from .common import ref_param, schema

ALL = ("personal", "lab", "department", "project")
H = "tools.agent.functions"

SKILLS_DIR = str(REPO_ROOT / "tools" / "agent" / "skills")


def _f(
    name,
    activity,
    summary,
    description,
    handler,
    *,
    params=None,
    required=(),
    output,
    core=False,
    group="",
    scopes=ALL,
    min_role=None,
    feature=None,
    audit=False,
    guest=None,
):
    return AgentFunction(
        name=name,
        activity=activity,
        summary=summary,
        description=description,
        parameters=schema(params, required),
        handler=handler,
        risk="read",
        output=output,
        scopes=scopes,
        min_role=min_role or {},
        core=core,
        feature=feature,
        audit=audit,
        group=group,
        guest=guest,
    )


AGENT = (
    _f(
        "ask_user",
        "Asking you a question",
        "Ask the person one question and wait for the answer.",
        "Ask the person one question when you cannot go on without their answer. "
        "The turn pauses until they answer. Offer options when the answer is a choice.",
        f"{H}.core:ask_user",
        group="agent",
        core=True,
        output="person",
        params={
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
        },
        required=("question",),
    ),
    _f(
        "update_todos",
        "Updating the plan",
        "Keep a short plan for a long task.",
        "Record or update your plan for a multi-step task as a list of steps; the "
        "person sees it. Send the whole list each time.",
        f"{H}.core:update_todos",
        group="agent",
        core=True,
        guest="public",
        output="person",
        params={
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "done": {"type": "boolean"},
                    },
                },
            }
        },
        required=("items",),
    ),
    _f(
        "find_functions",
        "Looking for the right tools",
        "Search the functions you can load.",
        "Search every function available to you here by what it does; returns names "
        "to pass to load_functions.",
        f"{H}.core:find_functions",
        group="agent",
        core=True,
        output="instance",
        params={"query": {"type": "string"}},
        required=("query",),
        guest="public",
    ),
    _f(
        "load_functions",
        "Getting tools ready",
        "Load functions by name for the rest of the conversation.",
        "Load functions listed under 'More functions' so you can call them from your "
        "next step on. They stay loaded for this conversation.",
        f"{H}.core:load_functions",
        group="agent",
        core=True,
        output="instance",
        params={"names": {"type": "array", "items": {"type": "string"}}},
        required=("names",),
        guest="public",
    ),
    _f(
        "read_skill",
        "Checking how to approach this",
        "Read a skill's instructions.",
        "Read the full instructions of a skill listed in your instructions before "
        "doing the task it covers.",
        f"{H}.core:read_skill",
        group="agent",
        core=True,
        output="instance",
        params={"name": {"type": "string"}},
        required=("name",),
        guest="public",
    ),
    _f(
        "read_result",
        "Rereading an earlier result",
        "Read more of an earlier, shortened or cleared result.",
        "Show an earlier function result again, from an offset, when it was cut "
        "short or cleared to save room.",
        f"{H}.core:read_result",
        group="agent",
        core=True,
        guest="public",
        output="person",
        params={
            "call_id": {"type": "string", "x-ref": "thread"},
            "offset": {"type": "integer"},
        },
        required=("call_id",),
    ),
    _f(
        "thread_search",
        "Looking through your earlier conversations",
        "Search this person's earlier conversations with Mylo.",
        "Find earlier conversations this person had with you, by what they were "
        "about. Returns titles, purposes and dates.",
        f"{H}.core:thread_search",
        group="agent",
        core=True,
        output="person",
        params={"query": {"type": "string"}, "limit": {"type": "integer"}},
        required=("query",),
    ),
)

ME = (
    _f(
        "me_profile",
        "Looking at your profile",
        "The person's own profile: name, title, labs, projects.",
        "The person's own account: name, title, institution, labs and departments "
        "with their role, and their projects.",
        f"{H}.me:me_profile",
        core=True,
        output="person",
    ),
    _f(
        "me_interests",
        "Looking at your interests",
        "The person's declared interest clusters and watch topics.",
        "The interest clusters and search terms the person declared, which drive "
        "their feed. They edit these in the app.",
        f"{H}.me:me_interests",
        core=True,
        output="person",
    ),
    _f(
        "me_understanding",
        "Checking what I know about you",
        "What Mylo has confirmed about the person, and what is pending.",
        "What Mylo understands about the person: confirmed preferences, direction and "
        "learning goals; things confirmed in conversation; and observations noticed "
        "but not confirmed (which change nothing).",
        f"{H}.me:me_understanding",
        core=True,
        output="person",
    ),
)

PROJECTS = (
    _f(
        "projects_list",
        "Looking at your projects",
        "Projects the person can see here.",
        "List the projects visible to the person in this conversation's scope "
        "(in a project thread: that project).",
        f"{H}.projects:projects_list",
        output="public",
        guest="no_people",
    ),
    _f(
        "projects_get",
        "Looking at the project",
        "One project: goals, state, blockers, developments, members.",
        "Read one project: goals, aliases, its confirmed state (problem, method, "
        "blockers, stage, milestones), developments in effect, and members. In a "
        "project thread the project argument may be left out.",
        f"{H}.projects:projects_get",
        output="public",
        params={"project": ref_param("project", "#n or project:<uuid>")},
        guest="no_people",
    ),
    _f(
        "projects_feed",
        "Looking at the project's feed",
        "A project's current slate of papers and calls, in rank order.",
        "The project's current per-category slate from the nightly ranking, in rank "
        "order, with why each item fits and when it entered.",
        f"{H}.projects:projects_feed",
        output="public",
        params={
            "project": ref_param("project", "#n or project:<uuid>"),
            "types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["paper", "grant", "fellowship", "conference"],
                },
            },
            "limit": {"type": "integer"},
        },
        guest="no_people",
    ),
)

CORPUS = (
    _f(
        "corpus_search",
        "Searching the corpus for “{query}”",
        "Search the shared corpus of papers, grants, fellowships, conferences.",
        "Search Mycelium's corpus by meaning and keywords. Returns the best matches "
        "with reference numbers to read further with corpus_item.",
        f"{H}.corpus:corpus_search",
        core=True,
        output="instance",
        params={
            "query": {"type": "string"},
            "types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["paper", "grant", "fellowship", "conference"],
                },
            },
            "limit": {"type": "integer"},
        },
        required=("query",),
        guest="public",
    ),
    _f(
        "corpus_item",
        "Reading {item}",
        "One corpus item: details, deadlines, whether it is still open, abstract.",
        "Read one paper, grant, fellowship or conference: its details, deadlines, "
        "whether it is still open, Mycelium's reading of its problem and method, and "
        "its abstract.",
        f"{H}.corpus:corpus_item",
        core=True,
        output="instance",
        params={"item": ref_param("item", "#n or item:<uuid>")},
        required=("item",),
        guest="public",
    ),
)

ITEM = ref_param("item", "#n or item:<uuid>")
LAB = ref_param("lab", "#n or lab:<slug>; default: this conversation's lab")
PROJECT = ref_param(
    "project", "#n or project:<uuid>; default: this conversation's project"
)
PERSON = ref_param("person", "#n or person:<username>")
KINDS = {
    "type": "array",
    "items": {"type": "string", "enum": ["paper", "grant", "fellowship", "conference"]},
}

ORG = (
    _f(
        "org_labs",
        "Looking at your labs",
        "The labs the person belongs to, with their role.",
        "List the labs the person is a member of, with their role in each.",
        f"{H}.org:org_labs",
        output="person",
    ),
    _f(
        "org_lab",
        "Looking at the lab",
        "One lab: profile clusters, member count, the person's role.",
        "Read one lab's profile (statement, declared interest clusters, funding "
        "needs), its member count, its department and the person's role there.",
        f"{H}.org:org_lab",
        output="lab",
        params={"lab": LAB},
        guest="no_people",
    ),
    _f(
        "org_lab_members",
        "Looking at the lab's members",
        "A lab's members with their role and declared interests.",
        "List a lab's members with their role and the interest labels each declared. "
        "Only declared, visible fields; nothing observed or private.",
        f"{H}.org:org_lab_members",
        output="lab",
        params={"lab": LAB},
        min_role={"lab": "member"},
        audit=True,
        guest="full",
    ),
    _f(
        "org_department",
        "Looking at the department",
        "One department: its labs, member count, profile.",
        "Read one department: its labs, effective member count, the person's role and "
        "its declared profile.",
        f"{H}.org:org_department",
        output="department",
        params={"department": ref_param("department", "#n or department:<uuid>")},
        guest="no_people",
    ),
    _f(
        "org_person",
        "Looking up {person}",
        "One visible person: name, labs in common, declared interests.",
        "Read the visible fields of one person: name, username, labs in common with "
        "the person asking, and the interest labels they declared. Never anything "
        "private.",
        f"{H}.org:org_person",
        output="lab",
        params={"person": PERSON},
        required=("person",),
        audit=True,
        guest="full",
    ),
)

FEEDS = (
    _f(
        "feeds_slate",
        "Looking at the current feed",
        "The current per-category slate of the person, a lab, a project.",
        "The current Top-25 slate per category from the nightly ranking, in rank "
        "order, with why each item fits: the person's own (in a personal thread), or a "
        "lab's or project's (named, or this conversation's).",
        f"{H}.feeds:feeds_slate",
        output="lab",
        params={
            "lab": LAB,
            "project": PROJECT,
            "types": KINDS,
            "limit": {"type": "integer", "description": "per category, at most 25"},
        },
        guest="no_people",
    ),
    _f(
        "feeds_briefing",
        "Reading the latest report",
        "The latest daily or weekly Mylo report.",
        "The latest daily or weekly report Mylo wrote for the person, or for a lab: "
        "its date, what entered the Top-25, and the report text.",
        f"{H}.feeds:feeds_briefing",
        output="lab",
        params={"kind": {"type": "string", "enum": ["daily", "weekly"]}, "lab": LAB},
        guest="no_people",
    ),
    _f(
        "feeds_saved",
        "Looking at saved items",
        "The person's saved items (and this lab's saves).",
        "The items the person saved, with their deadlines and notes; in a lab or "
        "project conversation also the lab's saves.",
        f"{H}.feeds:feeds_saved",
        output="person",
        params={"types": KINDS, "limit": {"type": "integer"}},
    ),
    _f(
        "feeds_deadlines",
        "Checking upcoming deadlines",
        "Upcoming deadlines among saved and slate items.",
        "Deadlines in the coming days (default 60) of the grants, fellowships and "
        "conferences the person or this lab saved or has in its current slate.",
        f"{H}.feeds:feeds_deadlines",
        output="lab",
        params={"days": {"type": "integer"}, "limit": {"type": "integer"}},
        guest="no_people",
    ),
)

KNOWLEDGE = (
    _f(
        "knowledge_my_concepts",
        "Looking at your research topics",
        "What the graph holds about the person, by tier.",
        "The concepts the graph links to the person, grouped by evidence: declared in "
        "their profile, demonstrated by their papers, confirmed in conversation, and "
        "suggestions not yet confirmed.",
        f"{H}.knowledge:knowledge_my_concepts",
        output="person",
    ),
    _f(
        "knowledge_project_concepts",
        "Looking at the project's topics",
        "A project's concepts; which no member declares.",
        "The problem, method, setting and need concepts a project declares, marking "
        "the ones none of its people declares in their profile (a gap).",
        f"{H}.knowledge:knowledge_project_concepts",
        output="lab",
        params={"project": PROJECT},
    ),
    _f(
        "knowledge_backing",
        "Checking which of your topics your papers back",
        "Which of the person's declared topics their papers back.",
        "For each topic the person declares or their papers show: declared and backed, "
        "declared only (weaker), or shown by papers but not declared.",
        f"{H}.knowledge:knowledge_backing",
        output="person",
    ),
    _f(
        "knowledge_introduction_paths",
        "Finding who could introduce you to {person}",
        "Who could introduce the person to someone.",
        "The shortest co-authorship chain from the person to someone they can see, "
        "passing only through people they can already see.",
        f"{H}.knowledge:knowledge_introduction_paths",
        output="person",
        params={"person": PERSON},
        required=("person",),
        audit=True,
    ),
    _f(
        "knowledge_people_for_call",
        "Finding who could go after {call}",
        "Who in the lab could go after a grant or call.",
        "For a call, which of its requirement slots each lab member covers and with "
        "what evidence (declared, demonstrated, confirmed in conversation — lab-mates "
        "on their declared profile only), the gaps, and who the nightly ranking "
        "named for it.",
        f"{H}.knowledge:knowledge_people_for_call",
        output="lab",
        scopes=("personal", "lab", "project"),
        min_role={"lab": "member"},
        audit=True,
        params={"call": ITEM, "lab": LAB},
        required=("call",),
        guest="full",
    ),
    _f(
        "knowledge_people_beyond_lab",
        "Looking beyond the lab for {call}",
        "People beyond the lab who could join a call.",
        "Search people outside the person's lab who are open to collaborating with "
        "them and fill a call's gaps or share its expertise, from their declared "
        "profile and papers. Counts against the person's daily collaborator searches.",
        f"{H}.knowledge:knowledge_people_beyond_lab",
        output="person",
        feature="features.collab_search",
        audit=True,
        params={"call": ITEM},
        required=("call",),
    ),
)

FUNCTIONS = AGENT + ME + PROJECTS + CORPUS + ORG + FEEDS + KNOWLEDGE

K = "tools.agent.functions.kinds"
REFS = (
    RefKind(
        "item",
        f"{K}:resolve_item",
        f"{K}:search_items",
        "A paper, grant, fellowship or conference in the corpus.",
    ),
    RefKind("project", f"{K}:resolve_project", f"{K}:search_projects", "A project."),
    RefKind("lab", f"{K}:resolve_lab", f"{K}:search_labs", "A lab."),
    RefKind("department", f"{K}:resolve_department", None, "A department."),
    RefKind("person", f"{K}:resolve_person", f"{K}:search_people", "A person."),
)
