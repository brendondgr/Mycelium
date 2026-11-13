"""The ``knowledge`` group: what the graph holds about the person, a project's
concepts, which claims their papers back, introduction paths, and who could go
after a call.

Everything goes through the knowledge core's read door (``apps.knowledge.read``),
which already decides which tiers each reader may see, and through the
collaboration app's coverage and matcher. Two rules from there are kept here:

* a lab-mate is named for a call only on what their profile **declares**
  (``collab.coverage``); their papers and anything Mylo understood from
  conversation never name them. Only the caller's own row shows the
  demonstrated and conversation tiers, and only in a reply the caller alone
  reads;
* outward search (beyond the lab) runs only with ``features.collab_search`` on
  and the matcher's own consent gate passed.
"""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common
from .org import audience_lab_ok, lab_arg, shared

TIER_NAMES = {
    "declared": "declared",
    "demonstrated": "demonstrated by their papers",
    "conversational": "confirmed in conversation",
}


def _rel(relation: str) -> str:
    return relation.replace("_", " ")


def knowledge_my_concepts(caller):
    from apps.knowledge import read

    edges = read.own_edges(caller.user)
    if not edges:
        return Result(
            content="The knowledge graph holds nothing about you yet "
            "(it fills from your profile, papers and confirmed "
            "conversation)."
        )
    groups = {
        "Declared (your profile)": [
            e for e in edges if e.tier == "declared" and e.status == "active"
        ],
        "Demonstrated by your papers": [
            e for e in edges if e.tier == "demonstrated" and e.status == "active"
        ],
        "Confirmed in conversation": [
            e for e in edges if e.tier == "conversational" and e.status == "active"
        ],
        "Suggested from conversation, not confirmed (changes nothing)": [
            e for e in edges if e.status == "pending"
        ],
        "You said no to, or faded": [
            e for e in edges if e.status in ("rejected", "faded")
        ],
    }
    out = []
    for title, rows in groups.items():
        if not rows:
            continue
        out.append(f"{title} ({len(rows)}):")
        out += [
            f"- {_rel(e.relation)} {e.surface or e.label}"
            + (f" ({e.facet})" if e.facet else "")
            for e in rows[:40]
        ]
    out.append("The person reviews these in the app; you cannot change them.")
    return Result(content="\n".join(out))


def knowledge_project_concepts(caller, project=None):
    from apps.knowledge import read

    from .feeds import _project_ok
    from .projects import _project

    p = _project(caller, project)
    _project_ok(caller, p)
    info = common.project_info(p)
    edges = read.project_edges(p, caller.user)
    missing = {e.concept_id for e in read.undeclared_project_concepts(p, caller.user)}
    if not edges:
        return Result(
            content=f"{{ref:{info.ref}}} {p.name} declares no concepts yet "
            "(they come from its goals and confirmed state).",
            refs=[info],
        )
    lines = [f"Concepts of {{ref:{info.ref}}} {p.name}:"]
    for e in edges:
        flag = " — none of its people declares this" if e.concept_id in missing else ""
        lines.append(f"- {_rel(e.relation)} {e.surface or e.label}{flag}")
    if missing:
        lines.append(
            f"{len(missing)} of its problem/method/setting/need concepts are held "
            "by no member's declared profile (Q1): a gap to fill or a profile to "
            "update."
        )
    return Result(content="\n".join(lines), refs=[info])


def knowledge_backing(caller):
    from apps.knowledge import read

    rows = read.backing(caller.user)
    if not rows:
        return Result(content="Nothing declared or demonstrated yet.")
    both = [b for b in rows if b.declared and b.demonstrated]
    said = [b for b in rows if b.declared_only]
    shown = [b for b in rows if b.demonstrated and not b.declared]
    out = []
    if both:
        out.append("Declared and backed by your papers:")
        out += [f"- {b.surface} ({len(b.works)} works)" for b in both[:30]]
    if said:
        out.append("Declared, not (yet) shown by your papers — weaker evidence:")
        out += [f"- {b.surface}" for b in said[:30]]
    if shown:
        out.append("Shown by your papers, not in your profile:")
        out += [f"- {b.surface} ({len(b.works)} works)" for b in shown[:30]]
    return Result(content="\n".join(out))


