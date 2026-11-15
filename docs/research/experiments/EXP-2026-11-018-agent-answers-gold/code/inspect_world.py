"""EXP-2026-11-018: print the demo lab's stored state (read-only), to design
questions before build_gold.py freezes them. Writes nothing to the database."""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "EXP-2026-11-013-agent-answers-human-judged" / "code"))
import mylo_turn  # noqa
mylo_turn.setup()
from django.utils import timezone
from apps.accounts.models import LabMembership
from apps.research.models import Project, ProjectMember
from tools.recommendation.read import RelevanceScore, order_by_slate, in_slate
from tools.retrieval.read import ContentDeadline
from tools.recommendation.targets import project_watch_topics, project_interests
from tools.agent.functions.org import interest_labels

ctx = mylo_turn.demo_context()
pi, lab = ctx["pi"], ctx["lab"]
print("PI", pi.username, pi.get_full_name(), "lab", lab.slug, lab.name, "today", timezone.localdate())
for m in LabMembership.objects.filter(lab=lab).select_related("user", "user__profile"):
    p = getattr(m.user, "profile", None)
    print("MEMBER", m.user.username, "|", m.user.get_full_name(), "|", m.role, m.is_lead, "|",
          getattr(p, "academic_title", None), "|", interest_labels(getattr(p, "interests", None)))
for pr in Project.objects.filter(scope_lab=lab):
    g = pr.goals or {}
    print("PROJECT", pr.pk, pr.name, pr.is_archived, pr.visibility, "status=", g.get("status"), "progress=", g.get("progress"),
          "watched=", project_watch_topics(pr), "areas=", project_interests(pr).get("areas"),
          "members=", [(u.username, u.get_full_name()) for u in pr.members.all()], "keys=", sorted(g))
    for t in ("paper", "grant", "fellowship", "conference"):
        rows = order_by_slate(RelevanceScore.objects.filter(target_project=pr, content__type=t).select_related("content"))[:3]
        for r in rows:
            print("   PFEED", t, r.content_id, (r.content.metadata or {}).get("title", "")[:80])
for t in ("paper", "grant", "fellowship", "conference"):
    rows = RelevanceScore.objects.filter(target_lab=lab, content__type=t).select_related("content")
    rows = [r for r in rows if in_slate(r.signals or {})]
    print("LABSLATE", t, len(rows))
    today = timezone.localdate()
    for r in order_by_slate(rows)[:30]:
        meta = r.content.metadata or {}
        dls = [(d.kind, str(d.due_date), d.confidence) for d in ContentDeadline.objects.filter(content=r.content)]
        print("   ", r.content_id, "|", str(meta.get("title", ""))[:70], "|", {k: str(meta.get(k))[:60] for k in ("authors","venue","year","sponsor","agency","amount","deadline","location","start_date") if meta.get(k)}, "|", dls)
