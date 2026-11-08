"""Manual re-render + re-delivery of one target's daily report.

The load-bearing assertion is that a re-send *sends*. Both of the commands that
existed for this ran clean and delivered nothing: the outbox is idempotent on
``dedupe_key``, the daily key is per-day, so asking again on the same day re-found
the row that had already gone out at 3am. Everything else here is about telling an
operator why a target was skipped instead of leaving them with a silent success.
"""

from __future__ import annotations

from datetime import date

import pytest
from apps.accounts.models import Lab, WatchPreference
from apps.billing.testing import link_discord, paid_plan
from apps.integrations.models import (
    DiscordIdentity,
    DiscordOutboxMessage,
)
from apps.integrations.testing import bind
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from tools.delivery.models import DailyBriefing
from tools.delivery.report_resend import repost_lab_report, resend_user_report
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = timezone.now().date().isoformat()


@pytest.fixture(autouse=True)
def _discord_settings(tmp_path, settings):
    settings.DISCORD_OUTBOX_ATTACHMENT_DIR = str(tmp_path / "outbox")
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def _reader(username="reader") -> User:
    user = User.objects.create_user(username, password="x")
    WatchPreference.objects.create(user=user, categories=["papers"])
    paid_plan(user)
    link_discord(user)
    return user


def _slate_row(target: dict, title: str, *, entered_on=TODAY, rank=1):
    content = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="test",
        external_id=title,
        source_url="https://example.org/x",
        metadata={"title": title},
    )
    return RelevanceScore.objects.create(
        content=content,
        score=0.9,
        signals={
            "suggested": True,
            "run_at": "2026-07-11T06:00:00",
            "rank": rank,
            "headline": f"Headline {title}",
            "reason": f"Why {title} fits.",
            "match_percent": 88,
            "embedding_match": 0.8,
            "first_seen": TODAY,
            "top_rank": rank,
            "entered_top_on": entered_on,
            "is_new_top": entered_on == TODAY,
        },
        **target,
    )


# --------------------------------------------------------------------------- #
# A person
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_resend_queues_even_after_the_day_already_sent() -> None:
    """The regression: the daily key made a same-day re-send a silent no-op."""
    user = _reader()
    _slate_row({"target_user": user}, "A Paper")
    # This morning's send, already settled.
    DiscordOutboxMessage.objects.create(
        dedupe_key=f"daily_report:{user.id}:{TODAY}",
        kind="daily_report",
        target_type=DiscordOutboxMessage.Target.DM,
        recipient_user=user,
        status=DiscordOutboxMessage.Status.SENT,
        next_attempt_at=timezone.now(),
    )

    outcome = resend_user_report(user, complete=lambda _s, _u: None)

    assert outcome.ok, outcome.blocked_by
    assert outcome.dedupe_key == f"daily_report:{user.id}:{TODAY}:resend:1"
    assert DiscordOutboxMessage.objects.filter(
        dedupe_key=outcome.dedupe_key, status=DiscordOutboxMessage.Status.PENDING
    ).exists()


@pytest.mark.django_db
def test_each_resend_takes_the_next_key() -> None:
    """Two re-sends are two rows, not one row sent twice."""
    user = _reader()
    _slate_row({"target_user": user}, "A Paper")

    first = resend_user_report(user, complete=lambda _s, _u: None)
    second = resend_user_report(user, complete=lambda _s, _u: None)

    assert first.dedupe_key.endswith(":resend:1")
    assert second.dedupe_key.endswith(":resend:2")
    assert first.ok and second.ok


@pytest.mark.django_db
def test_a_resend_rewrites_the_briefing_over_the_current_top_25() -> None:
    """"Re-render" means re-render — the reader gets today's data, not 3am's."""
    user = _reader()
    _slate_row({"target_user": user}, "A Paper")
    DailyBriefing.objects.create(
        user=user,
        generated_on=timezone.localdate(),
        body="The stale 3am body.",
        origin=DailyBriefing.Origin.LLM,
    )

    outcome = resend_user_report(user, complete=lambda _s, _u: "A fresh body.")

    assert outcome.regenerated
    body = DailyBriefing.objects.get(user=user, generated_on=timezone.localdate()).body
    assert "The stale 3am body." not in body


@pytest.mark.django_db
def test_no_regenerate_keeps_the_stored_briefing() -> None:
    user = _reader()
    _slate_row({"target_user": user}, "A Paper")
    DailyBriefing.objects.create(
        user=user,
        generated_on=timezone.localdate(),
        body="Exactly what was written earlier.",
        origin=DailyBriefing.Origin.LLM,
    )

    def boom(_system, _user):
        raise AssertionError("the model must not be called with --no-regenerate")

    outcome = resend_user_report(user, regenerate=False, complete=boom)

    assert outcome.ok and not outcome.regenerated
    assert DailyBriefing.objects.get(
        user=user, generated_on=timezone.localdate()
    ).body == "Exactly what was written earlier."


