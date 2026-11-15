"""EXP-2026-11-018: build the question set and its gold answers from the database.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/build_gold.py

Read-only. Every gold answer is computed here, by a query written before any
answer was generated, from the same stored rows the product's own functions
read (`corpus_item`, `projects_get`, `org_person`, the slate helpers). Writes
``code/questions.json`` (what is asked) and ``data/gold.json`` (the query that
defines each answer, the gold ids and values, the values stored on the records
involved, and the snapshot time).

Candidates are listed per kind in a fixed order; the first ten that pass the
builder's checks are kept. A question is rejected when its gold set is empty
(except unanswerable ones) or larger than eight, and an unanswerable question
is rejected unless its fact pattern is absent from every record the agent
could read for it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(EXP.parent / "EXP-2026-11-013-agent-answers-human-judged" / "code"))
import mylo_turn  # noqa: E402
import normalise as N  # noqa: E402

PER_KIND = 10
MAX_GOLD = 8
KINDS = ("field", "list", "project", "people", "join", "unanswerable")

#: Fact patterns for unanswerable questions (the answer "states a fact" when
#: one matches). ``AMOUNT`` and ``PERCENT`` use the normaliser instead.
PATTERNS = {
    "cites": r"\b(cited|citations?)\b[^.\n]{0,40}?\b\d+\b|\b\d[\d,]*\s+(times|citations?)\b",
    "email": r"[\w.+-]+@[\w-]+\.[a-z]{2,}",
    "phone": r"\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-\s]\d{4}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
    "hindex": r"h-?\s?index[^.\n]{0,40}?\b\d+\b|\b\d+\b[^.\n]{0,12}h-?\s?index",
    "proposals": r"\b\d[\d,]*\s+(proposals|applications|applicants|submissions)\b",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main() -> int:
    mylo_turn.setup()
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.accounts.models import LabMembership
    from tools.agent.caller import Audience, Caller, Scope
    from tools.agent.functions.corpus import corpus_item
    from tools.agent.functions.org import interest_labels, org_person
    from tools.agent.functions.projects import _slate, projects_get
    from tools.recommendation.read import RelevanceScore, in_slate, order_by_slate
    from tools.recommendation.targets import project_watch_topics
    from tools.retrieval.read import ContentDeadline, ContentItem

    ctx = mylo_turn.demo_context()
    pi, lab = ctx["pi"], ctx["lab"]
    projects = ctx["projects"]
    today = timezone.localdate()
    snapshot = timezone.now().isoformat()
    caller = Caller(user=pi, surface="web", scope=Scope("lab", lab), audience=Audience("person"))
    User = get_user_model()

    texts: dict[str, str] = {}

    def item_text(cid) -> str:
        key = f"item:{cid}"
        if key not in texts:
            texts[key] = corpus_item(caller, key).content
        return texts[key]

    def project_text(p) -> str:
        key = f"project:{p.pk}"
        if key not in texts:
            texts[key] = projects_get(caller, key).content
        return texts[key]

    def person_text(username) -> str:
        key = f"person:{username}"
        if key not in texts:
            texts[key] = org_person(caller, key).content
        return texts[key]

    def item_obj(cid):
        row = ContentItem.objects.get(pk=cid)
        meta = row.metadata or {}
        return {"kind": "item", "id": str(row.pk), "item_type": row.type,
                "title": str(meta.get("title") or meta.get("name") or "")[:200]}

    def person_obj(u):
        return {"kind": "person", "id": u.username, "name": u.get_full_name() or u.username}

    def project_obj(p):
        return {"kind": "project", "id": str(p.pk), "name": p.name}

    def allowed_from(*bodies) -> dict:
        joined = "\n".join(bodies)
        ds = sorted({f"{d[0] or 0:04d}-{d[1]:02d}-{d[2]:02d}" for d in N.dates(joined)})
        return {"date": ds + [today.isoformat()], "amount": sorted(N.amounts(joined)),
                "percent": sorted(N.percents(joined))}

    # --- the lab's feed, and each project's -----------------------------------
    def lab_slate(t):
        rows = RelevanceScore.objects.filter(target_lab=lab, content__type=t).select_related("content")
        return [r.content for r in order_by_slate([r for r in rows if in_slate(r.signals or {})])]

    def project_top(p, t, n=1):
        return [s.content for s in _slate({"target_project": p}, [t], n)]

    def due(item, kinds=("application",), confirmed_only=False):
        rows = ContentDeadline.objects.filter(content=item, kind__in=kinds, due_date__isnull=False)
        if confirmed_only:
            rows = rows.filter(confidence="confirmed")
        return sorted(r.due_date for r in rows)

    def any_due_in(item, lo: date, hi: date, **kw) -> bool:
        return any(lo <= d <= hi for d in due(item, **kw))

    def month(y, m):
        lo = date(y, m, 1)
        hi = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        return lo, hi

    MHW = projects["Marine heatwave early warning"]
    PP = projects["Plastic pathways"]
    members = [m.user for m in LabMembership.objects.filter(lab=lab).select_related("user", "user__profile")]
    others = [u for u in members if u.pk != pi.pk]

    def labels(u):
        return interest_labels(getattr(getattr(u, "profile", None), "interests", None))

    def with_interest(rx, pool=None):
        return [u for u in (pool or others) if any(re.search(rx, lab_, re.I) for lab_ in labels(u))]

    def surname(author: str) -> str:
        author = author.strip()
        return author.split(",")[0].strip() if "," in author else author.split()[-1]

    def authors_of(cid):
        meta = ContentItem.objects.get(pk=cid).metadata or {}
        raw = meta.get("authors") or []
        if isinstance(raw, str):
            raw = [a.strip() for a in raw.split(",")]
        return [str(a) for a in raw]

    out: dict[str, list] = {k: [] for k in KINDS}
    rejected = []

    def add(kind, qid, text, gold, mentions=(), query=""):
        objs = gold.get("objects", [])
        vals = gold.get("values", [])
        n = len(objs) + len(vals)
        if kind != "unanswerable" and not (1 <= n <= MAX_GOLD):
            rejected.append({"id": qid, "why": f"gold size {n}"})
            return
        if len(out[kind]) >= PER_KIND:
            return
        gold.setdefault("objects", [])
        gold.setdefault("values", [])
        gold.setdefault("allowed", {"date": [today.isoformat()], "amount": [], "percent": []})
        out[kind].append({"id": qid, "kind": kind, "text": text, "mentions": list(mentions),
                          "scope": "lab", "query": query, "gold": gold})

    # 1. field of a tagged item ------------------------------------------------
    def field_amount(qid, cid, text):
        meta = ContentItem.objects.get(pk=cid).metadata or {}
        golds = sorted(N.amounts(str(meta.get("amount") or "")))
        add("field", qid, text, {"values": [{"type": "amount", "gold": g} for g in golds],
                                  "allowed": allowed_from(item_text(cid))},
            [f"item:{cid}"], "metadata.amount of the tagged item, parsed by normalise.amounts")

    def field_deadline(qid, cid, text):
        ds = [d for d in due(ContentItem.objects.get(pk=cid)) if d >= today]
        add("field", qid, text, {"values": [{"type": "date", "gold": ds[0].isoformat()}] if ds else [],
                                  "allowed": allowed_from(item_text(cid))},
            [f"item:{cid}"], "earliest ContentDeadline(kind=application, due_date>=today) of the tagged item")

    def field_venue(qid, cid, text):
        meta = ContentItem.objects.get(pk=cid).metadata or {}
        v = str(meta.get("venue") or "")
        add("field", qid, text, {"values": [{"type": "phrase", "alts": [v]}] if v else [],
                                  "allowed": allowed_from(item_text(cid))},
            [f"item:{cid}"], "metadata.venue of the tagged item")

    def field_authors(qid, cid, text):
        names = authors_of(cid)
        add("field", qid, text, {"values": [{"type": "phrase", "alts": [surname(a)], "author": a} for a in names],
                                  "allowed": allowed_from(item_text(cid))},
            [f"item:{cid}"], "metadata.authors of the tagged item; each surname must appear")

    field_amount("f01", "c4ffc4a1-77b2-4060-ada9-51f292bdd497", "How much funding does this call offer?")
    field_amount("f02", "292faa75-52a4-47d3-b44c-4342c364cb9a", "What is the funding range for this call?")
    field_amount("f03", "143a2bb8-abf0-426d-bb3b-db14f5756140", "How much can one award from this program be?")
    field_deadline("f04", "6eeec7f2-7fad-4197-a554-0fc8fb1fabee", "When is the application deadline for this call?")
    field_deadline("f05", "36b49619-9af9-4f8d-a073-ebf98a3328dd", "What is the deadline to apply to this call?")
    field_deadline("f06", "0f8b50a8-c940-45af-b5bd-8ad9a5d0d4e6", "When are applications for this fellowship due?")
    field_venue("f07", "410090eb-5b58-4c24-b735-361707b0057d", "Where was this paper published?")
    field_venue("f08", "d3ef7054-cc80-4f4a-891a-9876fc99e1ae", "Which journal published this paper?")
    field_authors("f09", "50626250-280b-405d-a93c-750f2894b7c7", "Who are the authors of this?")
    field_authors("f10", "7a0631d5-b422-48d9-ba65-6adfc0522437", "Who wrote this paper?")
    field_deadline("f11", "1aa0ebe1-339f-438d-b248-990dc3ded7bf", "When is this fellowship's deadline?")

    # 2. a filtered list from the lab's feed -----------------------------------
    def lst(qid, text, t, pred, query):
        objs = [item_obj(c.pk) for c in lab_slate(t) if pred(c)]
        add("list", qid, text, {"objects": objs}, (), f"lab slate (in_slate, target_lab) of type {t}: {query}")

    feb27, mar27 = month(2027, 2), month(2027, 3)
    dec26, jan27, apr27 = month(2026, 12), month(2027, 1), month(2027, 4)
    lst("l01", "Which grants in the lab's feed have an application deadline in February 2027?",
        "grant", lambda c: any_due_in(c, *feb27), "application deadline in 2027-02")
    lst("l02", "Which grants in the lab's feed close between today and 31 January 2027?",
        "grant", lambda c: any_due_in(c, today, date(2027, 1, 31)), "application deadline today..2027-01-31")
    lst("l03", "Which grants in the lab's feed have an application deadline in March 2027?",
        "grant", lambda c: any_due_in(c, *mar27), "application deadline in 2027-03")
    lst("l04", "Which fellowships in the lab's feed have a confirmed deadline before 1 January 2027?",
        "fellowship", lambda c: any_due_in(c, today, date(2026, 12, 31), confirmed_only=True),
        "confirmed application deadline today..2026-12-31")
    lst("l05", "Which fellowships in the lab's feed have a deadline in the next 30 days?",
        "fellowship", lambda c: any_due_in(c, today, today + timedelta(days=30)),
        "application deadline today..today+30 (any confidence)")
    lst("l06", "Which conferences in the lab's feed have a paper submission deadline in December 2026?",
        "conference", lambda c: any_due_in(c, *dec26, kinds=("manuscript",)), "manuscript deadline in 2026-12")
    lst("l07", "Which conferences in the lab's feed have a paper submission deadline in the next 10 days?",
        "conference", lambda c: any_due_in(c, today, today + timedelta(days=10), kinds=("manuscript",)),
        "manuscript deadline today..today+10")
    lst("l08", "Which grants in the lab's feed offer up to at least €40 million?",
        "grant", lambda c: max(N.amounts(str((c.metadata or {}).get("amount") or "")) or [0]) >= 40e6
        and "€" in str((c.metadata or {}).get("amount") or ""), "max parsed metadata.amount >= 40,000,000 EUR")
    lst("l09", "Which grants in the lab's feed state their funding in US dollars?",
        "grant", lambda c: "$" in str((c.metadata or {}).get("amount") or ""), "metadata.amount contains '$'")
    lst("l10", "Which fellowships in the lab's feed have a deadline in February 2027?",
        "fellowship", lambda c: any_due_in(c, *feb27), "application deadline in 2027-02")
    lst("l11", "Which conferences in the lab's feed take place in April 2027?",
        "conference", lambda c: any_due_in(c, *apr27, kinds=("event",)), "event date in 2027-04")
    lst("l12", "Which conferences in the lab's feed have a paper submission deadline in January 2027?",
        "conference", lambda c: any_due_in(c, *jan27, kinds=("manuscript",)), "manuscript deadline in 2027-01")

    # 3. a project's stored state ----------------------------------------------
    def prog(qid, p, text):
        g = (p.goals or {}).get("progress")
        add("project", qid, text, {"values": [{"type": "percent", "gold": float(g)}] if g is not None else [],
                                    "allowed": allowed_from(project_text(p))},
            (), f"Project({p.name}).goals.progress")

    def watched(qid, p, text):
        add("project", qid, text, {"values": [{"type": "phrase", "alts": [t]} for t in project_watch_topics(p)],
                                    "allowed": allowed_from(project_text(p))},
            (), f"project_watch_topics(Project({p.name}))")

    def on_project(qid, p, text):
        add("project", qid, text, {"objects": [person_obj(u) for u in p.members.all() if u.pk != pi.pk]},
            (), f"Project({p.name}).members minus the asker")

    def status(qid, p, text, alts):
        st = str((p.goals or {}).get("status") or "")
        ok = any(N.has_phrase(st, a) for a in alts)
        add("project", qid, text, {"values": [{"type": "phrase", "alts": alts}] if ok else [],
                                    "allowed": allowed_from(project_text(p)), "stored": st},
            (), f"Project({p.name}).goals.status contains one of {alts}")

    prog("s01", MHW, "How far along is the Marine heatwave early warning project?")
    prog("s02", PP, "What progress is recorded for the Plastic pathways project?")
    watched("s03", MHW, "Which topics does the Marine heatwave early warning project watch?")
    watched("s04", PP, "Which topics does the Plastic pathways project watch?")
    on_project("s05", MHW, "Who else, besides me, is on the Marine heatwave early warning project?")
    on_project("s06", PP, "Who else, besides me, is on the Plastic pathways project?")
    status("s07", MHW, "According to its status, which years do the Marine heatwave early warning project's hindcasts cover?",
           ["2015-2024", "2015 to 2024", "2015 through 2024"])
    status("s08", MHW, "According to its status, how far ahead do the Marine heatwave early warning project's hindcasts beat persistence?",
           ["four weeks", "4 weeks"])
    status("s09", PP, "According to its status, how often do the Plastic pathways project's satellite debris detections run?",
           ["weekly", "every week", "once a week"])
    status("s10", PP, "According to its status, what is the Plastic pathways project's beaching model being checked against?",
           ["beach surveys", "beach survey"])

    # 4. people -----------------------------------------------------------------
    def interest(qid, rx, text):
        add("people", qid, text, {"objects": [person_obj(u) for u in with_interest(rx)]},
            (), f"lab members other than the asker whose declared interest labels match /{rx}/i")

    def declared(qid, username, text):
        u = User.objects.get(username=username)
        person_text(username)
        add("people", qid, text, {"values": [{"type": "phrase", "alts": [lab_]} for lab_ in labels(u)]},
            (), f"interest_labels(profile of {username})")

    interest("p01", r"marine litter", "Who in the lab has declared an interest in marine litter?")
    interest("p02", r"satellite oceanography", "Who in the lab works on satellite oceanography, by their declared interests?")
    interest("p03", r"ocean data tools", "Which lab member has declared an interest in ocean data tools?")
    interest("p04", r"turbulence", "Who in the lab has declared an interest in turbulence?")
    interest("p05", r"coastal water quality", "Who in the lab lists coastal water quality among their interests?")
    interest("p06", r"lagrangian", "Which lab member has declared an interest in Lagrangian analysis?")
    interest("p07", r"\bML\b|machine learning", "Which lab members, other than me, declare an interest involving machine learning?")
    declared("p08", "demo.priya", "What research interests has Priya Raman declared?")
    declared("p09", "demo.tomas", "What research interests has Tomás Ferreira-Lind declared?")
    on_mhw = {u.pk for u in MHW.members.all()}
    add("people", "p10", "Which lab members are not on the Marine heatwave early warning project?",
        {"objects": [person_obj(u) for u in others if u.pk not in on_mhw]},
        (), "lab members minus Project(Marine heatwave early warning).members minus the asker")

    # 5. joins across kinds -----------------------------------------------------
    def watcher(topic):
        ps = [p for p in (MHW, PP) if topic in project_watch_topics(p)]
        assert len(ps) == 1, topic
        return ps[0]

    def member_project(username):
        ps = [p for p in (MHW, PP) if p.members.filter(username=username).exists()]
        assert len(ps) == 1, username
        return ps[0]

    for qid, topic in (("j01", "marine litter tracking"), ("j02", "marine heatwave prediction")):
        p = watcher(topic)
        add("join", qid, f"Which of our projects watches the topic '{topic}', and which paper ranks first in that project's feed?",
            {"objects": [project_obj(p)] + [item_obj(c.pk) for c in project_top(p, "paper")]},
            (), f"the project whose watch topics include '{topic}' + its slate's first paper (order_by_slate)")
    for qid, topic in (("j03", "ocean data dashboards"), ("j04", "satellite ocean remote sensing")):
        p = watcher(topic)
        add("join", qid, f"Which grant ranks first in the feed of the project that watches '{topic}'?",
            {"objects": [item_obj(c.pk) for c in project_top(p, "grant")]},
            (), f"first grant in the slate of the project watching '{topic}'")
    p = member_project("demo.jonah")
    add("join", "j05", "Which conference ranks first in the feed of the project Jonah Whitcombe works on?",
        {"objects": [item_obj(c.pk) for c in project_top(p, "conference")]}, (),
        "first conference in the slate of demo.jonah's only lab project")
    p = member_project("demo.sunhee")
    add("join", "j06", "Which fellowship ranks first in the feed of the project Sun-hee Park works on?",
        {"objects": [item_obj(c.pk) for c in project_top(p, "fellowship")]}, (),
        "first fellowship in the slate of demo.sunhee's only lab project")
    add("join", "j07", "Which members of the Marine heatwave early warning project, other than me, declare an interest involving machine learning?",
        {"objects": [person_obj(u) for u in with_interest(r"\bML\b|machine learning",
                                                           [u for u in MHW.members.all() if u.pk != pi.pk])]},
        (), "Project(MHW).members minus asker, declared interest matching /\\bML\\b|machine learning/i")
    top3 = {pp.pk: [c.pk for c in project_top(pp, "grant", 3)] for pp in (MHW, PP)}
    both = [cid for cid in top3[MHW.pk] if cid in top3[PP.pk]]
    add("join", "j08", "Which grants are in the top three of both projects' feeds?",
        {"objects": [item_obj(c) for c in both]}, (), "intersection of the first three grants of each project's slate")
    p = member_project("demo.priya")
    add("join", "j09", "What progress is recorded for the project Priya Raman works on?",
        {"objects": [project_obj(p)],
         "values": [{"type": "percent", "gold": float((p.goals or {}).get("progress"))}],
         "allowed": allowed_from(project_text(p))}, (),
        "demo.priya's only lab project + its goals.progress")
    cands = project_top(MHW, "grant", 3)
    firsts = sorted((min([d for d in due(c) if d >= today] or [date.max]), str(c.pk)) for c in cands)
    earliest = [cid for d, cid in firsts if d == firsts[0][0] and d != date.max]
    add("join", "j10", "Of the three top-ranked grants in the Marine heatwave early warning project's feed, which has the earliest application deadline?",
        {"objects": [item_obj(c) for c in earliest]}, (),
        "among the first three grants of Project(MHW)'s slate, the one(s) with the earliest future application deadline")

    # 6. unanswerable -----------------------------------------------------------
    def unans(qid, text, pattern, bodies, mentions=(), note=""):
        joined = "\n".join(bodies)
        if pattern == "AMOUNT":
            present = bool(N.amounts(joined))
        elif pattern == "PERCENT":
            present = bool(N.percents(joined))
        else:
            present = bool(re.search(PATTERNS[pattern], joined, re.I))
        if present:
            rejected.append({"id": qid, "why": f"fact pattern {pattern} present in the record"})
            return
        add("unanswerable", qid, text,
            {"unanswerable": {"pattern": pattern, "regex": PATTERNS.get(pattern),
                              "records_sha": sha(joined), "note": note}},
            mentions, f"absent: {pattern} matches none of the records the agent can read for this question")

    def tagged(cid):
        return item_text(cid), [f"item:{cid}"]

    for qid, cid, text in (
        ("u01", "d0691bc6-c114-41bb-96be-8c60b687474c", "How much funding does this call offer per award?"),
        ("u02", "e644da43-05ce-49a2-ac9c-5d62aa5bb7f7", "What is the award size for this call?"),
        ("u03", "435caf38-5230-42b5-8f9d-b32ca73d29e7", "What is the maximum award under this program?"),
    ):
        body, m = tagged(cid)
        unans(qid, text, "AMOUNT", [body], m, "no amount stored on the item")
    for qid, cid in (("u04", "3a964b7a-3e32-454f-b51a-efb81f17637b"), ("u05", "410090eb-5b58-4c24-b735-361707b0057d")):
        body, m = tagged(cid)
        meta = ContentItem.objects.get(pk=cid).metadata or {}
        if any("cit" in k.lower() for k in meta):
            rejected.append({"id": qid, "why": "metadata has a citation key"})
            continue
        unans(qid, "How many times has this paper been cited?", "cites", [body], m, "no citation count stored")
    body, m = tagged("4794d81a-76e1-4c10-8b0b-94807801df1e")
    unans("u06", "What was this conference's acceptance rate last year?", "PERCENT", [body], m, "no rate stored")
    unans("u07", "What is the Plastic pathways project's total budget?", "AMOUNT", [project_text(PP)], (),
          "no budget stored on the project")
    unans("u08", "What is Sun-hee Park's email address?", "email", [person_text("demo.sunhee")], (),
          "contact details are not stored for the agent and not visible to the asker")
    unans("u09", "What is Tomás Ferreira-Lind's phone number?", "phone", [person_text("demo.tomas")], (),
          "contact details are not stored for the agent and not visible to the asker")
    unans("u10", "What is Jonah Whitcombe's h-index?", "hindex", [person_text("demo.jonah")], (),
          "no bibliometrics stored")
    body, m = tagged("c4ffc4a1-77b2-4060-ada9-51f292bdd497")
    unans("u11", "How many proposals were submitted to this call last year?", "proposals", [body], m,
          "no submission statistics stored")
    unans("u12", "What is the Marine heatwave early warning project's total budget?", "AMOUNT", [project_text(MHW)], (),
          "no budget stored on the project")
    for qid, cid in (("u13", "1f62c961-e6ab-4a2c-b166-1c8f2040b7a8"), ("u14", "2e7975bf-11a0-43f9-84af-2af957e7b857")):
        body, m = tagged(cid)
        unans(qid, "What stipend does this fellowship pay?", "AMOUNT", [body], m, "no stipend stored")

    short = {k: len(v) for k, v in out.items() if len(v) < PER_KIND}
    if short:
        raise SystemExit(f"not enough valid questions: {short}; rejected: {rejected}")
    questions = [q for k in KINDS for q in out[k]]
    (HERE / "questions.json").write_text(json.dumps({
        "note": "EXP-2026-11-018. Built by code/build_gold.py and frozen before any answer was generated. "
                "Asked as the demo lab's fictional PI in lab scope. Mentions are item:<ContentItem id>.",
        "snapshot": snapshot, "today": today.isoformat(),
        "questions": [{k: q[k] for k in ("id", "kind", "text", "mentions", "scope")} for q in questions],
    }, indent=1, ensure_ascii=False) + "\n")
    (EXP / "data").mkdir(exist_ok=True)
    (EXP / "data" / "gold.json").write_text(json.dumps({
        "snapshot": snapshot, "today": today.isoformat(), "lab": lab.slug, "asker": pi.username,
        "rejected": rejected, "patterns": PATTERNS,
        "records_sha": {k: sha(v) for k, v in sorted(texts.items())},
        "questions": questions,
    }, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({"questions": len(questions), "rejected": rejected,
                      "gold_sizes": {q["id"]: len(q["gold"]["objects"]) + len(q["gold"]["values"]) for q in questions}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
