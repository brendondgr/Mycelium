"""EXP-2026-11-015: one read-only count pass over the live instance.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-015-deployment-usage-snapshot/code/snapshot.py

Counts only: no name, username, email or message text leaves the database.
The public demo's fictional people (``@showcase.mycelium.invalid``) are counted
separately from real accounts, and agent threads tagged by this session's
experiments (``demo_visitor`` starting ``EXP-``) are excluded from every usage
count. Writes data/metrics.json and data/metrics.csv.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
DEMO_DOMAIN = "@showcase.mycelium.invalid"


def main() -> int:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Q
    from django.utils import timezone

    from apps.accounts.models import Department, Lab
    from apps.demo.models import DemoQuestion
    from tools.agent.models import AgentEvent, AgentThread
    from tools.delivery.models import DailyBriefing, SavedOpportunity
    from tools.recommendation.models import RelevanceEvent
    from tools.retrieval.read import ContentItem

    now = timezone.now()
    User = get_user_model()
    real = User.objects.exclude(email__iendswith=DEMO_DOMAIN).exclude(username__startswith="demo.")
    m = {"as_of": now.isoformat(timespec="seconds")}
    m["accounts_real"] = real.count()
    m["accounts_real_active"] = real.filter(is_active=True).count()
    m["accounts_real_email_verified"] = real.filter(profile__is_verified=True).count()
    m["accounts_staff"] = real.filter(is_staff=True).count()
    m["accounts_demo_fictional"] = User.objects.count() - m["accounts_real"]
    m["labs"] = Lab.objects.count()
    m["departments"] = Department.objects.count()
    from apps.accounts.models import LabMembership

    m["labs_with_real_members"] = LabMembership.objects.filter(user__in=real).values("lab").distinct().count()
    exp = Q(demo_visitor__startswith="EXP-")
    threads = AgentThread.objects.exclude(exp)
    for days in (7, 30):
        since = now - timedelta(days=days)
        active = set(real.filter(last_login__gte=since).values_list("pk", flat=True))
        active |= set(AgentEvent.objects.filter(type="user", ts__gte=since, thread__user__in=real)
                      .exclude(thread__demo_visitor__startswith="EXP-")
                      .values_list("thread__user_id", flat=True))
        active |= set(RelevanceEvent.objects.filter(created_at__gte=since, user__in=real)
                      .values_list("user_id", flat=True))
        active |= set(SavedOpportunity.objects.filter(created_at__gte=since, user__in=real)
                      .values_list("user_id", flat=True))
        m[f"people_active_{days}d"] = len(active - {None})
        m[f"people_logged_in_{days}d"] = real.filter(last_login__gte=since).count()
    since30 = now - timedelta(days=30)
    t30 = threads.filter(created_at__gte=since30)
    by_surface = {}
    for row in t30.values("surface", "demo_visitor"):
        key = "demo" if row["demo_visitor"] else row["surface"]
        by_surface[key] = by_surface.get(key, 0) + 1
    m["mylo_threads_30d_by_surface"] = by_surface
    turns = {}
    for row in (AgentEvent.objects.filter(type="user", ts__gte=since30)
                .exclude(thread__demo_visitor__startswith="EXP-")
                .values("thread__surface", "thread__demo_visitor")):
        key = "demo" if row["thread__demo_visitor"] else row["thread__surface"]
        turns[key] = turns.get(key, 0) + 1
    m["mylo_turns_30d_by_surface"] = turns
    first = DemoQuestion.objects.order_by("created_at").values_list("created_at", flat=True).first()
    m["demo_opened_first_question"] = first.isoformat(timespec="seconds") if first else None
    m["demo_questions_total"] = DemoQuestion.objects.count()
    m["demo_visitors_total"] = DemoQuestion.objects.values("visitor").distinct().count()
    m["demo_ip_hashes_total"] = DemoQuestion.objects.values("ip_hash").distinct().count()
    daily = DailyBriefing.objects.filter(kind=DailyBriefing.Kind.DAILY, generated_on__gte=(now - timedelta(days=30)).date())
    m["nightly_days_with_daily_briefings_30d"] = daily.values("generated_on").distinct().count()
    m["daily_briefings_30d"] = daily.count()
    analytics = sorted((REPO / "data" / "analytics").glob("mycelium-run-analytics-*.pdf"))
    cutoff = (now - timedelta(days=30)).date().isoformat()
    m["run_analytics_reports_30d"] = sum(1 for p in analytics if p.stem[-10:] >= cutoff)
    m["corpus_items_by_type"] = dict(ContentItem.objects.values_list("type").annotate(n=Count("id")).order_by("type"))
    m["corpus_items_total"] = ContentItem.objects.count()
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    flat = []
    for k, v in m.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                flat.append({"metric": f"{k}.{kk}", "value": vv})
        else:
            flat.append({"metric": k, "value": v})
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "value"])
        w.writeheader()
        w.writerows(flat)
    print(json.dumps(m, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
