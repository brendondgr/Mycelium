"""The lab's daily digest, posted to the channel it already configured.

A lab binds an updates channel in ``/setup``, sees a success confirmation, and — until
now — waits forever. Nothing ever posted there. This is the missing send.

Three things it deliberately is not:

* **Not the PDF report.** This lands in a shared channel people scroll past, not a
  document someone sat down to read. Counts by theme, the day's best few items, and a
  link into the portal for everything else.
* **Not a second source of truth.** It reads the same ``RelevanceScore`` rows the
  lab's feed and briefing read, so the channel post cannot drift from what the portal
  shows.
* **Not a ping.** ``allowed_mentions.parse`` stays empty and no member is tagged. It
  is an update, not a summons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.utils import timezone

from apps.content.briefing import LAB_BRIEFING_CATEGORIES, _suggested_scores
from apps.content.models import ContentItem, DailyBriefing
from apps.integrations.services import outbox, resolve

#: Themes shown before the post stops being scannable. Matches the cluster ceiling.
MAX_THEMES = 8
#: Items named per theme. Enough to be useful, few enough to skim.
ITEMS_PER_THEME = 3

_CATEGORY_TYPE = {
    "papers": ContentItem.Type.PAPER,
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
}
_NOUN = {"papers": "paper", "grants": "grant", "conferences": "conference"}


@dataclass
class ThemeBlock:
    label: str
    counts: dict[str, int] = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)


@dataclass
class LabDigest:
    lab_name: str
    lab_slug: str
    on: date
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    themes: list[ThemeBlock] = field(default_factory=list)
    ungrouped: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def compile_lab_digest(lab, *, on: date | None = None) -> LabDigest:
    """Gather the lab's day from the same scores its feed and briefing read."""
    on = on or timezone.localdate()
    digest = LabDigest(lab_name=lab.name, lab_slug=lab.slug, on=on)

    by_theme: dict[str, ThemeBlock] = {}
    for category in LAB_BRIEFING_CATEGORIES:
        content_type = _CATEGORY_TYPE.get(category)
        if content_type is None:
            continue
        scores = _suggested_scores({"target_lab": lab}, content_type)
        if not scores:
            continue
        digest.counts[category] = len(scores)
        digest.total += len(scores)
        for score in scores:
            row = _row(score, category)
            label = score.signals.get("cluster_label") or ""
            if not label:
                digest.ungrouped.append(row)
                continue
            block = by_theme.setdefault(label, ThemeBlock(label=label))
            block.counts[category] = block.counts.get(category, 0) + 1
            block.items.append(row)

    # Strongest themes first: a channel post is skimmed, so the lab's busiest focus
    # should be the first thing read, not whichever category happened to sort first.
    ordered = sorted(by_theme.values(), key=lambda b: -sum(b.counts.values()))
    for block in ordered[:MAX_THEMES]:
        block.items.sort(key=lambda r: -r["match_percent"])
        block.items = block.items[:ITEMS_PER_THEME]
    digest.themes = ordered[:MAX_THEMES]
    digest.ungrouped.sort(key=lambda r: -r["match_percent"])
    digest.ungrouped = digest.ungrouped[:ITEMS_PER_THEME]
    return digest


def _row(score, category: str) -> dict:
    meta = (score.content.metadata or {}) if score.content_id else {}
    return {
        "title": meta.get("title") or meta.get("name") or "Untitled",
        "url": meta.get("website") or meta.get("pdf_url") or (
            score.content.source_url if score.content_id else ""
        ),
        "category": category,
        "match_percent": int(score.signals.get("match_percent") or 0),
        "is_new": bool(score.signals.get("is_new")),
    }


