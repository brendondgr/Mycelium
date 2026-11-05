"""Which opportunities a lab or department hears about, and what each post says.

The nightly path (plan "The nightly path", steps 1–4). Posting to Discord is step
5 and lives in :mod:`apps.content.discord_announcements`; this module decides and
records, and hands each decision to a ``poster``.

1. **Select.** A target's candidates are the grants, fellowships and conferences
   currently in one of its per-theme slates (:mod:`.slates`) that have no
   :class:`~apps.content.models.Announcement` for it yet. On an ordinary night that
   is exactly the night's entrants; after a missed night it catches up. Nothing is
   ever announced to the same target twice.

   **The first run for a target** announces only its ``activation_seed`` best open
   items (default six), interleaving kinds by slate position so one kind cannot
   take every place, labelled *Already open*. Everything else already in its slates
   is recorded as ``seeded_seen`` and never announced later.
2. **Check usability** (:mod:`.usability`). A ``block`` holds the item back with
   its reason ("Mylo held back").
3. **Align** — the theme it entered, the projects it touches, and who it suits.
4. **Edit** (:mod:`.announce_editor`) — the bounded editor, its verifier, and the
   template fallback.

``daily_cap = -1`` means no limit; with a cap, the rest wait for the next night.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.content import announce_editor as editor
from apps.content import announce_facts, usability
from apps.content.clustering import IMPLICIT_CLUSTER_ID
from apps.content.liveness import is_live
from apps.content.models import (
    Announcement,
    AnnouncementSettings,
    ContentItem,
    RelevanceScore,
)
from apps.content.slates import cluster_entries, slate_depth

KIND_ORDER = (
    ContentItem.Type.GRANT,
    ContentItem.Type.FELLOWSHIP,
    ContentItem.Type.CONFERENCE,
)
#: An item first posted by its source this recently is a *New call*.
NEW_CALL_DAYS = 14
#: How many people a post names under *Who should look*.
PEOPLE_SHOWN = 3


def enabled() -> bool:
    """The deployment-wide switch (default off) every phase ships behind."""
    return bool(getattr(settings, "OPPORTUNITY_ANNOUNCEMENTS_ENABLED", False))


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #
@dataclass
class Target:
    kind: str  # "lab" | "department"
    obj: object
    settings: AnnouncementSettings

    @property
    def key(self) -> str:
        return getattr(self.obj, "slug", "") or str(self.obj.pk)

    @property
    def name(self) -> str:
        return self.obj.name

    @property
    def persist_kwargs(self) -> dict:
        return (
            {"target_lab": self.obj}
            if self.kind == "lab"
            else {"target_department": self.obj}
        )

    @property
    def announcement_filter(self) -> dict:
        return (
            {"target_lab": self.obj}
            if self.kind == "lab"
            else {"target_department": self.obj}
        )

    def kinds(self) -> list[str]:
        s = self.settings
        wanted = {
            ContentItem.Type.GRANT: s.grants,
            ContentItem.Type.FELLOWSHIP: s.fellowships,
            ContentItem.Type.CONFERENCE: s.conferences,
        }
        return [k for k in KIND_ORDER if wanted[k]]


def target_entitled(target: Target) -> bool:
    from apps.billing.entitlements import (
        Feature,
        department_has_feature,
        lab_has_feature,
    )

    check = lab_has_feature if target.kind == "lab" else department_has_feature
    return check(target.obj, Feature.OPPORTUNITY_ANNOUNCEMENTS) and check(
        target.obj, Feature.BOT_SERVER
    )


def enabled_targets() -> list[Target]:
    """Every lab (and, once supported, department) with announcements switched on
    and a plan that covers them."""
    out = []
    rows = AnnouncementSettings.objects.filter(enabled=True).select_related(
        "target_lab__profile", "target_department__profile"
    )
    for row in rows:
        if row.target_lab_id:
            target = Target("lab", row.target_lab, row)
        else:
            target = Target("department", row.target_department, row)
        if target_entitled(target):
            out.append(target)
    return out


# --------------------------------------------------------------------------- #
# Step 1 — select
# --------------------------------------------------------------------------- #
def best_slot(signals: dict | None) -> tuple[int, str, str]:
    """``(rank, cluster_id, label)`` of the row's best theme slate position."""
    best = (10**6, "", "")
    for cluster_id, entry in cluster_entries(signals).items():
        rank = entry.get("rank") if isinstance(entry, dict) else None
        if isinstance(rank, int) and rank < best[0]:
            best = (rank, cluster_id, str(entry.get("label") or ""))
    if best[1] == "" and isinstance((signals or {}).get("top_rank"), int):
        return (signals["top_rank"], "", "")
    return best