def knowledge_introduction_paths(caller, person):
    from apps.knowledge import read

    from .kinds import visible_people

    seen = visible_people(caller.user)
    target = seen.filter(username=common.ref_key(person)).first()
    if target is None:
        raise FunctionError(
            "not_visible",
            "That person is not available.",
            "Introduction paths reach only people with an account here whom you "
            "can see. For an author outside the platform, say who they are from "
            "what you read; there is no path to look up.",
        )
    if target.pk == caller.user.pk:
        raise FunctionError("self", "That is you.", "Name someone else.")
    # Only people the caller can already see may be named on a path.
    through = {u.pk: u for u in seen.exclude(pk__in=[caller.user.pk, target.pk])}
    path = read.introduction_paths(caller.user.pk, [target.pk], list(through)).get(
        target.pk
    )
    info = common.person_info(target, caller=caller)
    if not path:
        return Result(
            content=f"No co-authorship path to {{ref:{info.ref}}} runs only "
            "through people you can see.",
            refs=[info],
        )
    refs, names = [info], []
    for pk in path[1:-1]:
        mid = common.person_info(through[pk], caller=caller)
        refs.append(mid)
        names.append(f"{{ref:{mid.ref}}} @{through[pk].username}")
    if not names:
        return Result(
            content=f"You have co-authored with {{ref:{info.ref}}} directly.", refs=refs
        )
    return Result(
        content=f"Shortest co-authorship path to {{ref:{info.ref}}} "
        f"({len(path) - 1} hops): you → "
        + " → ".join(names)
        + f" → @{target.username}",
        refs=refs,
    )


# --------------------------------------------------------------------------- #
# People for a call (Q3 inside the lab, Q4 beyond it)
# --------------------------------------------------------------------------- #


def _call(item):
    from tools.retrieval.read import ContentItem

    row = ContentItem.objects.filter(pk=common.ref_key(item)).first()
    if row is None:
        raise FunctionError("not_found", "That call is no longer in the corpus.")
    return row


def _own_tiers(user, row, *, declared_only: bool) -> dict[str, list[tuple[str, str]]]:
    """``{slot text: [(tier, matched words)]}`` for the caller's own edges."""
    from apps.collab.coverage import YOU, assess
    from apps.knowledge import read

    edges = [e for e in read.own_edges(user) if e.status == "active"]
    tiers = (
        ("declared",)
        if declared_only
        else ("declared", "demonstrated", "conversational")
    )
    out: dict[str, list[tuple[str, str]]] = {}
    for tier in tiers:
        mine = [e for e in edges if e.tier == tier]
        if not mine:
            continue
        for slot in assess(row, own=mine).slots:
            if slot.covered_by == YOU:
                out.setdefault(slot.text, []).append((tier, slot.matched))
    return out


