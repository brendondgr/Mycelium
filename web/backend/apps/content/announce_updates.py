"""What changed overnight for things already announced (plan D9, D11).

``announce_opportunity_updates`` runs after ``announce_opportunities`` and plans
three kinds of work for each target; :mod:`.discord_announcements` carries them out.

* **Changed calls.** A posted announcement whose facts differ from the snapshot its
  post showed (:mod:`.announce_facts`). Its existing thread is updated in place:
  opening post edited, renamed ``[🚨 Update <Mon D>]``, tagged *Updated*, and a
  reply tags whoever is following it. At most one update per thread per night.
* **Closed calls.** A posted announcement whose last deadline has passed, or whose
  item was pruned, is archived and tagged *Closed*.
* **Closing soon.** Grants and fellowships on the target's list closing within
  fourteen days, one list per kind, replacing yesterday's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from apps.content import announce_facts
from apps.content.announce import Target, list_items
from apps.content.models import Announcement, ContentItem


@dataclass
class Changed:
    announcement: Announcement
    changes: list[announce_facts.Change]
    facts: dict


@dataclass
class UpdatePlan:
    target: Target
    changed: list[Changed] = field(default_factory=list)
    to_close: list[Announcement] = field(default_factory=list)
    closing_soon: dict[str, list[announce_facts.ClosingSoon]] = field(
        default_factory=dict
    )


def plan(target: Target, today: date) -> UpdatePlan:
    out = UpdatePlan(target)
    posted = Announcement.objects.filter(
        **target.announcement_filter, state=Announcement.State.POSTED
    ).select_related("content")
    for ann in posted:
        if ann.content is None:
            out.to_close.append(ann)
            continue
        facts = announce_facts.facts_for(ann.content, today)
        if _finished(facts, today):
            out.to_close.append(ann)
            continue
        found = announce_facts.changes(ann.facts, facts)
        if found:
            out.changed.append(Changed(ann, found, facts))
    if target.settings.closing_soon_list:
        rows = announce_facts.closing_soon(list_items(target, today), today)
        for kind in (ContentItem.Type.GRANT, ContentItem.Type.FELLOWSHIP):
            if kind not in target.kinds():
                continue
            wanted = [r for r in rows if r.kind == kind]
            if wanted:
                out.closing_soon[kind] = wanted
    return out


def _finished(facts: dict, today: date) -> bool:
    """No future round left, though the post once showed one."""
    if facts.get("deadline"):
        return False
    rounds = facts.get("rounds") or []
    return bool(rounds) and max(rounds) < today.isoformat()


def record_update(changed: Changed) -> None:
    """Store the new facts as what the post now shows."""
    ann = changed.announcement
    ann.facts = changed.facts
    ann.facts_fingerprint = announce_facts.fingerprint(changed.facts)
    ann.save(update_fields=["facts", "facts_fingerprint", "updated_at"])


def record_closed(ann: Announcement, when) -> None:
    ann.state = Announcement.State.CLOSED
    ann.closed_at = when
    ann.save(update_fields=["state", "closed_at", "updated_at"])