def in_slate(row: RelevanceScore) -> bool:
    """In one of the target's theme slates — or, for a kind still ranked on the
    single legacy list (fellowships), within that kind's slate depth of it."""
    if cluster_entries(row.signals):
        return best_slot(row.signals)[0] < 10**6
    rank = (row.signals or {}).get("top_rank")
    return isinstance(rank, int) and rank <= slate_depth(row.content.type)


def slate_rows(target: Target, today: date) -> list[RelevanceScore]:
    """The target's opportunities currently in a theme slate, best position first."""
    rows = (
        RelevanceScore.objects.filter(
            **target.persist_kwargs, content__type__in=target.kinds()
        )
        .select_related("content")
        .order_by("id")
    )
    iso = today.isoformat()
    out = [
        r
        for r in rows
        if in_slate(r) and is_live(r.content.type, r.content.metadata, iso)
    ]
    out.sort(key=lambda r: (best_slot(r.signals)[0], -r.score, str(r.content_id)))
    return out


def interleave(rows: list[RelevanceScore], n: int) -> list[RelevanceScore]:
    """Up to ``n`` rows, taking kinds in turn by slate position, so one kind can't
    fill every place."""
    queues = {k: [r for r in rows if r.content.type == k] for k in KIND_ORDER}
    picked: list[RelevanceScore] = []
    while len(picked) < n and any(queues.values()):
        for kind in KIND_ORDER:
            if queues[kind] and len(picked) < n:
                picked.append(queues[kind].pop(0))
    return picked


@dataclass
class Selection:
    seeding: bool
    chosen: list[RelevanceScore]
    passed_over: list[RelevanceScore] = field(default_factory=list)
    waiting: list[RelevanceScore] = field(default_factory=list)  # over the cap


def select(
    target: Target,
    today: date,
    usable: Callable[[RelevanceScore], bool],
) -> Selection:
    """``usable(row)`` says whether a row would survive the checks; the seed spends
    its places only on rows that would."""
    rows = slate_rows(target, today)
    announced = set(
        Announcement.objects.filter(
            **target.announcement_filter, content__isnull=False
        ).values_list("content_id", flat=True)
    )
    fresh = [r for r in rows if r.content_id not in announced]
    if target.settings.seeded_at is None:
        # A seed slot spent on a closed, too-late or ineligible call is a slot
        # wasted, so the seed takes the best rows that would actually be posted.
        open_rows = [r for r in fresh if usable(r)]
        chosen = interleave(open_rows, target.settings.activation_seed)
        chosen_ids = {r.content_id for r in chosen}
        return Selection(
            True,
            chosen,
            passed_over=[r for r in fresh if r.content_id not in chosen_ids],
        )
    cap = target.settings.daily_cap
    if cap is None or cap < 0:
        return Selection(False, fresh)
    return Selection(False, fresh[:cap], waiting=fresh[cap:])


# --------------------------------------------------------------------------- #
# Steps 2–4 — check, align, edit
# --------------------------------------------------------------------------- #
@dataclass
class Prepared:
    row: RelevanceScore
    label: str
    checks: list[usability.Check]
    alignment: dict
    packet: editor.Packet
    write_up: editor.WriteUp
    write_up_key: str
    editor_note: str
    facts: dict

    @property
    def held(self) -> usability.Check | None:
        return usability.blocking(self.checks)

    @property
    def item(self) -> ContentItem:
        return self.row.content


