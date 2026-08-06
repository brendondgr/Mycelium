"""The nightly analytics measure the run, render, and never invent numbers."""

from __future__ import annotations

import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Department, Lab, LabMembership
from apps.billing.models import Subscription, Tier
from apps.content.analytics_report_pdf import render_analytics_pdf
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.content.run_analytics import (
    collect_delivery,
    collect_discovery,
    collect_llm_usage,
    collect_recommendations,
    collect_run_analytics,
    collect_trend,
)
from apps.content.tests.entitle import entitle_user
from apps.core.models import LLMUsageDaily
from apps.integrations.models import DiscordOutboxMessage

User = get_user_model()


def _item(kind: str, *, external_id: str) -> ContentItem:
    return ContentItem.objects.create(
        type=kind,
        source="test-source",
        external_id=external_id,
        metadata={"title": f"Item {external_id}"},
    )


def _backdate(queryset, field: str, day) -> None:
    """Move rows onto an earlier day. ``auto_now_add`` needs an explicit update."""
    queryset.update(**{field: day})


class DiscoveryTests(TestCase):
    def test_counts_new_items_by_category(self):
        _item(ContentItem.Type.PAPER, external_id="p1")
        _item(ContentItem.Type.PAPER, external_id="p2")
        _item(ContentItem.Type.GRANT, external_id="g1")
        _item(ContentItem.Type.FELLOWSHIP, external_id="f1")
        _item(ContentItem.Type.CONFERENCE, external_id="c1")

        discovery = collect_discovery(timezone.localdate())

        self.assertEqual(discovery.get("papers"), 2)
        self.assertEqual(discovery.get("grants"), 1)
        self.assertEqual(discovery.get("fellowships"), 1)
        self.assertEqual(discovery.get("conferences"), 1)
        self.assertEqual(discovery.total, 5)

    def test_yesterdays_items_are_not_todays_discovery(self):
        old = _item(ContentItem.Type.PAPER, external_id="old")
        yesterday = timezone.now() - timedelta(days=1)
        _backdate(
            ContentItem.objects.filter(pk=old.pk), "created_at", yesterday
        )
        _item(ContentItem.Type.PAPER, external_id="new")

        self.assertEqual(collect_discovery(timezone.localdate()).get("papers"), 1)

    def test_empty_day_reports_zeroes_not_gaps(self):
        discovery = collect_discovery(timezone.localdate())
        self.assertEqual(discovery.total, 0)
        self.assertEqual(discovery.get("papers"), 0)


class RecommendationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password="x")
        self.lab = Lab.objects.create(name="Fungal Systems", slug="fungal-systems")

    def test_splits_by_category_and_by_target(self):
        paper = _item(ContentItem.Type.PAPER, external_id="p1")
        grant = _item(ContentItem.Type.GRANT, external_id="g1")
        RelevanceScore.objects.create(content=paper, target_user=self.user, score=0.9)
        RelevanceScore.objects.create(content=grant, target_user=self.user, score=0.7)
        RelevanceScore.objects.create(content=paper, target_lab=self.lab, score=0.6)

        recs = collect_recommendations(timezone.localdate())

        self.assertEqual(recs.total, 3)
        self.assertEqual(recs.by_category["papers"], 2)
        self.assertEqual(recs.by_category["grants"], 1)
        self.assertEqual(recs.by_target["user"], 2)
        self.assertEqual(recs.by_target["lab"], 1)
        self.assertEqual(recs.by_target["project"], 0)

    def test_earlier_days_scores_are_excluded(self):
        paper = _item(ContentItem.Type.PAPER, external_id="p1")
        score = RelevanceScore.objects.create(
            content=paper, target_user=self.user, score=0.5
        )
        _backdate(
            RelevanceScore.objects.filter(pk=score.pk),
            "created_at",
            timezone.now() - timedelta(days=2),
        )

        self.assertEqual(collect_recommendations(timezone.localdate()).total, 0)


