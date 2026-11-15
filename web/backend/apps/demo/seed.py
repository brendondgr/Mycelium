"""The demo lab's activity, rebuilt from its own current feed.

A visitor should not find empty Saves, Reminders, "Suggested for you" or
"Mylo & you" pages, and nothing there should be invented: every saved item,
reminder and shared paper is one the nightly ranking put in the demo people's
or the lab's feed. Rebuilt after ``demo build`` and every night (the
``demo seed`` stage), so nothing points at an item the prune has removed.

- **Saves.** The viewer saves her best paper, grant and conference that are
  still open; the lab saves its best grant and conference. "Best" is the run's
  own judgement first — a ``read`` before a ``skim`` before an unjudged or filed
  item, never a ``skip`` — then the score, so a call the model found too
  speculative is never what the demo shows off. No fellowship: she is a PI, and
  fellowships are for students and postdocs.
- **Reminders.** A lab reminder on each lab-saved call whose next deadline is
  at least three weeks away, a week and a day before it.
- **Suggested for you.** A teammate on the viewer's first project shares that
  project's best paper (by the same judgement); delivery's fan-out decides
  whether it fits the viewer.
- **Mylo & you.** One open question, about a topic from a project she is on
  that her own profile does not name, with the number of papers in her feed
  about it; and the project status the world file set, as a change.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.research import visibility

from . import world as demo_world
from .models import DemoWorld

#: A lab reminder needs room before the deadline, so that it is still upcoming
#: for a visitor and the first offset is not already past.
REMINDER_LEAD = timedelta(days=21)
OFFSETS = [(1, "week"), (1, "day")]
SHARE_TRIES = 8


def seed(built: DemoWorld, *, log=print) -> dict:
    from tools._framework import services

    delivery = services.get("delivery")
    if delivery is None:
        log("  The delivery tool is not loaded: no activity.")
        return {}
    viewer, lab = built.viewer, built.lab
    people = list(
        get_user_model().objects.filter(email__iendswith="@" + demo_world.DOMAIN)
    )
    # Every project of the fictional lab, through the one door for project scope.
    projects = list(visibility.lab_projects(lab).order_by("name"))
    today = timezone.localdate()
    delivery.clear_activity(users=people, labs=[lab], projects=projects)

    out = {"saves": 0, "lab_saves": 0, "reminders": 0, "suggested": 0}
    for kind in ("paper", "grant", "conference"):
        item = _best(viewer.relevance_scores, kind, today)
        if item is not None:
            delivery.save_item(viewer, item)
            out["saves"] += 1
    # A teammate saves to the lab: the app lists everything a person saved on
    # their own Saves page, so lab saves by the viewer would show twice there.
    mine = [p for p in projects if p.members.filter(pk=viewer.pk).exists()]
    saver = _teammate(mine or projects, viewer) or viewer
    for kind in ("grant", "conference"):
        item = _best(lab.relevance_scores, kind, today, lead=REMINDER_LEAD)
        if item is None:
            continue
        delivery.save_item(saver, item, target_lab=lab)
        out["lab_saves"] += 1
        if _remind(delivery, lab, item, today):
            out["reminders"] += 1

    if mine:
        out["suggested"] = _share(delivery, mine[0], viewer)
    out["mylo"] = _understanding(viewer, mine)
    log(
        "  {saves} personal save(s), {lab_saves} lab save(s), {reminders} "
        "reminder(s), {suggested} suggestion(s), {mylo} Mylo question(s)".format(**out)
    )
    return out


def _open(item, today, lead=timedelta(0)) -> bool:
    """Papers never close; a call counts only with a next deadline far enough off."""
    if item.type == "paper":
        return True
    return item.deadline_rows.filter(
        is_next=True, due_date__gte=today + max(lead, timedelta(days=1))
    ).exists()


#: The run's verdicts, best first; anything else (unjudged, ``file``) after them.
FIT_ORDER = {"read": 0, "skim": 1}
POOL = 200


def _by_fit(scores, kind):
    """A target's suggested rows of one kind, best judged fit first; skips out."""
    rows = [
        s
        for s in scores.filter(content__type=kind).select_related("content")[:POOL]
        if (s.signals or {}).get("suggested", True)
        and (s.signals or {}).get("verdict") != "skip"
    ]
    rows.sort(key=lambda s: (FIT_ORDER.get(s.signals.get("verdict"), 2), -s.score))
    return rows


def _best(scores, kind, today, lead=timedelta(0)):
    for score in _by_fit(scores, kind):
        if _open(score.content, today, lead):
            return score.content
    return None