def label_for(item: ContentItem, today: date, *, seeding: bool) -> str:
    if seeding:
        return Announcement.Label.ALREADY_OPEN
    meta = item.metadata or {}
    posted = str(meta.get("published_on") or meta.get("first_seen") or "")[:10]
    try:
        if posted and (today - date.fromisoformat(posted)).days <= NEW_CALL_DAYS:
            return Announcement.Label.NEW_CALL
    except ValueError:
        pass
    return Announcement.Label.NEWLY_RELEVANT


def _members(target: Target) -> list:
    if target.kind != "lab":
        return []
    from django.contrib.auth import get_user_model

    return list(
        get_user_model()
        .objects.filter(lab_memberships__lab=target.obj)
        .select_related("profile")
        .order_by("username")
    )


def align(target: Target, row: RelevanceScore, members: list) -> dict:
    """The theme, the projects and the people — facts only."""
    from apps.core.people import display_name

    _rank, cluster_id, theme = best_slot(row.signals)
    if cluster_id in ("", IMPLICIT_CLUSTER_ID):
        theme = ""  # the implicit grouping is not a theme anyone named
    notes = []
    writeup = ((row.signals or {}).get("writeups") or {}).get(cluster_id) or {}
    for beat in (writeup.get("beats") or [])[:2]:
        if isinstance(beat, str) and beat.strip():
            notes.append(beat.strip())

    projects: list[str] = []
    if target.kind == "lab":
        project_rows = RelevanceScore.objects.filter(
            target_project__scope_lab=target.obj, content_id=row.content_id
        ).select_related("target_project")
        projects = sorted(
            {
                pr.target_project.name
                for pr in project_rows
                if (pr.signals or {}).get("suggested") and pr.target_project
            }
        )[:3]

    by_username = {m.get_username(): m for m in members}
    people = []
    for entry in (row.signals or {}).get("member_fit") or []:
        user = by_username.get(entry.get("username"))
        if user is None:
            continue
        people.append(
            {
                "id": f"p{len(people) + 1}",
                "username": user.get_username(),
                "user_id": user.id,
                "name": display_name(user),
                "why": _reason(entry),
                "fit": entry.get("fit"),
            }
        )
        if len(people) >= PEOPLE_SHOWN:
            break
    return {
        "cluster_id": cluster_id,
        "theme": theme,
        "theme_notes": notes,
        "projects": projects,
        "people": people,
    }


_PERCENT = re.compile(r"\s*\([^)]*\d\s*%[^)]*\)|\s*\d+(?:\.\d+)?\s*%[^.,;]*")


def _reason(entry: dict) -> str:
    """A member-fit reason fit to post: no percentages, ever (plan, Discord
    surfaces). The deterministic fallback line is mostly a percentage, so what is
    left of it is replaced with a plain statement."""
    text = " ".join(str(entry.get("reason") or "").split())
    text = _PERCENT.sub("", text).strip(" .;,")
    if not text or entry.get("source") not in (None, "llm"):
        return "Closest match to their research profile"
    return text[:200]


def _summary(meta: dict) -> str:
    ai = meta.get("ai_fields") or {}
    return str(
        ai.get("summary") or meta.get("ai_summary") or meta.get("blurb") or ""
    ).strip()


def _next_step_hint(checks: list[usability.Check], due: str, buffer_days: int | None):
    if not due or buffer_days is None:
        return ""
    decide = date.fromisoformat(due) - timedelta(days=buffer_days)
    return (
        f"Decide by **{decide:%a}, {decide:%b} {decide.day}** whether to apply. "
        f"That keeps your {buffer_days}-day buffer."
    )


