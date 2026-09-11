"""The lab digest finally reaches the channel labs have been configuring all along.

The load-bearing assertion is idempotency: one post per lab per day, and re-running
the daily pipeline produces no second post — the summary or the attached report.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab
from apps.content.daily_report import compile_report_for_lab
from apps.content.discord_embeds import lab_post_embed
from apps.content.lab_digest import (
    eligible_labs,
    is_quiet,
    queue_lab_digest,
    queue_lab_report,
)
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.integrations.models import DiscordGuildLink, DiscordOutboxMessage
from apps.integrations.services import discord_api, outbox
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)

TODAY = date(2026, 7, 16)  # the digest's "on" date — drives filenames and dedupe
# The *run* date, which the report's freshness gate compares first_seen against.
# It has to be the real one: nothing here freezes the clock.
RUN_DATE = timezone.now().date().isoformat()


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
            "first_seen": RUN_DATE,
            "embedding_match": 0.8,
            # The report shows the lab's slate, so a row meant to reach it is in it.
            "top_rank": 1,
            "entered_top_on": RUN_DATE,
            "is_new_top": True,
        },
    )
    return item


# --------------------------------------------------------------------------- #
# Eligibility — every condition checked at delivery, not trusted from setup
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_configured_entitled_lab_is_eligible(db) -> None:
    lab = _lab()
    assert eligible_labs([lab], on=TODAY) == [lab]


@pytest.mark.django_db
def test_a_lapsed_addon_goes_quiet(db) -> None:
    """The check has to happen at delivery, or it never happens at all."""
    lab = _lab(addon=False)
    assert eligible_labs([lab], on=TODAY) == []


@pytest.mark.django_db
def test_a_blank_channel_is_a_silent_opt_out(db) -> None:
    """A lab that turned this off should not hear about it every morning."""
    lab = _lab(channel="")
    assert eligible_labs([lab], on=TODAY) == []


@pytest.mark.django_db
def test_a_kicked_guild_is_not_posted_to(db) -> None:
    lab = _lab(state=DiscordGuildLink.State.KICKED)
    assert eligible_labs([lab], on=TODAY) == []


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_post_counts_what_entered_a_top_list(db) -> None:
    """The post reports change; the attached document holds the standing lists."""
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI")
    _scored(lab, title="Imaging call", cluster="Medical AI",
            category=ContentItem.Type.GRANT)
    _scored(lab, title="Soft actuators", cluster="Robotics")

    stats = compile_report_for_lab(lab).stats

    assert stats.entered == 3
    assert stats.by_category["papers"] == (2, 2)
    assert stats.by_category["grants"] == (1, 1)


@pytest.mark.django_db
def test_fellowships_are_counted_too(db) -> None:
    """A lab is scored for fellowships, so its post has to admit they exist."""
    lab = _lab()
    _scored(lab, title="A paper", cluster="Medical AI")
    _scored(
        lab,
        title="A fellowship",
        cluster="Medical AI",
        category=ContentItem.Type.FELLOWSHIP,
    )

    stats = compile_report_for_lab(lab).stats

    assert stats.by_category["fellowships"][0] == 1


@pytest.mark.django_db
def test_a_quiet_day_posts_nothing(db) -> None:
    """A daily 'I found nothing' trains people to ignore the channel (plan H7)."""
    lab = _lab()

    assert is_quiet(compile_report_for_lab(lab)) is True
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
    """Discord rejects an oversized embed outright, so the post is fitted first."""
    lab = _lab()
    for theme in range(12):
        for n in range(6):
            _scored(lab, title=f"Item {theme}-{n} " + "x" * 200, cluster=f"Theme {theme}")

    data = compile_report_for_lab(lab)
    queue_lab_digest(lab, on=TODAY, data=data)
    row = DiscordOutboxMessage.objects.get()

    assert len(data.stats.by_theme) <= 8
    assert len(row.embed["fields"]) <= 25
    assert all(len(f["value"]) <= 1024 for f in row.embed["fields"])
    assert len(row.embed["description"]) <= 4096


# --------------------------------------------------------------------------- #
# The post: an overview first, then statistics
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_post_says_what_kind_of_day_it_was_before_any_number(db) -> None:
    """A count with nothing behind it cannot answer "was that a lot?"."""
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI")
    _scored(
        lab,
        title="Imaging call",
        cluster="Medical AI",
        category=ContentItem.Type.GRANT,
    )
    _scored(lab, title="Soft actuators", cluster="Robotics")

    data = compile_report_for_lab(lab)
    embed = lab_post_embed(data, data.stats)

    assert embed["description"].strip()
    names = [f["name"] for f in embed["fields"]]
    assert any(name.startswith("Found ") for name in names)
    assert any(name.startswith("By category") for name in names)
    assert embed["footer"]["text"].endswith("Mylo never tags anyone")


@pytest.mark.django_db
def test_the_post_carries_no_percentage_cosine_or_score(db) -> None:
    """Plan H3: user-facing text shows verdicts and positions only."""
    lab = _lab()
    _scored(lab, title="Segmentation nets", cluster="Medical AI", percent=88)

    data = compile_report_for_lab(lab)
    rendered = str(lab_post_embed(data, data.stats)).lower()

    assert "%" not in rendered
    assert "cosine" not in rendered
    assert "score" not in rendered


# --------------------------------------------------------------------------- #
# The report, attached as a PDF
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_report_is_attached_not_pasted(db, tmp_path) -> None:
    """A day's report runs to thousands of words.

    Posting it as message text — the first attempt — turns the channel into a wall
    people mute. It goes as the same PDF a member already receives by DM.
    """
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\nA readable report.")

    queue_lab_digest(lab, on=TODAY)
    assert queue_lab_report(lab, on=TODAY, workdir=tmp_path) is True

    rows = list(DiscordOutboxMessage.objects.order_by("id"))
    assert [r.kind for r in rows] == ["lab_digest", "lab_report"]
    assert all(r.channel_id == "updates-chan" for r in rows)
    report = rows[1]
    # A one-line note, and the document itself as a file.
    assert report.content == "Today's full report is attached."
    assert "A readable report" not in report.content
    assert report.attachment_filename == f"mylo-report-neuro-{TODAY:%Y-%m-%d}.pdf"
    written = tmp_path / report.attachment_filename
    assert written.exists()
    assert written.read_bytes().startswith(b"%PDF")
    assert str(written) == report.attachment_path


@pytest.mark.django_db
def test_the_report_carries_the_labs_own_matches(db, tmp_path) -> None:
    """It must be the lab's day, not a blank template with the lab's name on it."""
    from apps.content.daily_report import compile_report_for_lab

    lab = _lab()
    _scored(lab, title="A paper", cluster="Medical AI")
    _scored(
        lab,
        title="A grant",
        cluster="Medical AI",
        category=ContentItem.Type.GRANT,
    )
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\nToday's reading.")

    data = compile_report_for_lab(lab)

    assert data.display_name == "Lab neuro"
    assert data.counts["papers"] == 1
    assert data.counts["grants"] == 1
    assert [i.title for i in data.personal.items["papers"]] == ["A paper"]
    assert data.briefing_markdown == "## Papers\n\nToday's reading."


@pytest.mark.django_db
def test_a_lab_with_nothing_to_report_still_gets_its_summary(db, tmp_path) -> None:
    lab = _lab()

    assert queue_lab_report(lab, on=TODAY, workdir=tmp_path) is False
    assert DiscordOutboxMessage.objects.count() == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db
def test_the_report_is_queued_once_per_day_too(db, tmp_path) -> None:
    """Re-running the daily chain must not upload the report a second time."""
    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\nA readable report.")

    first = queue_lab_report(lab, on=TODAY, workdir=tmp_path)
    second = queue_lab_report(lab, on=TODAY, workdir=tmp_path)

    assert first is True
    assert second is False
    assert DiscordOutboxMessage.objects.filter(kind="lab_report").count() == 1
    # And no half-written staging file is left behind by the second render.
    assert [p.name for p in tmp_path.iterdir()] == [
        f"mylo-report-neuro-{TODAY:%Y-%m-%d}.pdf"
    ]


@pytest.mark.django_db
def test_the_pdf_is_uploaded_to_the_channel_and_pings_nobody(
    db, tmp_path, monkeypatch, settings
) -> None:
    """The end the change is actually judged at: what Discord receives.

    ``deliver_one`` branches on the attachment path, never on the target type, so a
    channel row takes the same multipart upload a DM already did — this pins that it
    genuinely does, at the lab's own channel, with mentions still disarmed.
    """
    settings.DISCORD_BOT_TOKEN = "test-token"
    calls: list[dict] = []

    def transport(method, path, *, auth=None, json_body=None, raw_body=None, **kw):
        calls.append({"path": path, "raw_body": raw_body, **kw})
        return RawResponse(200, {"id": "msg-1"})

    monkeypatch.setattr(discord_api, "_request", transport)

    lab = _lab()
    _scored(lab, title="Something", cluster="Medical AI")
    DailyBriefing.objects.create(lab=lab, body="## Papers\n\nA readable report.")
    queue_lab_report(lab, on=TODAY, workdir=tmp_path)

    result = outbox.drain()

    assert result.delivered == 1
    sent = calls[-1]
    assert sent["path"] == "/channels/updates-chan/messages"
    assert sent["content_type"].startswith("multipart/form-data; boundary=")
    assert b"%PDF" in sent["raw_body"]
    assert b'name="files[0]"; filename="mylo-report-neuro-' in sent["raw_body"]
    assert b'"parse": []' in sent["raw_body"]


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

    stats = compile_report_for_lab(lab).stats

    # Only the promoted row is counted; the computed-but-unpromoted one is not.
    assert stats.entered == 1
    assert stats.by_category["papers"] == (1, 1)
