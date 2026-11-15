"""``/mylo populate``: fill a server's opportunity forums with the best open items.

The activation seed posts six items across all three kinds and records the rest of
the slates as passed over, so a freshly set-up server has two or three threads per
forum. A manager who wants more asks for them: this fills each forum this binding
routes (one per kind for a lab, the one shared forum for a department) so that it
carries the target's ``count`` best open items of that kind.

Walking a kind's slate best position first:

* an item already posted here with a live thread **counts** toward ``count`` — so
  running it twice posts nothing new, and asking for more later tops up;
* an item Mylo held back, or whose thread someone deleted by hand, is skipped —
  that was a decision, and populating is not a way round it;
* anything else (never announced, or passed over at activation) goes through the
  same checks, alignment and editor as a nightly post, labelled *Already open*.
  If the editor judges it not worth a post it is recorded as skipped and the walk
  moves on.

The model is called at most ``2 × count`` times per kind, so a weak slate cannot
turn one command into an unbounded bill. Every post is recorded with origin
*manual* and the manager who asked. Populating needs announcements switched on and
seeded first (``/setup``): the seed is what marks the rest of the slate as seen, and
without it the next nightly run would announce the whole backlog again.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from tools.delivery import announce, discord_announcements, usability
from tools.delivery import announce_editor as editor
from tools.delivery.models import Announcement, AnnouncementPost
from tools.retrieval.models import ContentItem

MAX_COUNT = 10
DEFAULT_COUNT = 5


@dataclass
class KindResult:
    kind: str
    already: int = 0
    posted: list[str] = field(default_factory=list)  # titles
    skipped: int = 0
    no_route: bool = False

    @property
    def total(self) -> int:
        return self.already + len(self.posted)


def populate(
    binding, count: int = DEFAULT_COUNT, *, actor=None, complete="default"
) -> tuple[str, dict]:
    """Fill this binding's forums. ``(status, payload)`` with a ``message`` the bot
    shows as is; the caller has already run the gate."""
    from tools.delivery.announcement_setup import settings_for_binding

    count = max(1, min(MAX_COUNT, int(count or DEFAULT_COUNT)))
    if not announce.enabled():
        return "switched_off", {
            "message": "Opportunity announcements aren't switched on for this "
            "Mycelium instance, so there is nothing to post."
        }
    row = settings_for_binding(binding)
    if not row.enabled or row.seeded_at is None:
        return "not_on", {
            "message": "Turn announcements on first: `/setup` → **Opportunity "
            "announcements…** → **Turn on**. Then run `/mylo populate` to add more."
        }
    target = announce.Target(binding.target_kind, binding.target, row)
    if not announce.target_entitled(target):
        return "not_entitled", {
            "message": "This plan doesn't include opportunity announcements."
        }
    if complete == "default":
        complete = editor._model_complete

    today = timezone.localdate()
    rows = announce.slate_rows(target, today)
    members = announce._members(target)
    labs = None
    if target.kind == "department":
        from tools.delivery import lab_fit

        labs = lab_fit.candidates(target.obj)
    reader = (
        usability.reader_for_lab(target.obj, min_award=announce._min_award(target))
        if target.kind == "lab"
        else usability.reader_for_department(
            target.obj, min_award=announce._min_award(target)
        )
    )
    counts = usability.fellowship_counts(
        [m.id for m in members],
        [r.content for r in rows if r.content.type == ContentItem.Type.FELLOWSHIP],
        today,
    )
    existing = {
        a.content_id: a
        for a in Announcement.objects.filter(
            **target.announcement_filter, content__isnull=False
        )
    }
    results = []
    for kind in target.kinds():
        result = KindResult(kind)
        results.append(result)
        if discord_announcements.route_for(binding, kind) is None:
            result.no_route = True
            continue
        attempts = 0
        for score in (r for r in rows if r.content.type == kind):
            if result.total >= count or attempts >= 2 * count:
                break
            ann = existing.get(score.content_id)
            if ann is not None and ann.state == Announcement.State.POSTED:
                post = AnnouncementPost.objects.filter(
                    announcement=ann, binding=binding
                ).first()
                if post is None:
                    # Posted to another server of this target, never here.
                    discord_announcements.post(ann, drain=False, bindings=[binding])
                    result.posted.append(ann.snapshot.get("title") or "")
                elif post.deleted_at is None:
                    result.already += 1
                continue
            if ann is not None and ann.state != Announcement.State.SEEDED_SEEN:
                continue  # held back, or closed: a decision populating keeps
            attempts += 1
            prepared = announce.prepare(
                target,
                score,
                today,
                seeding=True,
                reader=reader,
                members=members,
                fellowship_counts=counts,
                complete=complete,
                labs=labs,
            )
            if prepared.held is not None:
                if not announce._waits(prepared):
                    announce._record(
                        target,
                        prepared,
                        Announcement.State.SKIPPED,
                        prepared.held.label,
                    )
                result.skipped += 1
                continue
            if not prepared.write_up.announce:
                announce._record(
                    target,
                    prepared,
                    Announcement.State.SKIPPED,
                    f"Mylo: {prepared.write_up.skip_reason}",
                )
                result.skipped += 1
                continue
            ann = announce._record(target, prepared, Announcement.State.POSTED, "")
            ann.origin = Announcement.Origin.MANUAL
            ann.created_by = actor
            ann.save(update_fields=["origin", "created_by", "updated_at"])
            discord_announcements.post(ann, drain=False, bindings=[binding])
            result.posted.append(ann.snapshot.get("title") or "")
    discord_announcements.flush()
    _audit(binding, actor, count, results)
    return "ok", {
        "message": summary(results, count),
        "results": [
            {
                "kind": r.kind,
                "already": r.already,
                "posted": len(r.posted),
                "skipped": r.skipped,
                "no_route": r.no_route,
            }
            for r in results
        ],
    }


def summary(results: list[KindResult], count: int) -> str:
    lines = []
    for r in results:
        noun = discord_announcements.KINDS[r.kind][0].lower() + "s"
        if r.no_route:
            lines.append(f"• **{noun.title()}:** no forum set up here.")
            continue
        bits = [f"posted **{len(r.posted)}**"]
        if r.already:
            bits.append(f"{r.already} already here")
        line = f"• **{noun.title()}:** " + ", ".join(bits)
        if r.total < count:
            line += f" — that's every open one Mylo would post (asked for {count})"
        lines.append(line + ".")
    if not lines:
        return "This server's announcements carry no kinds. Choose some in `/setup`."
    posted = any(r.posted for r in results)
    return (
        "📣 "
        + ("Done.\n" if posted else "Nothing new to post.\n")
        + "\n".join(lines)
        # Discord takes a forum's threads a few at a time (the outbox paces them).
        + ("\nThey appear a few a minute, so give it a moment." if posted else "")
    )


def _audit(binding, actor, count: int, results: list[KindResult]) -> None:
    from apps.integrations.services import audit

    audit.discord_audit(
        action="announcements.populated",
        actor=actor,
        guild_id=binding.guild.guild_id,
        metadata={
            "binding_id": binding.id,
            "count": count,
            "posted": {r.kind: len(r.posted) for r in results},
        },
    )