def prepare(
    target: Target,
    row: RelevanceScore,
    today: date,
    *,
    seeding: bool,
    reader: usability.Reader,
    members: list,
    fellowship_counts: dict,
    complete: Callable[[str], str | None] | None,
) -> Prepared:
    from dataclasses import replace

    from apps.content.cluster_fit import areas_fingerprint
    from apps.content.theme_report import declared_clusters

    item = row.content
    meta = item.metadata or {}
    alignment = align(target, row, members)
    reader = replace(
        reader,
        suited=tuple(p["name"] for p in alignment["people"])
        if target.kind == "lab"
        else None,
        fellowship_counts=fellowship_counts.get(str(item.id)),
    )
    checks = usability.assess(item, reader, today)
    facts = announce_facts.facts_for(item, today)
    label = label_for(item, today, seeding=seeding)
    packet = editor.Packet(
        item_id=str(item.id),
        kind=item.type,
        title=meta.get("title") or "Untitled",
        funder=meta.get("funder") or meta.get("sponsor") or meta.get("venue") or "",
        summary=_summary(meta),
        target_name=target.name,
        target_kind=target.kind,
        label=Announcement.Label(label).label,
        theme=alignment["theme"],
        theme_notes=alignment["theme_notes"],
        projects=alignment["projects"],
        people=[
            {"id": p["id"], "name": p["name"], "why": p["why"]}
            for p in alignment["people"]
        ],
        checks=[c.as_dict() for c in checks],
        next_step_hint=_next_step_hint(checks, facts["deadline"], reader.buffer_days),
    )
    interests = getattr(getattr(target.obj, "profile", None), "interests", None) or {}
    areas = next(
        (
            c.areas
            for c in declared_clusters(interests)
            if c.id == alignment["cluster_id"]
        ),
        [],
    )
    key = editor.write_up_key(
        packet,
        target_key=f"{target.kind}:{target.key}",
        areas_fp=areas_fingerprint(areas),
        text_fp=str(meta.get("search_text_hash") or ""),
    )
    existing = Announcement.objects.filter(
        **target.announcement_filter, content=item, write_up_key=key
    ).first()
    if existing and existing.write_up:
        write_up, note = editor.WriteUp.from_dict(existing.write_up), "reused"
    elif usability.blocking(checks) is not None:
        write_up, note = editor.template(packet), "held back, model not called"
    else:
        write_up, note = editor.edit(packet, complete=complete)
    return Prepared(
        row=row,
        label=label,
        checks=checks,
        alignment=alignment,
        packet=packet,
        write_up=write_up,
        write_up_key=key,
        editor_note=note,
        facts=facts,
    )


# --------------------------------------------------------------------------- #
# Running one target
# --------------------------------------------------------------------------- #
@dataclass
class Outcome:
    target: Target
    seeding: bool
    posted: list[Prepared] = field(default_factory=list)
    held: list[Prepared] = field(default_factory=list)
    skipped: list[Prepared] = field(default_factory=list)
    passed_over: int = 0
    waiting: int = 0


def snapshot(item: ContentItem) -> dict:
    meta = item.metadata or {}
    return {
        "title": meta.get("title") or "Untitled",
        "url": item.source_url or meta.get("external_url") or meta.get("website") or "",
        "funder": meta.get("funder") or meta.get("sponsor") or meta.get("venue") or "",
    }


