"""The Discord post explains itself before it counts anything (plan Phase 1).

The complaint this answers is specific: the posts listed a count per research
theme and nothing else, which cannot tell a reader whether the day was heavy or
thin. The contract now is an overview, then statistics, and the statistics must
reconcile with the attached document's own summary table — two numbers for one
morning is worse than one number nobody checks.

The other load-bearing assertion is fitting. Discord rejects an oversized embed
outright: the whole post fails, not the long field, and the reader hears nothing
and is told nothing. So ``fit_embed`` runs last on every producer, and it drops
whole lines.
"""

from __future__ import annotations

import pytest
from apps.accounts.models import WatchPreference
from django.contrib.auth.models import User
from django.utils import timezone

from tools.delivery import discord_embeds
from tools.delivery.daily_report import compile_report_for_user
from tools.delivery.discord_embeds import (
    DESCRIPTION_LIMIT,
    FIELD_VALUE_LIMIT,
    MAX_FIELDS,
    TOTAL_LIMIT,
    attention_lines,
    embed_size,
    fit_embed,
    overview_text,
    personal_report_embed,
    trim_to_sentence,
)
from tools.delivery.models import DailyBriefing
from tools.delivery.report_stats import ReportStats
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = timezone.now().date().isoformat()


def _item(title: str, ctype: str = ContentItem.Type.PAPER) -> ContentItem:
    return ContentItem.objects.create(
        type=ctype,
        source="test",
        external_id=title,
        source_url=f"https://example.org/{abs(hash(title))}",
        metadata={"title": title},
    )


def _score(user: User, content: ContentItem, *, rank: int = 1, verdict="read"):
    return RelevanceScore.objects.create(
        content=content,
        target_user=user,
        score=0.8,
        signals={
            "suggested": True,
            "rank": rank,
            "top_rank": rank,
            "entered_top_on": TODAY,
            "is_new_top": True,
            "first_seen": TODAY,
            "run_at": f"{TODAY}T06:00:00",
            "headline": f"Headline for {content.metadata['title']}",
            "reason": f"Why {content.metadata['title']} fits.",
            "verdict": verdict,
            "embedding_match": 0.8,
        },
    )


@pytest.fixture
def reader(db) -> User:
    user = User.objects.create_user("reader", password="x")
    WatchPreference.objects.create(user=user, categories=["papers", "grants"])
    return user


# --------------------------------------------------------------------------- #
# The overview
# --------------------------------------------------------------------------- #
def test_the_overview_is_cut_at_a_sentence_never_mid_clause() -> None:
    text = "One sentence here. A second sentence that runs on and on and on."
    assert trim_to_sentence(text, 30) == "One sentence here."
    # A single sentence longer than the limit has no boundary to cut at, so it
    # ends on a word with an ellipsis rather than mid-word.
    long = "a" + " word" * 200
    trimmed = trim_to_sentence(long, 40)
    assert len(trimmed) <= 40
    assert trimmed.endswith("…")
    assert not trimmed.endswith("wo…")


def test_overview_falls_back_when_lead_missing() -> None:
    """An unentitled reader has no prose; the fallback makes a smaller true claim."""
    stats = ReportStats(entered=4, by_theme=[("Agentic KG", 3), ("Surgical AI", 1)])
    text = overview_text("", stats, fallback_subject="your")
    assert "4 items entered your top lists today" in text
    assert "Agentic KG" in text

    quiet = overview_text("", ReportStats(), fallback_subject="your")
    assert "Nothing new entered your top lists today" in quiet


@pytest.mark.django_db
def test_the_stored_lead_is_reused_rather_than_rewritten(reader: User) -> None:
    """One model call per run: the post, the PDF and the page carry one wording."""
    _score(reader, _item("A paper"))
    DailyBriefing.objects.create(
        user=reader,
        body="## Papers",
        narrative={"lead": "Synapse had the day.", "lead_origin": "llm"},
    )

    data = compile_report_for_user(reader)
    embed = personal_report_embed(data, data.stats)

    assert embed["description"] == "Synapse had the day."