# --------------------------------------------------------------------------- #
# Eligibility
# --------------------------------------------------------------------------- #
def eligible_labs(labs) -> list:
    """Labs that should receive a channel digest today.

    Every condition is checked here rather than trusted from setup time:

    * the bot add-on is **live now** — a lapsed plan goes quiet, and the check has to
      happen at delivery or it never happens at all;
    * the guild link is active;
    * an updates channel is bound. **A blank binding is a deliberate opt-out and is
      respected in silence** — no warning, no incident. A lab that turned this off
      should not be told about it every morning.
    """
    from apps.billing.entitlements import Feature, lab_has_feature

    out = []
    for lab in labs:
        if not lab_has_feature(lab, Feature.BOT_SERVER):
            continue
        link = resolve.get_guild_link_for_lab(lab)
        if link is None or link.state != resolve.GUILD_ACTIVE:
            continue
        if not resolve.get_updates_channel_for_lab(lab):
            continue
        out.append(lab)
    return out


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def queue_lab_digest(lab, *, on: date | None = None, digest: LabDigest | None = None):
    """Queue one channel post for one lab, once per day.

    ``dedupe_key`` is ``lab_digest:<lab>:<date>`` and the outbox enforces it as a
    database uniqueness constraint, so re-running the daily pipeline is a no-op
    rather than a second post. That is the whole of the idempotency guarantee — no
    separate ledger, no "have I sent today?" query that could race.
    """
    on = on or timezone.localdate()
    digest = digest or compile_lab_digest(lab, on=on)
    if digest.is_empty:
        # Nothing found today. A daily "I found nothing" post trains people to
        # ignore the channel, which costs more than the silence does.
        return None, False

    channel_id = resolve.get_updates_channel_for_lab(lab)
    if not channel_id:
        return None, False

    return outbox.enqueue_channel(
        dedupe_key=f"lab_digest:{lab.id}:{on:%Y-%m-%d}",
        kind="lab_digest",
        channel_id=channel_id,
        lab=lab,
        embed=digest_embed(digest),
        subject_type="lab_digest",
        subject_id=str(lab.id),
    )


def digest_embed(digest: LabDigest) -> dict:
    """The channel post: themes, counts, a few titles, and a way to see the rest.

    Kept well inside Discord's limits (25 fields, 6000 characters across embeds) by
    construction rather than by truncation — at most eight themes of three items.
    """
    tally = ", ".join(
        f"**{n}** {_NOUN.get(cat, cat)}{'' if n == 1 else 's'}"
        for cat, n in digest.counts.items()
    )
    embed = {
        "title": f"{digest.lab_name} — what Mylo found today",
        "description": tally or "A quiet day.",
        "color": 0x3B7A57,
        "fields": [],
    }
    for block in digest.themes:
        lines = []
        for item in block.items:
            mark = " · new" if item["is_new"] else ""
            title = item["title"][:120]
            line = f"[{title}]({item['url']})" if item["url"] else title
            lines.append(f"{line} — {item['match_percent']}%{mark}")
        counts = ", ".join(
            f"{n} {_NOUN.get(cat, cat)}{'' if n == 1 else 's'}"
            for cat, n in block.counts.items()
        )
        embed["fields"].append(
            {
                "name": f"{block.label} · {counts}",
                "value": "\n".join(lines) or "—",
                "inline": False,
            }
        )
    if digest.ungrouped:
        embed["fields"].append(
            {
                "name": "Also today",
                "value": "\n".join(
                    f"[{i['title'][:120]}]({i['url']}) — {i['match_percent']}%"
                    if i["url"]
                    else f"{i['title'][:120]} — {i['match_percent']}%"
                    for i in digest.ungrouped
                ),
                "inline": False,
            }
        )

    base = str(getattr(settings, "DISCORD_APP_BASE_URL", "") or "").rstrip("/")
    if base:
        embed["url"] = f"{base}/app/daily"
    embed["footer"] = {"text": "The full report is in Mycelium."}
    return embed


def written_briefing_line(lab) -> str:
    """The first line of the lab's written briefing, if one exists."""
    briefing = DailyBriefing.objects.filter(lab=lab).first()
    if briefing is None or not briefing.body:
        return ""
    for line in briefing.body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""
