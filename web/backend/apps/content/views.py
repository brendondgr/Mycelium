from collections import Counter, defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import user_can_manage_lab, user_has_lab_access
from apps.core.people import display_name, initials
from apps.research.models import Project

from .collaboration import record_event
from .models import (
    ContentItem,
    DailyBriefing,
    MemberSuggestion,
    Notification,
    RelevanceEvent,
    RelevanceScore,
    SavedOpportunity,
)
from .onboarding_match import UnknownArea, onboarding_match_area
from .query_embedding import embed_query
from .scan_status import is_paper_scan_inflight
from .search import SearchFilters, normalize_query, run_search
from .serializers import (
    ConferenceSerializer,
    FellowshipSerializer,
    GrantSerializer,
    SavedDeadlineSerializer,
    SavedItemSerializer,
    SearchResultSerializer,
    SuggestionSerializer,
)

#: A suggestion at or above this percent match is called a "strong" match in the
#: daily summary. Kept here (not a setting) so the label logic stays with the view.
STRONG_MATCH_THRESHOLD = 75

#: A lab member counts as "interested" in a shared item when their *own* match for
#: it clears this percent — a confident personal fit, not a faint overlap.
INTEREST_MATCH_THRESHOLD = 70


class OnboardingMatchView(APIView):
    """Match one area for the signed-in user over the existing corpus (own only).

    Drives the post-onboarding live-match window: the frontend POSTs one area at a
    time (``papers`` | ``grants`` | ``fellowships`` | ``conferences``), each running
    that area's personalization over the already-scraped store — no scan/ingest —
    and persisting this user's scores so the workspace pages read them afterward.
    Returns ``{area, status, matched, llm, fallback, sample}``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        area = request.data.get("area")
        if not isinstance(area, str) or not area:
            return Response(
                {"detail": "area is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = onboarding_match_area(request.user, area)
        except UnknownArea:
            return Response(
                {"detail": f"Unknown area: {area}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class DailyReportView(APIView):
    """The signed-in user's daily research digest (own suggestions only).

    Returns two views of the most recent pipeline run — the rows the daily
    pipeline flagged ``suggested`` and stamped with a shared ``run_at``:

    - ``suggestions``: the ranked research papers (the Research Papers page).
    - ``summary``: a plain roll-up of the day's papers (the Daily Report page) —
      how many matched, how strongly, and the recurring themes. This is a
      deterministic summary of *today's* research; the richer cross-project,
      deadline-aware LLM synthesis is a later phase.

    Earlier runs' suggestions are ignored, so re-running the pipeline replaces
    the digest rather than piling onto it. An empty list (with
    ``generated_at: null``) is the honest "no run yet" state. ``scanning`` is true
    while a sign-up background scan is filling this user's feed (see
    :mod:`.scan_status`), so the page can say "scanning new articles for you".
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # A background scan (sign-up hybrid) may be filling this user's paper feed;
        # the page shows a "scanning" state while it runs. Best-effort: a Redis
        # outage reads as "not scanning".
        scanning = is_paper_scan_inflight(request.user)
        # Papers only: grants/conferences also persist suggested RelevanceScore
        # rows for this user, and they have their own pages (Opportunities /
        # Conferences). Filtering by content type keeps this feed to papers.
        scores = [
            score
            for score in RelevanceScore.objects.filter(
                target_user=request.user,
                content__type=ContentItem.Type.PAPER,
            ).select_related("content")
            if score.signals.get("suggested")
        ]
        if not scores:
            return Response(
                {
                    "generated_at": None,
                    "summary": None,
                    "suggestions": [],
                    "scanning": scanning,
                }
            )

        latest = max(score.signals.get("run_at", "") for score in scores)
        current = [s for s in scores if s.signals.get("run_at", "") == latest]
        today = timezone.now().date().isoformat()

        # Newly-gathered papers (pinned this week) lead the list; everything else
        # falls into plain percent-match / recommendation order below them, so a
        # paper drops out of the top zone once it is more than a week old.
        def sort_key(s: RelevanceScore):
            pinned_until = s.signals.get("pinned_until")
            pinned = bool(pinned_until and pinned_until >= today)
            return (0 if pinned else 1, s.signals.get("rank") or 999)

        current.sort(key=sort_key)
        return Response(
            {
                "generated_at": latest or None,
                "summary": _build_summary(current, today=today),
                "scanning": scanning,
                "suggestions": SuggestionSerializer(
                    current,
                    many=True,
                    context={
                        "today": today,
                        "saved_ids": _saved_content_ids(request.user),
                        "saved_labs": _saved_lab_slugs_by_content(request.user),
                        "cluster_labels": _user_cluster_labels(request.user),
                    },
                ).data,
            }
        )


def _build_summary(rows: list[RelevanceScore], *, today: str = "") -> dict:
    """Roll the matched papers up into the Daily Report summary.

    Deterministic on purpose: it reports the papers currently matching this
    researcher (count, how many are new this week, match strength, recurring focus
    themes, sources) without a second language-model call, so the summary is stable
    and always available. The paper feed is fresh-only (the latest gather batch), so
    ``new_count`` is what highlights this batch's brand-new arrivals.
    """
    matches = [
        m for m in (r.signals.get("match_percent") for r in rows) if isinstance(m, int)
    ]
    strong = sum(1 for m in matches if m >= STRONG_MATCH_THRESHOLD)

    def _is_new(row: RelevanceScore) -> bool:
        pinned_until = row.signals.get("pinned_until")
        return bool(row.signals.get("is_new")) and bool(
            pinned_until and pinned_until >= today
        )

    new_count = sum(1 for row in rows if _is_new(row))

    theme_counts: Counter[str] = Counter()
    for row in rows:
        for area in row.signals.get("focus_areas") or []:
            if isinstance(area, str) and area.strip():
                theme_counts[area.strip()] += 1
    themes = [area for area, _ in theme_counts.most_common(4)]

    sources: list[str] = []
    for row in rows:
        source = row.content.source
        if source and source not in sources:
            sources.append(source)

    count = len(rows)
    threshold = _match_threshold_percent()
    return {
        "paper_count": count,
        "new_count": new_count,
        "strong_matches": strong,
        "top_match": max(matches) if matches else None,
        "average_match": round(sum(matches) / len(matches)) if matches else None,
        # The embedding-match floor (percent) each surfaced paper had to clear, so the
        # UI can frame the count as "N papers met the X% match threshold".
        "match_threshold": threshold,
        "themes": themes,
        "sources": sources,
        "headline": _summary_headline(count, strong, threshold, new_count),
    }