# --------------------------------------------------------------------------- #
# The statistics
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_stats_reconcile_with_summary_table(reader: User) -> None:
    """Plan S7. Two totals for one morning is worse than one nobody checks."""
    _score(reader, _item("Paper one"), rank=1)
    _score(reader, _item("Paper two"), rank=2)
    _score(reader, _item("A grant", ContentItem.Type.GRANT), rank=1)

    data = compile_report_for_user(reader)
    stats = data.stats

    assert stats.entered == data.report_new
    for category in data.categories:
        column = sum(part.counts.get(category, 0) for part in data.parts)
        assert stats.by_category[category][0] == column
    assert sum(new for _label, (new, _total) in stats.by_category.items()) == (
        stats.entered
    )


@pytest.mark.django_db
def test_the_post_reports_volume_matched_and_entered(reader: User) -> None:
    """The middle number is what makes the other two legible."""
    _score(reader, _item("Paper one"))

    data = compile_report_for_user(reader)
    line = discord_embeds.volume_line(
        data.stats, subject="you or your projects", period="overnight"
    )

    assert "matched you or your projects" in line
    assert "entered a top list" in line
    assert "none raised alerts" in line


def test_volume_is_omitted_rather_than_reported_as_zero() -> None:
    """"Mylo read 0 new papers" and "Mylo does not know" are different claims."""
    stats = ReportStats(matched=3, entered=1)
    line = discord_embeds.volume_line(stats, subject="you", period="overnight")
    assert "Mylo read" not in line
    assert "3 matched you" in line


@pytest.mark.django_db
def test_no_percentage_cosine_or_score_reaches_a_post(reader: User) -> None:
    """Plan H3 / invariant 4."""
    _score(reader, _item("Paper one"))

    data = compile_report_for_user(reader)
    rendered = str(personal_report_embed(data, data.stats)).lower()

    assert "%" not in rendered
    assert "cosine" not in rendered
    assert "score" not in rendered


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_escape_mentions_applied_to_every_linked_title(reader: User) -> None:
    """A scraped title can never render as a mention token."""
    _score(reader, _item("Ping @everyone now"))

    data = compile_report_for_user(reader)
    embed = personal_report_embed(data, data.stats)
    top = next(f["value"] for f in embed["fields"] if f["name"] == "Top of today")

    # The zero-width space is the escape: the token renders literally and pings
    # nobody. ``parse: []`` in ``discord_api`` is the second layer under it.
    assert "@everyone" not in top
    assert "@\u200beveryone" in top


def test_a_bracket_in_a_title_cannot_break_out_of_its_link() -> None:
    """Discord honours no backslash escape inside a link label, so brackets go."""
    line = discord_embeds._linked("A [redacted] study", "https://example.org/x")
    assert line == "[A (redacted) study](https://example.org/x)"


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
def test_fit_embed_drops_whole_lines_never_mid_sentence() -> None:
    lines = [f"[A reasonably long item title number {n}](https://example.org/{n})"
             for n in range(200)]
    embed = fit_embed(
        {
            "title": "T",
            "description": "d",
            "fields": [{"name": "Top", "value": "\n".join(lines)}],
        }
    )
    value = embed["fields"][0]["value"]

    assert len(value) <= FIELD_VALUE_LIMIT
    assert value.endswith("more")
    # Every kept line is a whole line — none was cut inside its link.
    for line in value.split("\n")[:-1]:
        assert line.endswith(")")


def test_embed_fits_discord_limits_with_long_titles() -> None:
    huge = "x" * 5000
    embed = fit_embed(
        {
            "title": huge,
            "description": huge,
            "fields": [{"name": huge, "value": huge} for _ in range(40)],
        }
    )

    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= DESCRIPTION_LIMIT
    assert len(embed["fields"]) <= MAX_FIELDS
    assert all(len(f["value"]) <= FIELD_VALUE_LIMIT for f in embed["fields"])
    assert embed_size(embed) <= TOTAL_LIMIT


def test_fitting_is_idempotent() -> None:
    """Producers call it last, and a caller may call it again without harm."""
    embed = {
        "title": "T",
        "description": "line\n" * 4000,
        "fields": [{"name": "n", "value": "row\n" * 1000}],
    }
    once = fit_embed(embed)
    assert fit_embed(dict(once)) == once


def test_attention_lines_summarise_past_three() -> None:
    """A list long enough to scroll has already failed at "should I open this?"."""
    alerts = [(f"Project {n}", "overlap risk", f"Title {n}", "https://x.org/1")
              for n in range(6)]
    rendered = attention_lines(alerts)

    assert rendered.count("\n") == 3
    assert rendered.endswith("…and 3 more in the report")
    assert attention_lines([]) == ""