@pytest.mark.django_db
def test_an_opted_out_reader_is_refused_with_a_reason() -> None:
    """Opting out is the reader's decision; the operator is told, not obeyed."""
    user = _reader()
    DiscordIdentity.objects.filter(user=user).update(daily_report_opt_out=True)

    outcome = resend_user_report(user)

    assert not outcome.ok
    assert "opted out" in outcome.blocked_by
    assert not DiscordOutboxMessage.objects.exists()


@pytest.mark.django_db
def test_an_unentitled_reader_is_refused_with_a_reason() -> None:
    user = User.objects.create_user("free", password="x")
    link_discord(user)

    outcome = resend_user_report(user)

    assert not outcome.ok
    assert "scheduled reports" in outcome.blocked_by


@pytest.mark.django_db
def test_a_dry_run_renders_but_queues_nothing() -> None:
    user = _reader()
    _slate_row({"target_user": user}, "A Paper")

    outcome = resend_user_report(user, dry_run=True, complete=lambda _s, _u: None)

    assert not outcome.ok
    assert "dry run" in outcome.blocked_by
    assert not DiscordOutboxMessage.objects.exists()


@pytest.mark.django_db
def test_the_command_names_a_username_it_cannot_find() -> None:
    """A typo is the likeliest reason an operator sees nothing happen."""
    with pytest.raises(CommandError, match="no such user"):
        call_command("resend_user_report", "--user", "nobody-here")


# --------------------------------------------------------------------------- #
# A lab
# --------------------------------------------------------------------------- #
def _lab(slug="neuro", *, channel="updates-chan") -> Lab:
    lab = Lab.objects.create(name=f"Lab {slug}", slug=slug)
    grant_bot_server(lab)
    bind(lab=lab, guild_id=f"g-{slug}", updates=channel)
    return lab


@pytest.mark.django_db
def test_a_lab_repost_queues_even_after_the_day_already_posted() -> None:
    lab = _lab()
    _slate_row({"target_lab": lab}, "A Lab Paper")
    on = timezone.localdate()
    DiscordOutboxMessage.objects.create(
        dedupe_key=f"lab_report:{lab.id}:{on:%Y-%m-%d}",
        kind="lab_report",
        target_type=DiscordOutboxMessage.Target.CHANNEL,
        channel_id="updates-chan",
        lab=lab,
        status=DiscordOutboxMessage.Status.SENT,
        next_attempt_at=timezone.now(),
    )

    outcome = repost_lab_report(lab, complete=lambda _s, _u: None)

    assert outcome.ok, outcome.blocked_by
    assert outcome.dedupe_key.endswith(":resend:1")
    assert DiscordOutboxMessage.objects.filter(
        dedupe_key=outcome.dedupe_key, status=DiscordOutboxMessage.Status.PENDING
    ).exists()


@pytest.mark.django_db
def test_a_lab_repost_sends_the_report_and_not_a_second_summary() -> None:
    """The counts summary describes the same day; re-posting it reads as a new one."""
    lab = _lab()
    _slate_row({"target_lab": lab}, "A Lab Paper")

    repost_lab_report(lab, complete=lambda _s, _u: None)

    kinds = set(DiscordOutboxMessage.objects.values_list("kind", flat=True))
    assert kinds == {"lab_report"}


@pytest.mark.django_db
def test_a_lab_with_no_bound_channel_is_refused_with_a_reason() -> None:
    """The nightly digest respects a blank binding in silence; this does not."""
    lab = _lab(channel="")

    outcome = repost_lab_report(lab)

    assert not outcome.ok
    assert "updates channel" in outcome.blocked_by
    assert not DiscordOutboxMessage.objects.exists()


@pytest.mark.django_db
def test_the_lab_command_names_a_slug_it_cannot_find() -> None:
    with pytest.raises(CommandError, match="no such lab"):
        call_command("repost_lab_report", "--lab", "not-a-lab")


@pytest.mark.django_db
def test_the_lab_pdf_is_named_for_the_day_it_covers() -> None:
    lab = _lab()
    _slate_row({"target_lab": lab}, "A Lab Paper")

    outcome = repost_lab_report(
        lab, on=date(2026, 7, 16), complete=lambda _s, _u: None
    )

    assert outcome.pdf_path.endswith("mylo-report-neuro-2026-07-16.pdf")