class LLMUsageTests(TestCase):
    def test_totals_across_components_and_orders_by_spend(self):
        today = timezone.localdate()
        LLMUsageDaily.objects.create(
            day=today, component="papers", calls=10, failures=1,
            prompt_tokens=1000, completion_tokens=200,
        )
        LLMUsageDaily.objects.create(
            day=today, component="briefing", calls=4, failures=0,
            prompt_tokens=5000, completion_tokens=900,
        )

        usage = collect_llm_usage(today)

        self.assertEqual(usage.calls, 14)
        self.assertEqual(usage.failures, 1)
        self.assertEqual(usage.prompt_tokens, 6000)
        self.assertEqual(usage.completion_tokens, 1100)
        self.assertEqual(usage.total_tokens, 7100)
        self.assertAlmostEqual(usage.failure_rate, 1 / 14)
        # Heaviest first, so the report leads with what actually cost something.
        self.assertEqual(
            [c.component for c in usage.components], ["briefing", "papers"]
        )

    def test_no_calls_means_no_failure_rate_division(self):
        usage = collect_llm_usage(timezone.localdate())
        self.assertEqual(usage.calls, 0)
        self.assertEqual(usage.failure_rate, 0.0)


class DeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ben", password="x")
        self.lab = Lab.objects.create(name="Mycology", slug="mycology")

    def test_counts_briefings_and_outbox_progress(self):
        today = timezone.localdate()
        DailyBriefing.objects.create(
            user=self.user, generated_on=today, origin=DailyBriefing.Origin.LLM
        )
        DailyBriefing.objects.create(
            lab=self.lab, generated_on=today, origin=DailyBriefing.Origin.FALLBACK
        )
        DiscordOutboxMessage.objects.create(
            dedupe_key="daily_report:1", kind="daily_report",
            target_type=DiscordOutboxMessage.Target.DM, recipient_user=self.user,
            next_attempt_at=timezone.now(), status=DiscordOutboxMessage.Status.SENT,
        )
        DiscordOutboxMessage.objects.create(
            dedupe_key="daily_report:2", kind="daily_report",
            target_type=DiscordOutboxMessage.Target.DM, recipient_user=self.user,
            next_attempt_at=timezone.now(), status=DiscordOutboxMessage.Status.PENDING,
        )
        DiscordOutboxMessage.objects.create(
            dedupe_key="lab_digest:1", kind="lab_digest",
            target_type=DiscordOutboxMessage.Target.CHANNEL, channel_id="9",
            next_attempt_at=timezone.now(), status=DiscordOutboxMessage.Status.SENT,
        )

        delivery = collect_delivery(today)

        self.assertEqual(delivery.briefings_users, 1)
        self.assertEqual(delivery.briefings_labs, 1)
        self.assertEqual(delivery.briefings_generated, 2)
        self.assertEqual(delivery.briefings_fallback, 1)
        self.assertEqual(delivery.reports_queued, 2)
        self.assertEqual(delivery.reports_delivered, 1)
        self.assertEqual(delivery.reports_pending, 1)
        self.assertEqual(delivery.digests_delivered, 1)

    def test_a_pending_report_is_pending_not_lost(self):
        DiscordOutboxMessage.objects.create(
            dedupe_key="daily_report:9", kind="daily_report",
            target_type=DiscordOutboxMessage.Target.DM, recipient_user=self.user,
            next_attempt_at=timezone.now(), status=DiscordOutboxMessage.Status.PENDING,
        )
        delivery = collect_delivery(timezone.localdate())
        self.assertEqual(delivery.reports_failed, 0)
        self.assertEqual(delivery.reports_pending, 1)


class CoverageTests(TestCase):
    def test_counts_entitled_users_active_labs_and_departments(self):
        entitled = User.objects.create_user("cara", password="x")
        entitle_user(entitled)
        User.objects.create_user("free", password="x")  # Free: never pushed a run

        department = Department.objects.create(name="Biology", owner=entitled)
        lab = Lab.objects.create(name="Spores", slug="spores", department=department)
        LabMembership.objects.create(
            lab=lab, user=entitled, role=LabMembership.Role.OWNER
        )
        Subscription.objects.create(
            tier=Tier.CANOPY,
            scope_department=department,
            status=Subscription.Status.ACTIVE,
        )

        coverage = collect_run_analytics().coverage

        self.assertEqual(coverage.users, 1)
        self.assertEqual(coverage.labs, 1)
        self.assertEqual(coverage.departments, 1)


class TrendTests(TestCase):
    def test_window_is_contiguous_and_zero_filled(self):
        today = timezone.localdate()
        LLMUsageDaily.objects.create(
            day=today - timedelta(days=3), component="papers", calls=5,
            prompt_tokens=100, completion_tokens=50,
        )

        trend = collect_trend(today, days=7)

        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[-1].day, today)
        self.assertEqual(trend[0].day, today - timedelta(days=6))
        self.assertEqual(trend[3].llm_calls, 5)
        self.assertEqual(trend[3].total_tokens, 150)
        self.assertEqual(trend[-1].llm_calls, 0)


