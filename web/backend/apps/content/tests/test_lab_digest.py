"""The lab digest finally reaches the channel labs have been configuring all along.

The load-bearing assertion is idempotency: one post per lab per day, and re-running
the daily pipeline produces no second post — now across the summary *and* every
message the written report is split into.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab
from apps.content.lab_digest import (
    MAX_REPORT_CHUNKS,
    REPORT_CHUNK_CHARS,
    compile_lab_digest,
    digest_embed,
    eligible_labs,
    queue_lab_digest,
    queue_lab_report,
    report_chunks,
)
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.integrations.models import DiscordGuildLink, DiscordOutboxMessage
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)

TODAY = date(2026, 7, 16)


@pytest.fixture(autouse=True)
def _discord_settings():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _lab(slug="neuro", *, addon=True, channel="updates-chan", state=None):
    lab = Lab.objects.create(name=f"Lab {slug}", slug=slug)
    if addon:
        grant_bot_server(lab)
    DiscordGuildLink.objects.create(
        lab=lab,
        guild_id=f"g-{slug}",
        state=state or DiscordGuildLink.State.ACTIVE,
        updates_channel_id=channel,
    )
    return lab


def _scored(lab, *, title, cluster="", category=ContentItem.Type.PAPER, percent=80):
    item = ContentItem.objects.create(
        type=category,
        source="pivot",
        external_id=f"{title}-{cluster}",
        metadata={"title": title},
    )
    RelevanceScore.objects.create(
        content=item,
        target_lab=lab,
        score=0.9,
        signals={
            "suggested": True,
            "match_percent": percent,
            "cluster_label": cluster,
            "cluster_id": cluster.lower().replace(" ", "-") if cluster else "",
            "area": category,
            "run_at": "2026-07-16T00:00:00Z",
        },
    )
    return item


# --------------------------------------------------------------------------- #
# Eligibility — every condition checked at delivery, not trusted from setup
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_configured_entitled_lab_is_eligible(db) -> None:
    lab = _lab()
    assert eligible_labs([lab]) == [lab]


@pytest.mark.django_db
def test_a_lapsed_addon_goes_quiet(db) -> None:
    """The check has to happen at delivery, or it never happens at all."""
    lab = _lab(addon=False)
    assert eligible_labs([lab]) == []


@pytest.mark.django_db
def test_a_blank_channel_is_a_silent_opt_out(db) -> None:
    """A lab that turned this off should not hear about it every morning."""
    lab = _lab(channel="")
    assert eligible_labs([lab]) == []


@pytest.mark.django_db
def test_a_kicked_guild_is_not_posted_to(db) -> None:
    lab = _lab(state=DiscordGuildLink.State.KICKED)
    assert eligible_labs([lab]) == []


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_digest_groups_by_research_theme(db) -> None:
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI")
    _scored(lab, title="Imaging call", cluster="Medical AI",
            category=ContentItem.Type.GRANT)
    _scored(lab, title="Soft actuators", cluster="Robotics")

    digest = compile_lab_digest(lab, on=TODAY)

    labels = [t.label for t in digest.themes]
    assert set(labels) == {"Medical AI", "Robotics"}
    # Busiest theme first: a channel post is skimmed, so the lab's main focus leads.
    assert labels[0] == "Medical AI"
    assert digest.total == 3


@pytest.mark.django_db
def test_unattributed_items_are_still_counted(db) -> None:
    """They must not vanish just because they carry no theme."""
    lab = _lab()
    _scored(lab, title="Themed", cluster="Medical AI")
    _scored(lab, title="Themeless", cluster="")

    digest = compile_lab_digest(lab, on=TODAY)

    assert digest.total == 2
    assert digest.ungrouped is not None
    assert digest.ungrouped.total == 1


@pytest.mark.django_db
def test_fellowships_are_counted_too(db) -> None:
    """A lab is scored for fellowships, so its summary has to admit they exist."""
    lab = _lab()
    _scored(lab, title="A paper", cluster="Medical AI")
    _scored(
        lab,
        title="A fellowship",
        cluster="Medical AI",
        category=ContentItem.Type.FELLOWSHIP,
    )

    digest = compile_lab_digest(lab, on=TODAY)

    assert digest.counts["fellowships"] == 1
    assert digest.themes[0].counts["fellowships"] == 1


@pytest.mark.django_db
def test_a_quiet_day_posts_nothing(db) -> None:
    """A daily 'I found nothing' trains people to ignore the channel."""
    lab = _lab()

    row, created = queue_lab_digest(lab, on=TODAY)

    assert created is False
    assert DiscordOutboxMessage.objects.count() == 0


# --------------------------------------------------------------------------- #
# Idempotency — the guarantee introducing a queue is most likely to break
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_one_post_per_lab_per_day(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    _row, first = queue_lab_digest(lab, on=TODAY)
    _row, second = queue_lab_digest(lab, on=TODAY)
    _row, third = queue_lab_digest(lab, on=TODAY)

    assert first is True
    assert second is False and third is False
    assert DiscordOutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_the_next_day_is_a_new_post(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    queue_lab_digest(lab, on=TODAY)
    _row, created = queue_lab_digest(lab, on=date(2026, 7, 17))

    assert created is True
    assert DiscordOutboxMessage.objects.count() == 2


@pytest.mark.django_db
def test_two_labs_do_not_share_a_key(db) -> None:
    a, b = _lab("alpha"), _lab("beta")
    _scored(a, title="A item", cluster="Medical AI")
    _scored(b, title="B item", cluster="Robotics")

    queue_lab_digest(a, on=TODAY)
    queue_lab_digest(b, on=TODAY)

    assert DiscordOutboxMessage.objects.count() == 2


# --------------------------------------------------------------------------- #
# The post itself
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_post_goes_to_the_updates_channel_and_pings_nobody(db) -> None:
    """It is an update, not a summons."""
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    queue_lab_digest(lab, on=TODAY)

    row = DiscordOutboxMessage.objects.get()
    assert row.channel_id == "updates-chan"
    assert row.lab_id == lab.id
    assert not row.content  # no mention line at all
    assert row.embed["title"].startswith("Lab neuro")


@pytest.mark.django_db
def test_the_post_stays_inside_discords_embed_limits(db) -> None:
    """Bounded by construction — at most eight themes, one line each."""
    lab = _lab()
    for theme in range(12):
        for n in range(6):
            _scored(lab, title=f"Item {theme}-{n}", cluster=f"Theme {theme}")

    digest = compile_lab_digest(lab, on=TODAY)
    queue_lab_digest(lab, on=TODAY, digest=digest)
    row = DiscordOutboxMessage.objects.get()

    assert len(digest.themes) <= 8
    assert len(row.embed["fields"]) <= 25
    assert len(str(row.embed)) < 6000


# --------------------------------------------------------------------------- #
# The summary: names and numbers, nothing else
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_summary_names_themes_and_counts_only(db) -> None:
    """Three truncated titles per theme read as noise beside the report itself."""
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI")
    _scored(
        lab,
        title="Imaging call",
        cluster="Medical AI",
        category=ContentItem.Type.GRANT,
    )
    _scored(lab, title="Soft actuators", cluster="Robotics")

    embed = digest_embed(compile_lab_digest(lab, on=TODAY))

    rendered = str(embed)
    assert "Segmentation nets" not in rendered
    assert "Soft actuators" not in rendered
    assert "%" not in rendered  # no per-item match percentages either
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["Medical AI"] == "1 paper · 1 grant"
    assert fields["Robotics"] == "1 paper"
    assert embed["footer"]["text"] == "See the full report below."


@pytest.mark.django_db
def test_an_unthemed_lab_is_not_told_its_numbers_twice(db) -> None:
    """With nothing to break down by, one line is the whole summary."""
    lab = _lab()
    _scored(lab, title="One", cluster="")
    _scored(lab, title="Two", cluster="")

    embed = digest_embed(compile_lab_digest(lab, on=TODAY))

    assert embed["description"] == "**2** papers"
    assert embed["fields"] == []


@pytest.mark.django_db
def test_the_summary_link_is_not_localhost(db) -> None:
    """It goes to a whole lab's server; a loopback link helps nobody there."""
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    embed = digest_embed(compile_lab_digest(lab, on=TODAY))

    assert "localhost" not in embed.get("url", "")
    assert "127.0.0.1" not in embed.get("url", "")