def _remind(delivery, lab, item, today) -> bool:
    deadline = (
        item.deadline_rows.filter(is_next=True, due_date__gte=today + REMINDER_LEAD)
        .order_by("due_date")
        .first()
    )
    if deadline is None:
        return False
    meta = item.metadata or {}
    delivery.create_or_update_subscription(
        deadline_kind=deadline.kind,
        deadline_round_key=deadline.round_key,
        round_label=deadline.round_label,
        area=item.type,
        title=meta.get("title") or meta.get("name") or "Untitled",
        url=meta.get("website") or item.source_url or "",
        due_date=deadline.due_date,
        offsets=OFFSETS,
        target_lab=lab,
        content=item,
        created_by=None,  # a user here would be checked for Discord access
    )
    return True


def _teammate(projects, viewer):
    for project in projects:
        other = project.members.exclude(pk=viewer.pk).order_by("username").first()
        if other is not None:
            return other
    return None


#: Not research papers a teammate would pass on: discussion comments, replies,
#: corrections.
NOT_A_PAPER = re.compile(
    r"^\s*(comment on|reply to|response to|review of|correction|corrigendum|"
    r"erratum|retraction)\b",
    re.I,
)


def _share(delivery, project, viewer) -> int:
    """A teammate shares the project's best paper that the fan-out finds fits
    the viewer; a paper below the fit floor is passed over, as it would be."""
    sharer = _teammate([project], viewer)
    if sharer is None:
        return 0
    tried = 0
    for score in _by_fit(project.relevance_scores, "paper")[: SHARE_TRIES * 4]:
        title = (score.content.metadata or {}).get("title") or ""
        if NOT_A_PAPER.match(title):
            continue
        tried += 1
        if tried > SHARE_TRIES:
            break
        delivery.share_to_project(project, score.content, sharer)
        if viewer.member_suggestions.filter(
            content=score.content, suggested=True
        ).exists():
            return 1
    return 0


def _understanding(viewer, projects) -> int:
    """One open question from the viewer's feed, and the status change."""
    profile = getattr(viewer, "profile", None)
    interests = (getattr(profile, "interests", None) or {}) if profile else {}
    own = {
        str(a).lower()
        for a in [
            *(getattr(profile, "areas", None) or []),
            *(interests.get("areas") or []),
            *(a for c in interests.get("clusters") or [] for a in c.get("areas", [])),
        ]
    }
    papers = [
        ((s.content.metadata or {}).get("title") or "").lower()
        for s in viewer.relevance_scores.filter(content__type="paper")
        .select_related("content")[:200]
    ]
    # The topic, from a project she is on, with the most papers in her feed.
    best = None
    for project in projects:
        for area in (project.goals or {}).get("interests", {}).get("areas", []):
            if area.lower() in own:
                continue
            # Only the words her own areas do not already use ("litter", not
            # "marine"), all of them in the title.
            words = [
                w
                for w in re.findall(r"[a-z]{5,}", area.lower())
                if not any(w in mine for mine in own)
            ]
            if not words:
                continue
            count = sum(1 for title in papers if all(w in title for w in words))
            if count and (best is None or count > best[0]):
                best = (count, area, project)
    questions = []
    if best is not None:
        count, area, project = best
        papers_word = (
            "paper in your feed is" if count == 1 else "papers in your feed are"
        )
        questions.append(
            {
                "kind": "interest",
                "topic": area,
                "project": str(project.pk),
                "explanation": (
                    f"{count} {papers_word} about {area}, which {project.name} "
                    "works on but your own profile does not name. Should Mylo "
                    "treat it as yours too?"
                ),
                "choices": [
                    {"key": "reports", "label": "Include it in my reports"},
                    {"key": "interests", "label": "Add it to my interests"},
                    {
                        "key": f"project:{project.pk}",
                        "label": f"It's for {project.name}, not me",
                    },
                ],
            }
        )
    changes = [
        {
            "kind": "state_edit",
            "topic": project.name,
            "project": str(project.pk),
            "field": "status",
            "new_value": (project.goals or {}).get("status"),
            "explanation": f"{project.name}'s status was updated.",
            "visibility": "lab",
        }
        for project in projects
        if (project.goals or {}).get("status")
    ]
    call_command(
        "seed_understanding",
        json.dumps(
            {"user": viewer.username, "questions": questions, "changes": changes}
        ),
        stdout=_Quiet(),
    )
    return len(questions)


class _Quiet:
    def write(self, *_args, **_kwargs) -> None:
        pass

    def flush(self) -> None:
        pass