def _match_threshold_percent() -> int:
    """The paper-feed embedding-match threshold as a whole percent, for display."""
    from django.conf import settings

    return round(getattr(settings, "PAPER_MATCH_THRESHOLD", 0.5) * 100)


def _summary_headline(count: int, strong: int, threshold: int, new_count: int) -> str:
    if count == 0:
        return "No papers currently clear your match threshold."
    papers = "paper" if count == 1 else "papers"
    lead = f"{count} {papers} match your interests (≥{threshold}%)"
    extras = []
    if new_count:
        extras.append(f"{new_count} new this week")
    if strong:
        extras.append(f"{strong} a strong match")
    if extras:
        return f"{lead} — {', '.join(extras)}."
    return f"{lead}."


class DailyBriefingView(APIView):
    """The signed-in user's "Mylo Report" — the Daily page's three-zone surface.

    Serves the durable :class:`DailyBriefing` the daily run's briefing stage
    wrote: the written 2–3 paragraph body, the per-category counts (top-right
    "Today's Summaries"), and the top showcase items the prose is grounded in
    (bottom-right). Own briefing only. An honest empty envelope
    (``generated_at: null``) is the "no run yet" state.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        briefing = DailyBriefing.objects.filter(user=request.user).first()
        return Response(_daily_briefing_envelope(briefing))


def _daily_briefing_envelope(briefing) -> dict:
    """The three-zone envelope for a ``DailyBriefing`` (or the empty "no run" one)."""
    if briefing is None:
        return {
            "generated_at": None,
            "categories": [],
            "counts": {},
            "new_counts": {},
            "showcase": {},
            "briefing": None,
        }
    return {
        "generated_at": briefing.generated_at.isoformat(),
        "categories": briefing.categories,
        "counts": briefing.counts,
        "new_counts": briefing.new_counts,
        "showcase": briefing.showcase,
        "briefing": {"body": briefing.body, "origin": briefing.origin},
    }


class LabDailyBriefingView(APIView):
    """A lab's "Mylo Report" — the lab overview's written briefing zone.

    Serves the durable :class:`DailyBriefing` keyed to the lab (the daily run's
    briefing stage also fans out to entitled labs). Any lab member may read it; an
    honest empty envelope is the "no run yet" state, same as the personal view.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        briefing = DailyBriefing.objects.filter(lab=lab).first()
        return Response(_daily_briefing_envelope(briefing))


# --------------------------------------------------------------------------- #
# Opportunities (grants + conferences), saves, deadlines, notifications
# --------------------------------------------------------------------------- #

#: A saved deadline this many days out (or fewer) triggers a notification alert.
DEADLINE_ALERT_DAYS = 7


def _saved_content_ids(user) -> set[str]:
    """The content ids the user saved **personally** (the ``saved`` flag per item).

    Lab saves are excluded (``target_lab__isnull=True``): the card's ``saved`` flag
    means "in my personal saves", while ``saved_labs`` carries the lab-save state.
    """
    return {
        str(cid)
        for cid in SavedOpportunity.objects.filter(
            user=user, content__isnull=False, target_lab__isnull=True
        ).values_list("content_id", flat=True)
    }


def _saved_lab_slugs_by_content(user) -> dict[str, list[str]]:
    """Map content id -> lab slugs (among labs the user **manages**) that saved it.

    Feeds the ``saved_labs`` flag so the save dropdown can show which of the
    caller's managed labs already hold each item. One query; grouped in Python.
    """
    managed_lab_ids = list(
        LabMembership.objects.filter(
            user=user,
            role__in=[LabMembership.Role.OWNER, LabMembership.Role.ADMIN],
        ).values_list("lab_id", flat=True)
    )
    if not managed_lab_ids:
        return {}
    out: dict[str, list[str]] = {}
    rows = (
        SavedOpportunity.objects.filter(
            target_lab_id__in=managed_lab_ids, content__isnull=False
        )
        .select_related("target_lab")
        .values_list("content_id", "target_lab__slug")
    )
    for content_id, slug in rows:
        out.setdefault(str(content_id), []).append(slug)
    return out


def _latest_scores(target_filter: dict, content_type: str) -> list[RelevanceScore]:
    """A target's matched items for the area, from the latest run, pinned-first.

    The **fresh-only** read, used for **papers**: the paper feed shows only the
    latest gather batch (see :func:`apps.content.pipeline.recommend_for_user`), so a
    re-run replaces the digest rather than piling onto it. ``target_filter`` is the
    single ``target_*`` FK to read under — ``{"target_user": user}`` for a person,
    ``{"target_lab": lab}`` / ``{"target_project": project}`` for the institutional
    feeds. Rows the matcher persisted but marked ``suggested=False`` (below the
    match-percent floor) are excluded — mirroring ``DailyReportView``'s own filter —
    so a hidden verdict never surfaces just because it is the latest run.
    """
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        ).select_related("content")
        if s.signals.get("suggested")
    ]
    if not scores:
        return []
    latest = max(s.signals.get("run_at", "") for s in scores)
    current = [s for s in scores if s.signals.get("run_at", "") == latest]
    today = timezone.now().date().isoformat()

    def sort_key(s: RelevanceScore):
        pinned_until = s.signals.get("pinned_until")
        pinned = bool(pinned_until and pinned_until >= today)
        return (0 if pinned else 1, s.signals.get("rank") or 999)

    current.sort(key=sort_key)
    return current