# --------------------------------------------------------------------------- #
# The written report, in the same channel
# --------------------------------------------------------------------------- #
def test_a_short_report_is_one_message() -> None:
    assert report_chunks("## Papers\n\nOne short paragraph.") == [
        "## Papers\n\nOne short paragraph."
    ]


def test_an_empty_report_is_no_message() -> None:
    assert report_chunks("") == []
    assert report_chunks("   \n\n ") == []


def test_every_chunk_fits_and_nothing_is_lost() -> None:
    """Over 2000 characters Discord returns a 400, which the outbox never retries."""
    body = "\n\n".join(f"## Section {n}\n\n{'word ' * 120}" for n in range(6))

    chunks = report_chunks(body)

    assert len(chunks) > 1
    assert all(len(c) <= REPORT_CHUNK_CHARS for c in chunks)
    # Whitespace at the seams is normalised away; every word survives.
    assert " ".join(" ".join(chunks).split()) == " ".join(body.split())


def test_a_split_prefers_a_paragraph_boundary() -> None:
    """A heading must never be orphaned from the paragraph it introduces."""
    body = "\n\n".join(f"## Section {n}\n\n{'word ' * 100}" for n in range(4))

    chunks = report_chunks(body)

    assert all(not c.endswith("##") for c in chunks)
    assert all(c.strip() for c in chunks)