def knowledge_people_for_call(caller, call, lab=None):
    from apps.collab import coverage
    from apps.collab.models import RequirementSlots

    from tools.delivery.read import MemberSuggestion
    from tools.recommendation.read import RelevanceScore

    from .. import permissions

    target_lab = lab_arg(caller, lab)
    audience_lab_ok(caller, target_lab)
    if permissions.role_of(caller, "lab", target_lab) not in (
        "member",
        "admin",
        "owner",
    ):
        raise FunctionError(
            "role",
            "Naming a lab's people for a call needs the member role there.",
            "Ask a lab admin to change your role.",
        )
    item = _call(call)
    head, li = common.item_info(item), common.lab_info(target_lab)
    refs = [head, li]
    members = {
        m.user.username: m.user for m in target_lab.memberships.select_related("user")
    }
    person = {}

    def ref_of(username):
        if username not in person:
            info = common.person_info(members[username], caller=caller)
            refs.append(info)
            person[username] = info
        return f"{{ref:{person[username].ref}}} @{username}"

    lines = [
        f"Who in {{ref:{li.ref}}} {target_lab.name} could go after "
        f"{{ref:{head.ref}}} {common.item_title(item)}:"
    ]
    slots_row = RequirementSlots.objects.filter(
        content=item, status=RequirementSlots.Status.OK
    ).first()
    covers: dict[str, list[str]] = {}
    covered: set[str] = set()
    if slots_row is None:
        lines.append(
            "Its requirement slots have not been read yet, so coverage can't be "
            "shown; only profile fit below."
        )
    else:
        fit = coverage.for_call(target_lab, item)
        # A guest has no profile of their own: nobody is "you".
        mine = (
            _own_tiers(caller.user, slots_row, declared_only=shared(caller))
            if caller.user is not None
            else {}
        )
        me = caller.user.username if caller.user is not None else None
        for slot in fit.slots if fit else []:
            if slot.is_role:
                continue
            for username in slot.people:
                if username == me and slot.text in mine:
                    continue  # the caller's own line below carries every tier
                covers.setdefault(username, []).append(
                    f"“{slot.text}” [declared: {slot.matched}]"
                )
                covered.add(slot.text)
        for text, found in mine.items():
            tiers = "; ".join(f"{TIER_NAMES[t]}: {w}" for t, w in found)
            covers.setdefault(me, []).append(f"“{text}” [{tiers}]")
            covered.add(text)
        for username in sorted(covers, key=lambda u: (u != me, u)):
            if username not in members:
                continue
            who = "you" if username == me else ref_of(username)
            lines.append(f"- {who} covers " + ", ".join(covers[username]))
        gaps = [
            s["text"]
            for s in slots_row.slots
            if s.get("facet") != "role" and s["text"] not in covered
        ]
        roles = [s["text"] for s in slots_row.slots if s.get("facet") == "role"]
        if not covers:
            lines.append("- Nobody's declared profile covers any of its slots.")
        if gaps:
            lines.append("Gaps (no one here covers): " + "; ".join(gaps))
        if roles:
            lines.append(
                "Roles it asks for (never matched to a profile): " + "; ".join(roles)
            )
    # The member-fit layer: who the nightly run named for this call, and who it
    # already suggested it to.
    fits = []
    row = RelevanceScore.objects.filter(target_lab=target_lab, content=item).first()
    for f in ((row.signals or {}).get("member_fit") or []) if row else []:
        if isinstance(f, dict) and f.get("username") in members:
            fits.append(
                f"{ref_of(f['username'])}"
                + (
                    f" — {common.clip(f.get('reason', ''), 160)}"
                    if f.get("reason")
                    else ""
                )
            )
    suggested = MemberSuggestion.objects.filter(
        content=item,
        user__in=list(members.values()),
        suggested=True,
        dismissed=False,
        project__scope_lab=target_lab,
    ).select_related("user")
    for s in suggested:
        fits.append(
            f"{ref_of(s.user.username)} — already suggested to them in a lab project"
        )
    if fits:
        lines.append("Profile fit (from the nightly ranking):")
        lines += [f"- {f}" for f in fits]
    lines.append(
        "Evidence tiers: declared = their profile says so; demonstrated = their "
        "papers show it; confirmed in conversation = they told Mylo and said yes. "
        "Lab-mates are named on their declared profile only."
    )
    return Result(content="\n".join(lines), refs=refs)


_REFUSAL_FIX = {
    "unverified": "Verify your email in account settings first.",
    "no_institution": "Add and verify your institution's email in account settings.",
    "paid_plan": "Collaborator search is part of a paid plan; see account settings.",
    "daily_limit": "Try again tomorrow.",
}


def knowledge_people_beyond_lab(caller, call):
    from apps.collab import matcher

    item = _call(call)
    head = common.item_info(item)
    try:
        query = matcher.query_for_call(caller.user, item)
        if not [s for s in query.slots if s.get("facet") != "role"]:
            raise FunctionError(
                "no_slots",
                "This call's requirements have not been read yet, "
                "so there is nothing to search with.",
                "Try knowledge_people_for_call, or ask again tomorrow.",
            )
        result = matcher.search(caller.user, query)
    except matcher.SearchRefused as exc:
        raise FunctionError(
            f"search_{exc.code}",
            f"Collaborator search refused: {exc}.",
            _REFUSAL_FIX.get(
                exc.code, "Use the collaborator search in the app to see why."
            ),
        ) from exc
    groups = result.groups()
    lines = [
        f"People beyond your lab for {{ref:{head.ref}}} {common.item_title(item)} "
        "(only people open to collaboration with you; their declared profile and "
        "papers, never conversation):"
    ]
    for key, title in (
        ("fills_a_gap", "Fills a gap"),
        ("shares_expertise", "Shares your expertise"),
    ):
        rows = groups.get(key) or []
        if not rows:
            continue
        lines.append(f"{title}:")
        for r in rows:
            where = f", {r['institution']}" if r.get("institution") else ""
            why = f" — {common.clip(r['reason'], 160)}" if r.get("reason") else ""
            lines.append(
                f"- {r['name']} (@{r['username']}{where}): “{r['slot']}” "
                f"[{TIER_NAMES.get(r.get('tier'), r.get('tier'))}: {r['matched']}]"
                f"{why}"
            )
    if len(lines) == 1:
        lines.append("Nobody open to collaboration matches yet.")
    if not result.explained:
        lines.append("(Listed in retrieval order; the explanations were unavailable.)")
    lines.append(
        "To meet someone, the person uses “Who can introduce me?” in the app's "
        "collaborator search."
    )
    return Result(content="\n".join(lines), refs=[head])