def run_target(
    target: Target,
    today: date,
    *,
    dry_run: bool,
    complete: Callable[[str], str | None] | None,
    poster: Callable[[Announcement], object] | None = None,
) -> Outcome:
    """Decide every candidate for ``target`` and, unless ``dry_run``, record each
    decision and hand posts to ``poster``."""
    reader = (
        usability.reader_for_lab(target.obj, min_award=_min_award(target))
        if target.kind == "lab"
        else usability.reader_for_department(target.obj, min_award=_min_award(target))
    )
    members = _members(target)
    counts = usability.fellowship_counts(
        [m.id for m in members],
        [
            r.content
            for r in slate_rows(target, today)
            if r.content.type == ContentItem.Type.FELLOWSHIP
        ],
        today,
    )

    def usable(row: RelevanceScore) -> bool:
        from dataclasses import replace

        checked = replace(reader, fellowship_counts=counts.get(str(row.content_id)))
        checks = usability.assess(row.content, checked, today)
        return usability.blocking(checks) is None

    selection = select(target, today, usable)
    outcome = Outcome(
        target,
        selection.seeding,
        passed_over=len(selection.passed_over),
        waiting=len(selection.waiting),
    )
    for row in selection.chosen:
        prepared = prepare(
            target,
            row,
            today,
            seeding=selection.seeding,
            reader=reader,
            members=members,
            fellowship_counts=counts,
            complete=complete,
        )
        if prepared.held is not None:
            outcome.held.append(prepared)
        elif not prepared.write_up.announce:
            outcome.skipped.append(prepared)
        else:
            outcome.posted.append(prepared)

    if dry_run:
        return outcome

    with transaction.atomic():
        for prepared in outcome.held:
            if _waits(prepared):
                continue  # announced the night it gains a submission deadline
            _record(target, prepared, Announcement.State.SKIPPED, prepared.held.label)
        for prepared in outcome.skipped:
            _record(
                target,
                prepared,
                Announcement.State.SKIPPED,
                f"Mylo: {prepared.write_up.skip_reason}",
            )
        posted = [
            _record(target, prepared, Announcement.State.POSTED, "")
            for prepared in outcome.posted
        ]
        for row in selection.passed_over:
            Announcement.objects.get_or_create(
                **target.announcement_filter,
                content=row.content,
                defaults={
                    "category": row.content.type,
                    "state": Announcement.State.SEEDED_SEEN,
                    "snapshot": snapshot(row.content),
                },
            )
        if selection.seeding:
            target.settings.seeded_at = timezone.now()
            target.settings.save(update_fields=["seeded_at", "updated_at"])
    if poster is not None:
        for announcement in posted:
            poster(announcement)
    return outcome


def _waits(prepared: Prepared) -> bool:
    """A conference with no submission deadline yet is not held back for good: it
    stays unrecorded, so the night its dates are published it is a candidate."""
    held = prepared.held
    return (
        prepared.item.type == ContentItem.Type.CONFERENCE
        and held is not None
        and held.key == "deadline"
        and held.label == usability.NO_SUBMISSION_DEADLINE
    )


def _min_award(target: Target) -> float | None:
    value = target.settings.min_award
    return float(value) if value is not None else None


def _record(
    target: Target, prepared: Prepared, state: str, reason: str
) -> Announcement:
    item = prepared.item
    announcement, _ = Announcement.objects.update_or_create(
        **target.announcement_filter,
        content=item,
        defaults={
            "category": item.type,
            "state": state,
            "label": prepared.label,
            "skip_reason": reason[:300],
            "snapshot": snapshot(item),
            "checks": [c.as_dict() for c in prepared.checks],
            "alignment": prepared.alignment,
            "write_up": prepared.write_up.as_dict(),
            "write_up_key": prepared.write_up_key,
            "facts": prepared.facts,
            "facts_fingerprint": announce_facts.fingerprint(prepared.facts),
        },
    )
    return announcement


def run(
    today: date | None = None,
    *,
    dry_run: bool = False,
    complete: Callable[[str], str | None] | None = editor._model_complete,
    poster: Callable[[Announcement], object] | None = None,
    targets: Iterable[Target] | None = None,
) -> list[Outcome]:
    today = today or timezone.localdate()
    return [
        run_target(t, today, dry_run=dry_run, complete=complete, poster=poster)
        for t in (enabled_targets() if targets is None else targets)
    ]


# --------------------------------------------------------------------------- #
# The closing-soon list's inputs
# --------------------------------------------------------------------------- #
def list_items(target: Target, today: date) -> list[ContentItem]:
    """Everything on the target's list: its slates, its announced items, and what
    its members saved for it."""
    from apps.content.models import SavedOpportunity

    items = {r.content_id: r.content for r in slate_rows(target, today)}
    for ann in Announcement.objects.filter(
        **target.announcement_filter,
        state=Announcement.State.POSTED,
        content__isnull=False,
    ).select_related("content"):
        items.setdefault(ann.content_id, ann.content)
    if target.kind == "lab":
        for saved in SavedOpportunity.objects.filter(
            target_lab=target.obj
        ).select_related("content"):
            items.setdefault(saved.content_id, saved.content)
    return list(items.values())