def _accumulated_scores(
    target_filter: dict, content_type: str, *, cap: int | None = None
) -> list[RelevanceScore]:
    """A target's matched **opportunities**, accumulated across every run.

    The **accumulate** read, used for grants / conferences / fellowships: the daily
    run scores only that day's *new* items and appends them (see
    :func:`apps.content.opportunities.run_daily_opportunities_batch`), so a feed is
    the union of every run's suggested rows — one per ``(content, target)`` — not
    just the latest run. Items leave the feed only when the underlying
    :class:`ContentItem` is pruned at its deadline (``CASCADE`` drops the score).

    Newly-pinned items lead; below them, strongest match first (then the raw score),
    so an older still-relevant grant keeps a stable place. Rows marked
    ``suggested=False`` (below the match-percent floor) are excluded. Capped by
    ``OPPORTUNITY_FEED_MAX`` as a payload backstop, since an accumulating feed can
    otherwise grow unbounded between prunes.
    """
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        )
        .select_related("content")
        .prefetch_related("content__deadline_rows")
        if s.signals.get("suggested")
    ]
    if not scores:
        return []
    today = timezone.now().date().isoformat()

    def sort_key(s: RelevanceScore):
        pinned_until = s.signals.get("pinned_until")
        pinned = bool(pinned_until and pinned_until >= today)
        match = s.signals.get("match_percent")
        match = match if isinstance(match, int) else -1
        return (0 if pinned else 1, -match, -s.score)

    scores.sort(key=sort_key)
    if cap is None:
        cap = getattr(settings, "OPPORTUNITY_FEED_MAX", 250)
    return scores[:cap]


def _generated_at(scores: list[RelevanceScore]) -> str | None:
    """The most recent ``run_at`` across a (possibly multi-run) set of rows."""
    run_ats = [s.signals.get("run_at") for s in scores if s.signals.get("run_at")]
    return max(run_ats) if run_ats else None


class _OpportunityFeedView(APIView):
    """Shared GET for a matched-opportunity feed (grants or conferences)."""

    permission_classes = [IsAuthenticated]
    content_type: str = ""
    serializer_class = None

    def get(self, request):
        scores = _accumulated_scores({"target_user": request.user}, self.content_type)
        context = {
            "today": timezone.now().date().isoformat(),
            "saved_ids": _saved_content_ids(request.user),
            "saved_labs": _saved_lab_slugs_by_content(request.user),
        }
        return Response(
            {
                "generated_at": _generated_at(scores),
                "items": self.serializer_class(scores, many=True, context=context).data,
            }
        )


class GrantsView(_OpportunityFeedView):
    """The signed-in user's ranked funding opportunities (Opportunities page)."""

    content_type = ContentItem.Type.GRANT
    serializer_class = GrantSerializer


class ConferencesView(_OpportunityFeedView):
    """The signed-in user's ranked conferences (Conferences page)."""

    content_type = ContentItem.Type.CONFERENCE
    serializer_class = ConferenceSerializer


class FellowshipsView(_OpportunityFeedView):
    """The signed-in user's matched fellowships (Fellowships page)."""

    content_type = ContentItem.Type.FELLOWSHIP
    serializer_class = FellowshipSerializer


# --------------------------------------------------------------------------- #
# Lab + project recommendation feeds (the institutional scoring targets)
# --------------------------------------------------------------------------- #


def _interested_members(member_ids, content_ids) -> dict[str, list[dict]]:
    """Map each item to the lab members whose *own* match for it is strong.

    The seed of collaboration suggestions: an item recommended to the lab also
    surfaced personally for these members (above :data:`INTEREST_MATCH_THRESHOLD`),
    so they are the people to connect over it. One query over the members' personal
    scores, grouped by content — no per-item lookups.
    """
    if not member_ids or not content_ids:
        return {}
    interested: dict[str, list[dict]] = defaultdict(list)
    scores = (
        RelevanceScore.objects.filter(
            target_user_id__in=member_ids, content_id__in=content_ids
        )
        .select_related("target_user")
        .order_by("-score")
    )
    for score in scores:
        match = score.signals.get("match_percent")
        if not isinstance(match, int) or match < INTEREST_MATCH_THRESHOLD:
            continue
        member = score.target_user
        interested[str(score.content_id)].append(
            {
                "username": member.get_username(),
                "name": display_name(member),
                "initials": initials(member),
                "match_percent": match,
            }
        )
    return interested


#: The eligibility tiers that count as "eligible" for a lab fellowship surface.
_ELIGIBLE_TIERS = ("qualified", "conditional")


def _lab_fellowship_card(content, eligible: list[dict]) -> dict:
    """A lab-visible fellowship card: public display fields + the eligible members.

    Deliberately reads only the fellowship's own metadata — never a member's personal
    match reasoning (``reason``/``gates_failed``/``fit``) — so nothing beyond the
    named members' consented eligibility is exposed to the lab.
    """
    meta = content.metadata or {}
    deadline = meta.get("deadline") or {}
    return {
        "content_id": str(content.id),
        "title": meta.get("title") or "Untitled fellowship",
        "url": meta.get("external_url") or meta.get("website") or content.source_url,
        "award_class": meta.get("award_class") or "fellowship",
        "amount": meta.get("amount_raw") or "",
        "deadline_date": meta.get("deadline_date") or "",
        "deadline_type": deadline.get("type") or meta.get("deadline_type") or "",
        "fields": (meta.get("facets") or {}).get("field") or [],
        "eligible": eligible,
    }


