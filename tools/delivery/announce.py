"""Which opportunities a lab or department hears about, and what each post says.

The nightly path (plan "The nightly path", steps 1–4). Posting to Discord is step
5 and lives in :mod:`tools.delivery.discord_announcements`; this module decides and
records, and hands each decision to a ``poster``.

1. **Select.** A target's candidates are the grants, fellowships and conferences
   currently in one of its per-theme slates (:mod:`.slates`) that have no
   :class:`~tools.delivery.models.Announcement` for it yet. On an ordinary night that
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

from tools.delivery import announce_editor as editor
from tools.delivery import announce_facts, dept_level, usability
from tools.delivery.models import Announcement, AnnouncementSettings
from tools.recommendation.clustering import IMPLICIT_CLUSTER_ID
from tools.recommendation.models import RelevanceScore
from tools.recommendation.slates import cluster_entries, slate_depth
from tools.retrieval.liveness import is_live
from tools.retrieval.models import ContentItem

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


def enabled_departments() -> list:
    """Departments with announcements on and a plan that covers them: the ones
    the nightly run must score (registered with the recommendation tool)."""
    return [t.obj for t in enabled_targets() if t.kind == "department"]


def enabled_targets() -> list[Target]:
    """Every lab and department with announcements switched on and a plan that
    covers them."""
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
    if target.kind == "department":
        # A department hears only about calls a lab could not take on alone.
        fresh = [r for r in fresh if dept_level.reasons(r.content.metadata)]
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
    """The people whose eligibility a fellowship count reads: the lab's members, or
    the department's effective membership (direct members and its labs')."""
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.select_related("profile").order_by("username")
    if target.kind == "lab":
        return list(users.filter(lab_memberships__lab=target.obj))
    from apps.accounts.services import effective_member_ids

    return list(users.filter(id__in=effective_member_ids(target.obj)))


def align(
    target: Target, row: RelevanceScore, members: list, labs: list | None = None
) -> dict:
    """The theme, the projects and the people — facts only. For a department the
    "people" are its labs (``labs``: :func:`lab_fit.candidates`, computed once per
    run by the caller)."""
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

    if target.kind == "department":
        from tools.delivery import lab_fit

        if labs is None:
            labs = lab_fit.candidates(target.obj)
        fit = lab_fit.rank(row.content, labs)
        return {
            "cluster_id": cluster_id,
            "theme": theme,
            "theme_notes": notes,
            "projects": [],
            "people": [
                {"id": f"l{i}", "lab_id": lab["lab_id"], "name": lab["name"],
                 "why": lab["why"], "fit": lab["fit"]}
                for i, lab in enumerate(fit, start=1)
            ],
            "dept_reasons": [
                r.as_dict() for r in dept_level.reasons(row.content.metadata)
            ],
        }

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
    labs: list | None = None,
) -> Prepared:
    from dataclasses import replace

    from tools.delivery.theme_report import declared_clusters
    from tools.recommendation.cluster_fit import areas_fingerprint

    item = row.content
    meta = item.metadata or {}
    alignment = align(target, row, members, labs)
    reader = replace(
        reader,
        suited=tuple(p["name"] for p in alignment["people"]),
        suited_are_labs=target.kind == "department",
        fellowship_counts=fellowship_counts.get(str(item.id)),
    )
    checks = usability.assess(item, reader, today)
    facts = announce_facts.facts_for(item, today)
    label = label_for(item, today, seeding=seeding)
    packet = editor.Packet(
        item_id=str(item.id),
        kind=item.type,
        title=announce_facts.item_title(item),
        funder=announce_facts.item_host(item),
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
        dept_reasons=alignment.get("dept_reasons", []),
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
    return {
        "title": announce_facts.item_title(item),
        "url": announce_facts.item_url(item),
        "funder": announce_facts.item_host(item),
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
    labs = None
    if target.kind == "department":
        from tools.delivery import lab_fit

        labs = lab_fit.candidates(target.obj)
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
            labs=labs,
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
    from tools.delivery.models import SavedOpportunity

    rows = slate_rows(target, today)
    if target.kind == "department":
        rows = [r for r in rows if dept_level.reasons(r.content.metadata)]
    items = {r.content_id: r.content for r in rows}
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
    # A saved row outlives its pruned item (SET_NULL); only live items count.
    return [item for item in items.values() if item is not None]


# --------------------------------------------------------------------------- #
# The lab report's one line per kind (plan D6)
# --------------------------------------------------------------------------- #
_KIND_NOUN = {
    ContentItem.Type.GRANT: ("grant", "grants"),
    ContentItem.Type.FELLOWSHIP: ("fellowship", "fellowships"),
    ContentItem.Type.CONFERENCE: ("conference", "conferences"),
}


def announcements_live(lab) -> bool:
    """Announcements are on, switched on deployment-wide, covered by the plan, and
    routed somewhere: only then does the report hand opportunities to Discord."""
    from apps.integrations.services import resolve

    row = AnnouncementSettings.objects.filter(target_lab=lab, enabled=True).first()
    if row is None or not enabled() or not target_entitled(Target("lab", lab, row)):
        return False
    return any(
        resolve.get_route(b, purpose)
        for b in resolve.bindings_for_lab(lab)
        for purpose in ("grants", "fellowships", "conferences")
    )


def report_line(lab, on: date) -> str:
    """``## Opportunities`` with one line per kind posted ``on``, linking to the
    forum it went to (Markdown; the web shows Discord links with Discord's logo)."""
    from apps.integrations.services import resolve

    posted = Announcement.objects.filter(
        target_lab=lab, state=Announcement.State.POSTED, created_at__date=on
    )
    bindings = resolve.bindings_for_lab(lab)
    parts = []
    for kind, (one, many) in _KIND_NOUN.items():
        count = posted.filter(category=kind).count()
        if not count:
            continue
        route = next(
            (r for b in bindings if (r := resolve.get_route(b, many)) is not None),
            None,
        )
        noun = one if count == 1 else many
        where = ""
        if route is not None:
            url = f"https://discord.com/channels/{route.binding.guild.guild_id}/{route.channel_id}"
            where = f" → [#{route.channel_name or many}]({url})"
        parts.append(f"**{count} {noun}** announced{where}")
    from tools.delivery.models import AnnouncementPost

    updated = (
        AnnouncementPost.objects.filter(
            announcement__target_lab=lab, update_log__contains=[{"on": on.isoformat()}]
        )
        .values("announcement")
        .distinct()
        .count()
    )
    if updated:
        parts.append(
            f"**{updated} update{'s' if updated != 1 else ''}** to announced calls"
        )
    if not parts:
        return ""
    return "## Opportunities\n\n" + " · ".join(parts)


_OPPORTUNITY_HEADINGS = (
    "## grants",
    "## fellowships",
    "## conferences",
    "## opportunities",
)


def report_body(body: str, line: str) -> str:
    """``body`` without its grant, fellowship and conference sections (a quiet day
    carries yesterday's body forward, which may still list them), plus ``line``."""
    kept: list[str] = []
    skipping = False
    for row in (body or "").splitlines():
        if row.startswith("## "):
            skipping = row.strip().casefold().startswith(_OPPORTUNITY_HEADINGS)
        if not skipping:
            kept.append(row)
    text = "\n".join(kept).rstrip()
    return f"{text}\n\n{line}\n" if line else f"{text}\n"