class SnapshotTests(TestCase):
    def test_as_dict_is_json_serializable_and_complete(self):
        payload = collect_run_analytics().as_dict()
        json.dumps(payload)  # must not raise

        for key in ("coverage", "discovery", "recommendations", "llm", "delivery"):
            self.assertIn(key, payload)
        self.assertIn("total", payload["discovery"])
        self.assertIn("components", payload["llm"])
        self.assertEqual(len(payload["trend"]), 7)


class PdfTests(TestCase):
    def test_renders_from_an_empty_database(self):
        pdf = render_analytics_pdf(collect_run_analytics())
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)

    def test_renders_a_populated_run(self):
        today = timezone.localdate()
        user = User.objects.create_user("dee", password="x")
        paper = _item(ContentItem.Type.PAPER, external_id="p1")
        RelevanceScore.objects.create(content=paper, target_user=user, score=0.8)
        DailyBriefing.objects.create(user=user, generated_on=today)
        for index in range(8):  # more components than the chart shows
            LLMUsageDaily.objects.create(
                day=today, component=f"component-{index}", calls=index + 1,
                failures=index % 2, prompt_tokens=100 * index,
                completion_tokens=10 * index,
            )

        pdf = render_analytics_pdf(collect_run_analytics(today))
        self.assertTrue(pdf.startswith(b"%PDF"))


class CommandTests(TestCase):
    def test_writes_metrics_and_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "analytics.json"
            pdf_dir = Path(tmp) / "pdf"
            out = StringIO()
            call_command(
                "run_analytics_report",
                json_path=str(json_path),
                pdf_dir=str(pdf_dir),
                stdout=out,
            )

            payload = json.loads(json_path.read_text())
            self.assertIn("coverage", payload)
            self.assertIn("pdf_path", payload)
            self.assertTrue(Path(payload["pdf_path"]).exists())
            self.assertTrue(
                Path(payload["pdf_path"]).read_bytes().startswith(b"%PDF")
            )

    def test_no_pdf_flag_still_writes_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "analytics.json"
            call_command(
                "run_analytics_report",
                json_path=str(json_path),
                no_pdf=True,
                stdout=StringIO(),
            )
            payload = json.loads(json_path.read_text())
            self.assertNotIn("pdf_path", payload)

    @override_settings(RUN_ANALYTICS_RETENTION_DAYS=30)
    def test_old_reports_are_pruned_and_recent_ones_kept(self):
        today = timezone.localdate()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdf"
            pdf_dir.mkdir()
            stale = pdf_dir / (
                f"mycelium-run-analytics-{today - timedelta(days=200)}.pdf"
            )
            recent = pdf_dir / (
                f"mycelium-run-analytics-{today - timedelta(days=2)}.pdf"
            )
            unrelated = pdf_dir / "someone-elses-file.pdf"
            for path in (stale, recent, unrelated):
                path.write_bytes(b"%PDF")

            call_command(
                "run_analytics_report",
                json_path=str(Path(tmp) / "a.json"),
                pdf_dir=str(pdf_dir),
                stdout=StringIO(),
            )

            self.assertFalse(stale.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())  # not ours to delete

    @override_settings(RUN_ANALYTICS_RETENTION_DAYS=0)
    def test_retention_of_zero_keeps_everything(self):
        today = timezone.localdate()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdf"
            pdf_dir.mkdir()
            ancient = pdf_dir / (
                f"mycelium-run-analytics-{today - timedelta(days=999)}.pdf"
            )
            ancient.write_bytes(b"%PDF")
            call_command(
                "run_analytics_report",
                json_path=str(Path(tmp) / "a.json"),
                pdf_dir=str(pdf_dir),
                stdout=StringIO(),
            )
            self.assertTrue(ancient.exists())

    @override_settings(USE_TZ=True)
    def test_explicit_date_is_honoured(self):
        target = timezone.localdate() - timedelta(days=2)
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "analytics.json"
            call_command(
                "run_analytics_report",
                date=target.isoformat(),
                json_path=str(json_path),
                no_pdf=True,
                stdout=StringIO(),
            )
            payload = json.loads(json_path.read_text())
            self.assertEqual(payload["generated_on"], target.isoformat())