def _lab_fellowship_member_scores(member_ids):
    """Yield each member fellowship match that is **eligible** and **consenting**.

    The single gate the lab fellowship surface is built from (D-1/D-11): tier is
    qualified/conditional **and** the member opted into lab-visible eligibility
    (``interests.eligibility.lab_visible``, default off). Members who are ineligible,
    or eligible but not consenting, never appear. Shared by the card list and the
    time-window counts so both apply exactly the same disclosure rule.
    """
    if not member_ids:
        return
    scores = RelevanceScore.objects.filter(
        target_user_id__in=member_ids, content__type=ContentItem.Type.FELLOWSHIP
    ).select_related("content", "target_user", "target_user__profile")
    for score in scores:
        if score.signals.get("tier") not in _ELIGIBLE_TIERS:
            continue  # eligible only — an ineligible member is never surfaced
        member = score.target_user
        profile = getattr(member, "profile", None)
        interests = (profile.interests or {}) if profile else {}
        if not interests.get("eligibility", {}).get("lab_visible"):
            continue  # opt-in consent only
        yield score, member


def _lab_eligible_fellowships(member_ids) -> list[dict]:
    """Fellowships a lab can act on, named by their eligible **consenting** members.

    A fellowship "matches a lab" only as a union of member matches (see
    :func:`_lab_fellowship_member_scores`). This is the only place lab fellowships
    surface; the whole-corpus feed stays user-only.
    """
    content_by_id: dict[str, ContentItem] = {}
    members_by_content: dict[str, list[dict]] = defaultdict(list)
    for score, member in _lab_fellowship_member_scores(member_ids):
        cid = str(score.content_id)
        content_by_id[cid] = score.content
        members_by_content[cid].append(
            {
                "username": member.get_username(),
                "name": display_name(member),
                "initials": initials(member),
                "tier": score.signals.get("tier"),
            }
        )

    cards = [
        _lab_fellowship_card(content_by_id[cid], members_by_content[cid])
        for cid in content_by_id
    ]
    cards.sort(key=lambda c: (-len(c["eligible"]), c["title"]))
    return cards


def _count_windows(stamps, now) -> dict[str, int]:
    """Bucket a list of ``created_at`` datetimes into cumulative recency windows.

    Returns ``{today, week, month, year}`` where each larger window includes the
    smaller ones (today ≤ week ≤ month ≤ year), so the lab overview can show "found
    today / this week / this month / this year" as honest monotonic totals.
    """
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    year = now - timedelta(days=365)
    counts = {"today": 0, "week": 0, "month": 0, "year": 0}
    for ts in stamps:
        if ts is None or ts < year:
            continue
        counts["year"] += 1
        if ts >= month:
            counts["month"] += 1
        if ts >= week:
            counts["week"] += 1
        if ts >= start_today:
            counts["today"] += 1
    return counts


def _window_counts(target_filter: dict, member_ids) -> dict[str, dict[str, int]]:
    """Per-area today/week/month/year counts for a target's matched items.

    Papers/grants/conferences count the target's own suggested ``RelevanceScore``
    rows by their insert time (``created_at`` — when Mylo scored/appended it for the
    target). Fellowships count the distinct fellowships surfaced to the lab (union of
    eligible, consenting member matches), dated by when each first entered that
    surface. Empty windows are still reported as zeroes.
    """
    now = timezone.now()
    counts: dict[str, dict[str, int]] = {}
    for key, ctype in (
        ("papers", ContentItem.Type.PAPER),
        ("grants", ContentItem.Type.GRANT),
        ("conferences", ContentItem.Type.CONFERENCE),
    ):
        rows = RelevanceScore.objects.filter(
            **target_filter, content__type=ctype
        ).values_list("created_at", "signals")
        stamps = [ca for ca, sig in rows if (sig or {}).get("suggested")]
        counts[key] = _count_windows(stamps, now)

    # A lab fellowship is dated by when it first entered the consented union.
    earliest: dict[str, object] = {}
    for score, _member in _lab_fellowship_member_scores(member_ids):
        cid = str(score.content_id)
        if cid not in earliest or score.created_at < earliest[cid]:
            earliest[cid] = score.created_at
    counts["fellowships"] = _count_windows(list(earliest.values()), now)
    return counts


def _personal_window_counts(user) -> dict[str, dict[str, int]]:
    """Per-area today/week/month/year counts for a user's own matched items.

    Unlike a lab, fellowships are already scored directly to ``target_user``
    (fellowships stay user-only), so all four areas read the same
    ``target_user`` filter — no member-union step needed.
    """
    now = timezone.now()
    counts: dict[str, dict[str, int]] = {}
    for key, ctype in (
        ("papers", ContentItem.Type.PAPER),
        ("grants", ContentItem.Type.GRANT),
        ("conferences", ContentItem.Type.CONFERENCE),
        ("fellowships", ContentItem.Type.FELLOWSHIP),
    ):
        rows = RelevanceScore.objects.filter(
            target_user=user, content__type=ctype
        ).values_list("created_at", "signals")
        stamps = [ca for ca, sig in rows if (sig or {}).get("suggested")]
        counts[key] = _count_windows(stamps, now)
    return counts