def test_a_runaway_report_is_cut_with_a_pointer_home() -> None:
    """Past a certain length a channel is the wrong medium; flooding it is worse."""
    body = "\n\n".join(f"paragraph {n} " + "word " * 200 for n in range(60))

    chunks = report_chunks(body, tail_url="https://mycelium.example.com/app/daily")

    assert len(chunks) == MAX_REPORT_CHUNKS
    assert "the rest of today's report is in Mycelium" in chunks[-1]
    assert len(chunks[-1]) <= REPORT_CHUNK_CHARS


@pytest.mark.django_db
def test_the_report_follows_the_summary_into_the_same_channel(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\nA readable report.")

    queue_lab_digest(lab, on=TODAY)
    queued = queue_lab_report(lab, on=TODAY)

    assert queued == 1
    rows = list(DiscordOutboxMessage.objects.order_by("id"))
    assert [r.kind for r in rows] == ["lab_digest", "lab_report"]
    assert all(r.channel_id == "updates-chan" for r in rows)
    # The report is message text, not an embed — it is meant to be read in place.
    assert rows[1].content == "## Papers\n\nA readable report."
    assert not rows[1].embed


@pytest.mark.django_db
def test_a_lab_with_no_written_report_still_gets_its_summary(db) -> None:
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")

    queue_lab_digest(lab, on=TODAY)
    queued = queue_lab_report(lab, on=TODAY)

    assert queued == 0
    assert DiscordOutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_the_report_is_queued_once_per_day_too(db) -> None:
    """Re-running the daily chain must not repost the report either."""
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\n" + "word " * 900)

    first = queue_lab_report(lab, on=TODAY)
    second = queue_lab_report(lab, on=TODAY)

    assert first > 1  # long enough to need several messages
    assert second == 0
    assert DiscordOutboxMessage.objects.filter(kind="lab_report").count() == first


@pytest.mark.django_db
def test_the_digest_reads_the_same_scores_as_the_labs_feed(db) -> None:
    """It must not become a second source of truth."""
    lab = _lab()
    User.objects.create_user("member")
    _scored(lab, title="Shown", cluster="Medical AI", percent=90)
    # An unsuggested row is not in the lab's feed, so it is not in the digest.
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="pivot", external_id="hidden",
        metadata={"title": "Hidden"},
    )
    RelevanceScore.objects.create(
        content=item, target_lab=lab, score=0.1,
        signals={"suggested": False, "match_percent": 10, "area": "paper"},
    )

    digest = compile_lab_digest(lab, on=TODAY)

    # Only the promoted row is counted; the computed-but-unpromoted one is not.
    assert digest.total == 1
    assert digest.counts["papers"] == 1
    assert [t.label for t in digest.themes] == ["Medical AI"]