class PersonalWindowCountsView(APIView):
    """The signed-in user's own "what Mylo found" recency matrix (personal Overview)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"window_counts": _personal_window_counts(request.user)})


def _user_cluster_labels(user) -> dict[str, str]:
    """``cluster_id -> current label`` for a user's own clusters (badge labels).

    Passed as serializer context so a renamed cluster shows its new label on every
    card without a re-score; empty for a v1 / single-cluster profile.
    """
    from .clustering import cluster_labels

    profile = getattr(user, "profile", None)
    return cluster_labels(getattr(profile, "interests", None))


def _target_cluster_labels(target_filter: dict) -> dict[str, str]:
    """``cluster_id -> current label`` for a lab / project paper feed.

    Labs carry clusters on their ``LabProfile.interests``; projects rarely do, so
    the serializer's frozen-label fallback covers them.
    """
    from .clustering import cluster_labels

    lab = target_filter.get("target_lab")
    if lab is not None:
        profile = getattr(lab, "profile", None)
        return cluster_labels(getattr(profile, "interests", None))
    return {}


def _attach_search_clusters(items, user) -> None:
    """Best-effort ``· Cluster`` attribution for search hits (mutates in place).

    Search is query-first (no per-target score), so a result carries no persisted
    cluster. For a reader with >= 2 clusters we attribute each hit to the cluster
    whose areas best overlap its title/abstract — the same cheap lexical signal the
    focus re-rank uses — so search cards show the same attribution as the feed.
    Papers-first: off-type items rarely overlap and stay unattributed.
    """
    from .clustering import cluster_interests
    from .ranking import focus_overlap

    profile = getattr(user, "profile", None)
    clusters = [
        c
        for c in cluster_interests(getattr(profile, "interests", None))
        if not c.is_implicit
    ]
    if len(clusters) < 2:
        return
    for item in items:
        best = None
        best_frac = 0.0
        for cluster in clusters:
            frac, _matched = focus_overlap(cluster.areas, item)
            if frac > best_frac:
                best_frac = frac
                best = cluster
        if best is not None:
            item._cluster = {"id": best.id, "label": best.label}


# The per-area caps for a project's short-list digest — the condensed "Mylo's
# picks for this project" surface (the full feeds are uncapped beyond the payload
# backstop). Papers get the deepest slice since they are the highest-volume area.
DIGEST_CAPS = {"papers": 10, "grants": 5, "fellowships": 5, "conferences": 5}


def _drop_passed_conferences(scores: list[RelevanceScore], today: str) -> list:
    """Conferences whose next deadline has not already passed (empty = keep).

    A conference with a stored ``deadline_date`` strictly before today is no longer
    actionable, so the digest drops it; an unknown/blank deadline is kept (we don't
    hide something we can't date)."""
    out = []
    for s in scores:
        deadline = s.signals.get("deadline_date") or ""
        if not deadline or deadline >= today:
            out.append(s)
    return out


def _recommendations_payload(
    target_filter: dict,
    *,
    user,
    member_ids=(),
    project_fellowships: bool = False,
    digest: bool = False,
) -> dict:
    """The combined papers + grants + conferences + fellowships a lab / project matched.

    ``counts`` powers the overview stat cards; the lists power the feeds.
    ``interested`` maps each paper/grant/conference to the members who personally
    matched it strongly (from ``member_ids``).

    Fellowships differ by scope. For a **lab** they are individual by nature (D-1),
    so they surface only as a union of member matches, named by the eligible members
    who consented to lab-visible eligibility (``_lab_eligible_fellowships``) — never
    who was ineligible (D-11). For a **project** (``project_fellowships=True``) they
    are the project's own interest-matched fellowships scored under
    ``target_project`` (no personal eligibility involved), rendered with the normal
    fellowship card.

    ``digest`` returns the condensed short list — top ``DIGEST_CAPS`` per area, with
    passed-deadline conferences dropped — for the per-project "Mylo's picks" block.
    ``counts`` stays the full totals so the UI can say "top 5 of N". Saves remain
    personal, so ``saved`` reflects the signed-in user regardless of scope.
    """
    today = timezone.now().date().isoformat()
    opp_context = {
        "today": today,
        "saved_ids": _saved_content_ids(user),
        "saved_labs": _saved_lab_slugs_by_content(user),
    }
    # Papers are fresh-only (latest gather batch); opportunities accumulate.
    papers = _latest_scores(target_filter, ContentItem.Type.PAPER)
    grants = _accumulated_scores(target_filter, ContentItem.Type.GRANT)
    conferences = _accumulated_scores(target_filter, ContentItem.Type.CONFERENCE)
    if digest:
        conferences = _drop_passed_conferences(conferences, today)

    if project_fellowships:
        fellowship_scores = _accumulated_scores(
            target_filter, ContentItem.Type.FELLOWSHIP
        )
        fellowship_count = len(fellowship_scores)
    else:
        fellowship_union = _lab_eligible_fellowships(list(member_ids))
        fellowship_count = len(fellowship_union)

    # Full counts (before any digest slice) so the UI can show "top N of total".
    counts = {
        "papers": len(papers),
        "grants": len(grants),
        "conferences": len(conferences),
        "fellowships": fellowship_count,
    }

    if digest:
        papers = papers[: DIGEST_CAPS["papers"]]
        grants = grants[: DIGEST_CAPS["grants"]]
        conferences = conferences[: DIGEST_CAPS["conferences"]]
        if project_fellowships:
            fellowship_scores = fellowship_scores[: DIGEST_CAPS["fellowships"]]

    if project_fellowships:
        fellowships_data = FellowshipSerializer(
            fellowship_scores, many=True, context=opp_context
        ).data
    else:
        fellowships_data = fellowship_union

    content_ids = [s.content_id for s in (*papers, *grants, *conferences)]
    return {
        "generated_at": _generated_at([*papers, *grants, *conferences]),
        "counts": counts,
        # Per-area today/week/month/year totals for the overview stats block.
        "window_counts": _window_counts(target_filter, list(member_ids)),
        "papers": SuggestionSerializer(
            papers,
            many=True,
            context={
                "today": today,
                "cluster_labels": _target_cluster_labels(target_filter),
            },
        ).data,
        "grants": GrantSerializer(grants, many=True, context=opp_context).data,
        "conferences": ConferenceSerializer(
            conferences, many=True, context=opp_context
        ).data,
        "fellowships": fellowships_data,
        "interested": _interested_members(list(member_ids), content_ids),
    }


class LabRecommendationsView(APIView):
    """A lab's matched papers/grants/conferences (its aggregate interests).

    Any member of the lab may read them (``user_has_lab_access``); the lab overview
    reads ``counts`` and a lab feed reads the lists.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        member_ids = LabMembership.objects.filter(lab=lab).values_list(
            "user_id", flat=True
        )
        return Response(
            _recommendations_payload(
                {"target_lab": lab}, user=request.user, member_ids=member_ids
            )
        )


class ProjectRecommendationsView(APIView):
    """One project's matched papers/grants/conferences (its declared focus).

    Gated by the same cascade visibility that guards the project itself, so only
    people who can see the project can see what Mylo found for it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        if not project.is_visible_to(request.user):
            raise PermissionDenied("You do not have access to this project.")
        # "Interested" members come from the project's lab (a lab project) or its
        # own members (a personal project) — the people to connect over an item.
        if project.scope_lab_id is not None:
            member_ids = LabMembership.objects.filter(
                lab_id=project.scope_lab_id
            ).values_list("user_id", flat=True)
        else:
            member_ids = project.members.values_list("id", flat=True)
        digest = request.query_params.get("digest") in ("1", "true", "yes")
        return Response(
            _recommendations_payload(
                {"target_project": project},
                user=request.user,
                member_ids=member_ids,
                project_fellowships=True,
                digest=digest,
            )
        )


class SaveOpportunityView(APIView):
    """Save (POST) or unsave (DELETE) a bookmarkable item for the Saves page."""

    permission_classes = [IsAuthenticated]

    _SAVEABLE_TYPES = [
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
        ContentItem.Type.PAPER,
    ]

    def post(self, request):
        content_id = request.data.get("content_id")
        if not content_id:
            return Response(
                {"detail": "content_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item = ContentItem.objects.filter(
            id=content_id,
            type__in=self._SAVEABLE_TYPES,
        ).first()
        if item is None:
            return Response(
                {"detail": "No such paper, grant, conference, or fellowship."},
                status=status.HTTP_404_NOT_FOUND,
            )
        lab, error = self._resolve_lab(request)
        if error is not None:
            return error
        saved = _save_from_item(
            request.user, item, note=request.data.get("note", ""), target_lab=lab
        )
        context = {"today_date": timezone.now().date()}
        return Response(
            SavedDeadlineSerializer(saved, context=context).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, content_id):
        lab, error = self._resolve_lab(request)
        if error is not None:
            return error
        if lab is not None:
            qs = SavedOpportunity.objects.filter(
                target_lab=lab, content_id=content_id
            )
        else:
            qs = SavedOpportunity.objects.filter(
                user=request.user, target_lab__isnull=True, content_id=content_id
            )
        deleted, _ = qs.delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _resolve_lab(self, request):
        """Resolve an optional lab target (``lab_slug`` body / ``lab`` query).

        Returns ``(lab, None)`` — ``lab`` null for a personal save — or
        ``(None, Response)`` when the lab is unknown or the caller can't manage it.
        Only a lab manager (owner/admin/PI) may save to or unsave from a lab.
        """
        slug = request.data.get("lab_slug") or request.query_params.get("lab")
        if not slug:
            return None, None
        lab = Lab.objects.filter(slug=slug).first()
        if lab is None:
            return None, Response(
                {"detail": "No such lab."}, status=status.HTTP_404_NOT_FOUND
            )
        if not user_can_manage_lab(request.user, lab):
            return None, Response(
                {"detail": "Only a lab manager can save to a lab."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return lab, None


def _save_from_item(
    user, item: ContentItem, *, note: str, target_lab=None
) -> SavedOpportunity:
    """Create/update a save, snapshotting the display + deadline fields.

    ``target_lab`` null saves to ``user``'s personal workspace; otherwise it saves
    to the lab (``user`` records who added it). The unique keys mean a repeat save
    updates the existing row in place rather than duplicating.
    """
    meta = item.metadata or {}

    if item.type == ContentItem.Type.GRANT:
        area = SavedOpportunity.Area.GRANT
        title = meta.get("title") or "Untitled grant"
        subtitle = meta.get("sponsor") or ""
        url = meta.get("website") or item.source_url or ""
    elif item.type == ContentItem.Type.FELLOWSHIP:
        area = SavedOpportunity.Area.FELLOWSHIP
        title = meta.get("title") or "Untitled fellowship"
        # award_class is "fellowship" / "scholarship" / etc. — title-case for display.
        subtitle = (meta.get("award_class") or "fellowship").replace("_", " ").title()
        url = meta.get("external_url") or meta.get("website") or item.source_url or ""
    elif item.type == ContentItem.Type.PAPER:
        area = SavedOpportunity.Area.PAPER
        title = meta.get("title") or "Untitled paper"
        subtitle = meta.get("venue") or item.source or ""
        url = meta.get("pdf_url") or item.source_url or ""
    else:
        area = SavedOpportunity.Area.CONFERENCE
        title = meta.get("name") or "Untitled conference"
        subtitle = ", ".join(
            p for p in (meta.get("location"), meta.get("country")) if p
        )
        url = meta.get("website") or item.source_url or ""

    defaults = {
        "area": area,
        "title": title,
        "url": url,
        "subtitle": subtitle,
        "deadline_date": meta.get("deadline_date") or None,
        "deadline_kind": (
            meta.get("next_kind") or SavedOpportunity.DeadlineKind.OTHER
        ),
        "snapshot": meta,
        "note": note or "",
    }
    if target_lab is not None:
        # Lab save: keyed on (target_lab, content) so any manager updates one row;
        # ``user`` follows the latest saver.
        saved, _ = SavedOpportunity.objects.update_or_create(
            target_lab=target_lab,
            content=item,
            defaults={**defaults, "user": user},
        )
    else:
        # Personal save: keyed on (user, content), personal only.
        saved, _ = SavedOpportunity.objects.update_or_create(
            user=user,
            content=item,
            target_lab__isnull=True,
            defaults={**defaults, "target_lab": None},
        )
    # Round-trip so date/enum fields are proper types (not the raw strings just
    # written) before the row is serialized back in the response.
    saved.refresh_from_db()
    return saved


class DeadlinesView(APIView):
    """All the signed-in user's saved deadlines, soonest first (Deadlines page)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved = SavedOpportunity.objects.filter(user=request.user)
        context = {"today_date": timezone.now().date()}
        return Response(
            {"items": SavedDeadlineSerializer(saved, many=True, context=context).data}
        )


class SavedItemsView(APIView):
    """All the signed-in user's bookmarks, with feed-card parity (Saves page).

    Each save is joined back to the user's :class:`RelevanceScore` for the item
    (unique per ``(content, user)``), so the response carries the exact card
    payload the item's own feed page renders — grants look like the Grants page,
    fellowships like the Fellowships page, and so on. When the source item was
    pruned (or never scored for this user) the ``card`` is ``null`` and the save
    snapshot fields are all the client has to render.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        saves = list(
            SavedOpportunity.objects.filter(user=request.user)
            .select_related("content")
            .prefetch_related("content__deadline_rows")
            .order_by("-created_at")
        )
        content_ids = [s.content_id for s in saves if s.content_id]
        scores_by_content = {
            score.content_id: score
            for score in RelevanceScore.objects.filter(
                target_user=request.user,
                content_id__in=content_ids,
                content__isnull=False,
            )
            .select_related("content")
            .prefetch_related("content__deadline_rows")
        }
        today = timezone.now().date()
        context = {
            "today": today.isoformat(),
            "today_date": today,
            "saved_ids": {str(cid) for cid in content_ids},
            "saved_labs": _saved_lab_slugs_by_content(request.user),
            "scores_by_content": scores_by_content,
            "cluster_labels": _user_cluster_labels(request.user),
        }
        return Response(
            {"items": SavedItemSerializer(saves, many=True, context=context).data}
        )


class LabSavedItemsView(APIView):
    """A lab's shared bookmarks, with feed-card parity (lab Saves area).

    Any lab member may read them (``user_has_lab_access``); the card payloads are
    built from the **lab's** :class:`RelevanceScore` rows, falling back to the save
    snapshot when the item was never scored for the lab or has been pruned. The
    envelope carries ``can_manage`` so the client can gate the save/remind/remove
    affordances to managers (who alone may mutate a lab save).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        lab = Lab.objects.filter(slug=slug).first()
        if lab is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not user_has_lab_access(request.user, lab):
            return Response(
                {"detail": "You don't have access to that lab."},
                status=status.HTTP_403_FORBIDDEN,
            )
        saves = list(
            SavedOpportunity.objects.filter(target_lab=lab)
            .select_related("content")
            .prefetch_related("content__deadline_rows")
            .order_by("-created_at")
        )
        content_ids = [s.content_id for s in saves if s.content_id]
        scores_by_content = {
            score.content_id: score
            for score in RelevanceScore.objects.filter(
                target_lab=lab,
                content_id__in=content_ids,
                content__isnull=False,
            )
            .select_related("content")
            .prefetch_related("content__deadline_rows")
        }
        today = timezone.now().date()
        context = {
            "today": today.isoformat(),
            "today_date": today,
            # The card's ``saved`` flag stays personal-scoped for consistency; the
            # lab-save state travels on ``saved_labs``.
            "saved_ids": _saved_content_ids(request.user),
            "saved_labs": _saved_lab_slugs_by_content(request.user),
            "scores_by_content": scores_by_content,
            "cluster_labels": _target_cluster_labels({"target_lab": lab}),
        }
        return Response(
            {
                "can_manage": user_can_manage_lab(request.user, lab),
                "items": SavedItemSerializer(saves, many=True, context=context).data,
            }
        )


class NotificationsView(APIView):
    """The header bell, now backed by the ``Notification`` model (reminders rework).

    Three sources, one bell: a fired reminder, a moved deadline, and a high-signal
    recommendation (§10). Replaces the old on-the-fly "saves due within a week" scan —
    saving no longer produces an alert (D-3); a reminder created *from* a save does.
    Returns undismissed notifications, newest first, with the unread count.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(
            user=request.user, dismissed_at__isnull=True
        ).order_by("-created_at")[:50]
        items = [_notification_dict(n) for n in qs]
        count = Notification.objects.filter(
            user=request.user, dismissed_at__isnull=True, read_at__isnull=True
        ).count()
        return Response({"count": count, "items": items})


class NotificationActionView(APIView):
    """Mark one notification read or dismissed (POST ``{"action": ...}``)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        note = Notification.objects.filter(user=request.user, pk=pk).first()
        if note is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        now = timezone.now()
        if (request.data.get("action") or "read") == "dismiss":
            note.dismissed_at = note.dismissed_at or now
            note.read_at = note.read_at or now
            note.save(update_fields=["dismissed_at", "read_at"])
        else:
            note.read_at = note.read_at or now
            note.save(update_fields=["read_at"])
        return Response(_notification_dict(note))


def _notification_dict(note: Notification) -> dict:
    return {
        "id": str(note.id),
        "kind": note.kind,
        "content_id": str(note.content_id) if note.content_id else None,
        "title": note.title,
        "body": note.body,
        "url": note.url,
        "created_at": note.created_at.isoformat(),
        "read_at": note.read_at.isoformat() if note.read_at else None,
    }


# --------------------------------------------------------------------------- #
# Unified search
# --------------------------------------------------------------------------- #

#: The content types search accepts as a `type` filter (all of them).
_SEARCH_TYPES = set(ContentItem.Type.values)


def _multi_param(query_params, key: str) -> tuple[str, ...]:
    """Collect a repeatable/comma-separated query param into a clean tuple.

    Supports both ``?type=paper&type=grant`` and ``?type=paper,grant``; blanks
    are dropped and order-preserving duplicates collapse.
    """
    values: list[str] = []
    seen: set[str] = set()
    for raw in query_params.getlist(key):
        for part in str(raw).split(","):
            item = part.strip()
            if item and item not in seen:
                seen.add(item)
                values.append(item)
    return tuple(values)


def _parse_date(value: str | None):
    """Parse an ISO date, or ``None`` when it is missing/malformed (lenient)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except (ValueError, AttributeError):
        return None


def _parse_offset(query_params) -> int:
    """Read the paging cursor (an opaque non-negative offset) from the request."""
    raw = query_params.get("cursor") or query_params.get("offset") or "0"
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


class SearchView(APIView):
    """Query-first search across the content corpus (papers/grants/etc.).

    ``GET /api/search/?q=…`` runs the shared retrieval pipeline query-first (see
    :mod:`apps.content.search`) over the **global** corpus — the same items the
    opportunity feeds surface post-match — so it reads no lab-scoped data and
    requires only authentication. Query params: ``q`` (required — blank returns an
    empty result, not an error), repeatable/comma ``type``, the per-type facet
    filters ``year``/``sponsor``/``award_class``/``country`` (each scopes to its
    own type), ``date_from``/``date_to`` (ISO, on ingest date), ``sort``
    (relevance|date|deadline), ``limit``, and ``cursor`` (opaque offset). Search
    never abstains; ``confidence`` is a display cue only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        query = params.get("q", "")

        types = tuple(t for t in _multi_param(params, "type") if t in _SEARCH_TYPES)
        filters = SearchFilters(
            types=types,
            years=_multi_param(params, "year"),
            sponsors=_multi_param(params, "sponsor"),
            award_classes=_multi_param(params, "award_class"),
            countries=_multi_param(params, "country"),
            date_from=_parse_date(params.get("date_from")),
            date_to=_parse_date(params.get("date_to")),
        )

        # Embed the query in the shared corpus space for the semantic channel
        # (cached by normalized query in Phase 3). The embedder is the slow part,
        # so the view owns it while the search module stays embedder-free.
        normalized = normalize_query(query)
        query_vector = embed_query(normalized) if normalized else None

        result = run_search(
            query,
            filters=filters,
            sort=params.get("sort", "relevance"),
            limit=params.get("limit"),
            offset=_parse_offset(params),
            query_vector=query_vector,
        )

        saved_ids = _saved_content_ids(request.user) if result.items else set()
        saved_labs = (
            _saved_lab_slugs_by_content(request.user) if result.items else {}
        )
        if result.items:
            _attach_search_clusters(result.items, request.user)
        serializer = SearchResultSerializer(
            result.items,
            many=True,
            context={"saved_ids": saved_ids, "saved_labs": saved_labs},
        )
        return Response(
            {
                "query": result.query,
                "normalized": result.normalized,
                "sort": result.sort,
                "confidence": result.confidence,
                "count": result.count,
                "pool_truncated": result.pool_truncated,
                "facets": result.facets,
                "limit": result.limit,
                "offset": result.offset,
                "next_cursor": (
                    str(result.next_offset)
                    if result.next_offset is not None
                    else None
                ),
                "results": serializer.data,
            }
        )


# --------------------------------------------------------------------------- #
# Cross-member suggestions (Feature F — the in-app fan-out surface)
# --------------------------------------------------------------------------- #


def _suggestion_payload(suggestion: MemberSuggestion) -> dict:
    """One in-app suggestion for the bell / Suggested-for-you list."""
    meta = (suggestion.content.metadata or {}) if suggestion.content_id else {}
    share = suggestion.origin_share
    shared_by = share.shared_by if (share and share.shared_by_id) else None
    return {
        "id": str(suggestion.id),
        "content_id": str(suggestion.content_id),
        "title": meta.get("title") or meta.get("name") or "Untitled",
        "url": meta.get("pdf_url")
        or (suggestion.content.source_url if suggestion.content_id else "")
        or "",
        "score": round(suggestion.score, 3),
        "match_percent": round(suggestion.score * 100),
        "project": {
            "id": str(suggestion.project_id),
            "name": suggestion.project.name,
        },
        "shared_by": (
            {
                "username": shared_by.get_username(),
                "name": display_name(shared_by),
                "initials": initials(shared_by),
            }
            if shared_by
            else None
        ),
        "created_at": suggestion.created_at.isoformat(),
    }


class MemberSuggestionsView(APIView):
    """Papers teammates shared that match the signed-in user (Feature F, in-app).

    Only ``suggested=True`` (above-floor) and undismissed rows — the abstentions are
    persisted for audit but never surfaced.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        suggestions = (
            MemberSuggestion.objects.filter(
                user=request.user, suggested=True, dismissed=False
            )
            .select_related("content", "project", "origin_share__shared_by")
            .order_by("-created_at")
        )
        items = [_suggestion_payload(s) for s in suggestions]
        return Response({"count": len(items), "items": items})


class MemberSuggestionDismissView(APIView):
    """Dismiss an in-app suggestion (records a ``dismiss`` engagement event)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        suggestion = get_object_or_404(MemberSuggestion, pk=pk, user=request.user)
        if not suggestion.dismissed:
            suggestion.dismissed = True
            suggestion.save(update_fields=["dismissed"])
            record_event(
                request.user,
                suggestion.content,
                RelevanceEvent.Action.DISMISS,
                project=suggestion.project,
            )
        return Response({"id": str(suggestion.id), "dismissed": True})
