from collections import Counter, defaultdict
from datetime import date, timedelta

from apps.accounts import capabilities as caps
from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import (
    lab_manager_q,
    user_can_manage_lab,
    user_has_lab_access,
)
from apps.core.people import display_name, initials
from apps.research.models import Project
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tools.delivery import usability
from tools.delivery.collaboration import record_event
from tools.delivery.models import (
    DailyBriefing,
    IgnoredItem,
    MemberSuggestion,
    Notification,
    SavedOpportunity,
)
from tools.delivery.serializers import (
    _SAVED_CARD_SERIALIZERS,
    RANK_EXPLANATIONS,
    RANK_SYSTEM_INFO,
    ConferenceSerializer,
    FellowshipSerializer,
    GrantSerializer,
    IgnoredItemSerializer,
    SavedDeadlineSerializer,
    SavedItemSerializer,
    SearchResultSerializer,
    SuggestionSerializer,
)
from tools.recommendation.models import RelevanceEvent, RelevanceScore
from tools.recommendation.onboarding_match import UnknownArea, onboarding_match_area
from tools.recommendation.scan_status import is_paper_scan_inflight
from tools.recommendation.verdicts import READ, SKIM, VERDICTS
from tools.retrieval.liveness import is_live
from tools.retrieval.models import ContentItem
from tools.retrieval.search import SearchFilters

#: A suggestion at or above this percent match is called a "strong" match in the
#: daily summary. Kept here (not a setting) so the label logic stays with the view.
STRONG_MATCH_THRESHOLD = 75

#: A lab member counts as "interested" in a shared item when their *own* match for
#: it clears this percent — a confident personal fit, not a faint overlap.
INTEREST_MATCH_THRESHOLD = 70
#: The verdicts that mean a member is already looking at an item on their own feed.
_INTERESTED_VERDICTS = (READ, SKIM)


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
    Papers the reader manually ignored are dropped, here and in the summary built
    from the same list.
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
        ignored = _ignored_content_ids(request.user)
        scores = [
            score
            for score in RelevanceScore.objects.filter(
                target_user=request.user,
                content__type=ContentItem.Type.PAPER,
            ).select_related("content")
            if score.signals.get("suggested") and score.content_id not in ignored
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
    # "Strong" is now a verdict, not a number: a percent implied a measurement
    # nobody made, and the verdict says the same useful thing on both the paid and
    # the deterministic path.
    verdicts = Counter(
        v for v in (r.signals.get("verdict") for r in rows) if isinstance(v, str)
    )
    strong = verdicts.get(READ, 0)

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
        # How many of each verdict the feed currently holds, so the page can say
        # "3 worth reading, 12 to skim" instead of an average of a number that
        # measured nothing.
        "verdict_counts": {v: verdicts.get(v, 0) for v in VERDICTS},
        # The embedding-match floor (percent) each surfaced paper had to clear. Not
        # a relevance claim about any one item — it is what got them into the feed.
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
    lead = f"{count} {papers} match your interests"
    extras = []
    if new_count:
        extras.append(f"{new_count} new this week")
    if strong:
        extras.append(f"{strong} worth reading")
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
        briefing = DailyBriefing.latest_for(_requested_kind(request), user=request.user)
        return Response(_daily_briefing_envelope(briefing))


def _daily_briefing_envelope(briefing) -> dict:
    """The three-zone envelope for a ``DailyBriefing`` (or the empty "no run" one)."""
    if briefing is None:
        return {
            "generated_at": None,
            "generated_on": None,
            "categories": [],
            "counts": {},
            "new_counts": {},
            "showcase": {},
            "project_summary": [],
            "stats": {},
            "kind": "daily",
            "briefing": None,
        }
    return {
        "generated_at": briefing.generated_at.isoformat(),
        "generated_on": briefing.generated_on.isoformat(),
        "categories": briefing.categories,
        "counts": briefing.counts,
        "new_counts": briefing.new_counts,
        "showcase": briefing.showcase,
        # The report's summary table: Personal first, then one row per project.
        # Empty for a briefing written before the table existed, which the card
        # reads as "no table" rather than "no projects".
        "project_summary": briefing.project_summary or [],
        # The run's statistics, as the Discord post carries them (plan 1.5). Read
        # from the row rather than re-derived, so the header and the post cannot
        # quote different numbers for the same morning. Empty on a briefing
        # written before statistics existed.
        "stats": briefing.stats or {},
        # What the report was written against (ambient Plan 05): a digest of the
        # declared profile, confirmed understanding and developments in effect.
        "context_version": briefing.context_version or "",
        "kind": briefing.kind,
        "briefing": {"body": briefing.body, "origin": briefing.origin},
    }


def _briefing_summary(briefing) -> dict:
    """One row of the briefing index — the date and its headline numbers.

    Deliberately body-free: the index is a navigation list and may span the whole
    retention window, so shipping every day's prose would make it expensive for no
    one's benefit. The detail endpoint serves the body for the day picked.
    """
    return {
        "generated_on": briefing.generated_on.isoformat(),
        "generated_at": briefing.generated_at.isoformat(),
        "origin": briefing.origin,
        "kind": briefing.kind,
        "categories": briefing.categories,
        "counts": briefing.counts,
        "new_counts": briefing.new_counts,
    }


def _requested_kind(request) -> str:
    """Which report the caller is asking for — ``daily`` unless they say otherwise.

    Monday carries two rows for one target and one date, so every read of the
    history has to name a kind. Defaulting to ``daily`` keeps every existing
    caller — the app, the resend command, the Reports page — reading exactly what
    it read before the weekly existed.
    """
    asked = str(request.query_params.get("kind") or "").strip().lower()
    return (
        DailyBriefing.Kind.WEEKLY
        if asked == DailyBriefing.Kind.WEEKLY
        else DailyBriefing.Kind.DAILY
    )


def _briefing_history(kind: str = DailyBriefing.Kind.DAILY, **target):
    """Every retained briefing of one kind for one target, newest day first."""
    return DailyBriefing.objects.filter(kind=kind, **target).order_by("-generated_on")


class BriefingHistoryView(APIView):
    """The signed-in user's retained briefings, newest first (the Reports page).

    An index only — ``[{generated_on, generated_at, origin, categories, counts,
    new_counts}]``, no bodies. Own history only. An empty list is the honest "no
    run yet" state; a plan without scheduled reports never accrues rows at all.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        history = _briefing_history(_requested_kind(request), user=request.user)
        return Response([_briefing_summary(b) for b in history])


class BriefingDetailView(APIView):
    """One dated briefing for the signed-in user — the same envelope as today's.

    Reusing ``_daily_briefing_envelope`` is what lets the Reports page render an
    archived day through the identical card as the live one. 404 when that date
    has no briefing (including when it has aged past the retention window).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, on):
        briefing = get_object_or_404(
            DailyBriefing,
            user=request.user,
            generated_on=on,
            kind=_requested_kind(request),
        )
        return Response(_daily_briefing_envelope(briefing))


class LabBriefingHistoryView(APIView):
    """A lab's retained briefings, newest first. Any lab member may read them."""

    capabilities = {"GET": caps.MEMBERSHIP}

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        history = _briefing_history(_requested_kind(request), lab=lab)
        return Response([_briefing_summary(b) for b in history])


class LabBriefingDetailView(APIView):
    """One dated briefing for a lab, in the same envelope as the lab's current one."""

    capabilities = {"GET": caps.MEMBERSHIP}

    permission_classes = [IsAuthenticated]

    def get(self, request, slug, on):
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        briefing = get_object_or_404(
            DailyBriefing, lab=lab, generated_on=on, kind=_requested_kind(request)
        )
        return Response(_daily_briefing_envelope(briefing))


class LabDailyBriefingView(APIView):
    """A lab's "Mylo Report" — the lab overview's written briefing zone.

    Serves the durable :class:`DailyBriefing` keyed to the lab (the daily run's
    briefing stage also fans out to entitled labs). Any lab member may read it; an
    honest empty envelope is the "no run yet" state, same as the personal view.
    """

    capabilities = {"GET": caps.MEMBERSHIP}

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        briefing = DailyBriefing.latest_for(_requested_kind(request), lab=lab)
        return Response(_daily_briefing_envelope(briefing))


# --------------------------------------------------------------------------- #
# Opportunities (grants + conferences), saves, deadlines, notifications
# --------------------------------------------------------------------------- #

#: A saved deadline this many days out (or fewer) triggers a notification alert.
DEADLINE_ALERT_DAYS = 7

#: The content types a reader can bookmark or ignore — the four feed areas.
#: :class:`~tools.delivery.models.SavedOpportunity.Area` uses the same strings, so a
#: type doubles as its area, but the pair is asserted rather than assumed.
BOOKMARKABLE_TYPES = [
    ContentItem.Type.GRANT,
    ContentItem.Type.CONFERENCE,
    ContentItem.Type.FELLOWSHIP,
    ContentItem.Type.PAPER,
]


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
        LabMembership.objects.filter(user=user)
        .filter(lab_manager_q())
        .values_list("lab_id", flat=True)
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


def _ignored_content_ids(viewer) -> set:
    """The content ids ``viewer`` has manually ignored (empty for an anonymous read).

    An ignore belongs to the reader, not to the feed, so this is applied to the
    personal, lab, and project reads alike: the same shared item stays on a
    colleague's lab feed and leaves this reader's. Returns raw ids (not strings)
    so callers can compare against ``score.content_id`` directly.
    """
    if viewer is None:
        return set()
    return set(
        IgnoredItem.objects.filter(user=viewer).values_list("content_id", flat=True)
    )


def _latest_scores(
    target_filter: dict, content_type: str, *, viewer=None
) -> list[RelevanceScore]:
    """A target's matched items for the area, from the latest run, pinned-first.

    The **fresh-only** read, used for **papers**: the paper feed shows only the
    latest gather batch (see :func:`tools.recommendation.pipeline.recommend_for_user`),
    so a
    re-run replaces the digest rather than piling onto it. ``target_filter`` is the
    single ``target_*`` FK to read under — ``{"target_user": user}`` for a person,
    ``{"target_lab": lab}`` / ``{"target_project": project}`` for the institutional
    feeds. Rows the matcher persisted but marked ``suggested=False`` (below the
    match-percent floor) are excluded — mirroring ``DailyReportView``'s own filter —
    so a hidden verdict never surfaces just because it is the latest run. ``viewer``
    is the signed-in reader; anything they manually ignored is dropped, on this
    target's feed as on their own (see :func:`_ignored_content_ids`).
    """
    ignored = _ignored_content_ids(viewer)
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        ).select_related("content")
        if s.signals.get("suggested") and s.content_id not in ignored
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
    target_filter: dict, content_type: str, *, cap: int | None = None, viewer=None
) -> list[RelevanceScore]:
    """A target's matched **opportunities**, accumulated across every run.

    The **accumulate** read, used for grants / conferences / fellowships: the daily
    run scores only that day's *new* items and appends them (see
    :func:`tools.recommendation.opportunities.run_daily_opportunities_batch`), so a feed
    is
    the union of every run's suggested rows — one per ``(content, target)`` — not
    just the latest run. Items leave the feed only when the underlying
    :class:`ContentItem` is pruned at its deadline (``CASCADE`` drops the score).

    Newly-pinned items lead; below them, strongest match first (then the raw score),
    so an older still-relevant grant keeps a stable place. Rows marked
    ``suggested=False`` (below the match-percent floor) are excluded. Capped by
    ``OPPORTUNITY_FEED_MAX`` as a payload backstop, since an accumulating feed can
    otherwise grow unbounded between prunes.

    Dead listings are dropped **here**, not only by the nightly prune
    (:func:`tools.retrieval.liveness.is_live`). The prune is the removal guarantee
    and it runs once a night; this is the hiding guarantee and it runs on every
    request. Without it a conference whose last date passed this morning stays
    on the feed until tonight, and a *dateless* conference — which the prune
    cannot delete until the collector has stopped re-seeing it — would stay
    there indefinitely. Shared by personal, lab, and project feeds because they
    all read through this one function — which is also why ``viewer``'s manual
    ignores are applied here rather than per surface.
    """
    today = timezone.now().date().isoformat()
    ignored = _ignored_content_ids(viewer)
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        )
        .select_related("content")
        .prefetch_related("content__deadline_rows")
        if s.signals.get("suggested")
        and s.content_id not in ignored
        and is_live(content_type, s.content.metadata, today)
    ]
    if not scores:
        return []

    def sort_key(s: RelevanceScore):
        pinned_until = s.signals.get("pinned_until")
        pinned = bool(pinned_until and pinned_until >= today)
        # Slate position first — it is the ranking the run actually produced — then
        # the raw fused score for everything outside a slate. Sorting by the old
        # match percent ranked the feed by "what did the model reach", which is not
        # a relevance order at all.
        rank = s.signals.get("top_rank")
        rank = rank if isinstance(rank, int) else 10**6
        return (0 if pinned else 1, rank, -s.score)

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
        scores = _accumulated_scores(
            {"target_user": request.user}, self.content_type, viewer=request.user
        )
        context = {
            "today": timezone.now().date().isoformat(),
            "saved_ids": _saved_content_ids(request.user),
            "saved_labs": _saved_lab_slugs_by_content(request.user),
            # Without this the bridge badges resolve to empty labels: only the
            # attributed cluster carries a frozen label in its own signals, so a
            # feed built with no live map named one theme and left the rest blank.
            "cluster_labels": _user_cluster_labels(request.user),
            "usability_reader": usability.reader_for_user(request.user),
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


class RankingReferenceView(APIView):
    """Static hover copy for conference rank badges (plan Phase 9).

    A conference card carries only which rank it has (``rank_badges`` on
    :class:`~tools.delivery.serializers.ConferenceSerializer`) — small, per-item
    facts. What that rank *means* is identical prose for every card that shares
    it, so it lives here instead of being repeated on every row of a feed that
    can carry dozens of conferences. Authenticated (like the rest of ``/api/``)
    but otherwise static: no target, no personalization, safe to fetch once and
    cache.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "rank_systems": RANK_SYSTEM_INFO,
                "rank_explanations": RANK_EXPLANATIONS,
            }
        )


class FellowshipsView(_OpportunityFeedView):
    """The signed-in user's matched fellowships (Fellowships page).

    Adds ``stage_set``: whether this reader's career stage resolved at all. The
    stage gate is silent for anyone it cannot place on the ladder, so a feed built
    without one is genuinely less filtered than the page otherwise implies — the
    honest thing is to say so and offer the fix, not to promise eligibility
    filtering that did not happen.
    """

    content_type = ContentItem.Type.FELLOWSHIP
    serializer_class = FellowshipSerializer

    def get(self, request):
        from tools.recommendation.fellowships import derive_stage

        response = super().get(request)
        profile = getattr(request.user, "profile", None)
        response.data["stage_set"] = bool(profile and derive_stage(profile))
        return response


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
        verdict = score.signals.get("verdict")
        if verdict not in _INTERESTED_VERDICTS:
            continue
        member = score.target_user
        interested[str(score.content_id)].append(
            {
                "username": member.get_username(),
                "name": display_name(member),
                "initials": initials(member),
                "verdict": verdict,
            }
        )
    return interested


#: The eligibility tiers that count as "eligible" when naming who a fellowship suits.
_ELIGIBLE_TIERS = ("qualified", "conditional")


def _consented_eligibility(member_ids, content_ids) -> dict[str, dict[str, str]]:
    """``{content_id: {username: tier}}`` for **eligible, consenting** members.

    The one disclosure gate on personal fellowship eligibility (D-11), unchanged by
    the lab feed now being scored in its own right: a member is named as eligible
    only when their own tier is qualified/conditional **and** they opted into
    lab-visible eligibility (``interests.eligibility.lab_visible``, default off).
    Members who are ineligible, or eligible but not consenting, are never named.

    This is an *annotation* on the recommendation layer — it says who a fellowship
    the lab already matched is additionally eligible for. It no longer decides what
    the lab's Fellowships page contains.
    """
    if not member_ids or not content_ids:
        return {}
    out: dict[str, dict[str, str]] = defaultdict(dict)
    scores = RelevanceScore.objects.filter(
        target_user_id__in=member_ids,
        content_id__in=content_ids,
        content__type=ContentItem.Type.FELLOWSHIP,
    ).select_related("target_user", "target_user__profile")
    for score in scores:
        tier = score.signals.get("tier")
        if tier not in _ELIGIBLE_TIERS:
            continue  # eligible only — an ineligible member is never surfaced
        member = score.target_user
        profile = getattr(member, "profile", None)
        interests = (profile.interests or {}) if profile else {}
        if not interests.get("eligibility", {}).get("lab_visible"):
            continue  # opt-in consent only
        out[str(score.content_id)][member.get_username()] = tier
    return out


def _ineligible_members(roster: dict, scores: list[RelevanceScore]) -> dict[str, set]:
    """``{content_id: {username, …}}`` — members a fellowship hard-excludes.

    The lab fellowship feed is ranked on research fit with no eligibility gate,
    because a lab has no citizenship or career stage. That is correct for the
    *feed* and wrong for the *strip*: naming the members an award suits was
    running on topical cosine alone, so a postdoc-only award in a student's exact
    subfield named the student, confidently. This runs each named member's own
    eligibility against the item and removes the ones it hard-excludes.

    Evaluated live rather than read from their personal scores: a hard-ineligible
    row is dropped at scoring time and never persisted, so there is no stored
    "ineligible" to look up — and evaluating here means a profile edit corrects
    the strip without waiting for a re-score.

    Nothing is disclosed. A member who fails is silently absent, which reveals
    strictly less than the consented ``eligible`` annotation already does (D-11);
    the opt-in gate on *naming* someone eligible is untouched.
    """
    from tools.recommendation.fellowships import (
        eligibility_from_profile,
        evaluate_eligibility,
    )

    fellowships = [
        score for score in scores if score.content.type == ContentItem.Type.FELLOWSHIP
    ]
    if not fellowships or not roster:
        return {}
    today = timezone.now().date().isoformat()
    eligs = {}
    for username, user in roster.items():
        profile = getattr(user, "profile", None)
        if profile is not None:
            eligs[username] = eligibility_from_profile(profile)
    if not eligs:
        return {}

    out: dict[str, set] = {}
    for score in fellowships:
        metadata = score.content.metadata or {}
        blocked = {
            username
            for username, elig in eligs.items()
            if evaluate_eligibility(metadata, elig, today)["tier"] == "not_eligible"
        }
        if blocked:
            out[str(score.content_id)] = blocked
    return out


def _member_sort_key(row: dict):
    """Strip order: the members Mylo reasoned about first, then the rest.

    Two different claims live on this strip and they are not comparable — a
    profile cosine is a measured distance, an own-feed verdict is a judgement.
    Sorting the mixed column once ranked own-feed members above profile-fit
    members almost unconditionally, which pushed the one member Mylo actually
    wrote a rationale for out of the expanded slot. Grouping first, then sorting
    each group on its own terms, keeps every comparison within one scale.
    """
    explained = "profile_fit" in row["basis"]
    if explained:
        return (0, -(row.get("profile_cosine") or 0), row["username"])
    order = {READ: 0, SKIM: 1}.get(row.get("own_feed_verdict"), 2)
    return (1, order, row["username"])


def _recommended_for(
    scores: list[RelevanceScore],
    member_ids: list,
    interested: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """``{content_id: [member...]}`` — who each matched item is most applicable to.

    The one layer a lab feed has that a personal feed does not. Three bases, merged
    per member and ordered strongest first:

    - ``profile_fit`` — Mylo's own read, persisted at scoring time in
      ``signals["member_fit"]`` (:mod:`tools.recommendation.member_fit`): the member's
      interest vector matched the item, and ``reason`` is the consultant's sentence
      saying why (or the deterministic overlap line when the model was down).
    - ``own_match`` — the item independently cleared this member's *personal* feed
      at :data:`INTEREST_MATCH_THRESHOLD`, so they are already looking at it.
    - ``eligible`` — fellowships only: this member personally qualifies, disclosed
      only with their consent (:func:`_consented_eligibility`, D-11). Eligibility is
      an annotation on a recommendation, never the reason a lab sees the fellowship.

    Eligibility also *subtracts*: a member a fellowship hard-excludes is dropped
    from its strip whatever named them (:func:`_ineligible_members`). That gate
    needs no consent — it removes a name rather than publishing one.

    Two signals, each with its own field and its own meaning. ``profile_cosine``
    is the geometric distance between the item and the member's profile vector;
    ``own_feed_verdict`` is what the member's *own* feed concluded about it. They
    are not the same quantity — one is measured and one is judged — so they are
    never merged into a single number.

    Display fields (name, initials) resolve live from the member roster, so a rename
    lands without a re-score; a member who has since left the lab is dropped here
    even if a stale signal still names them.
    """
    if not member_ids or not scores:
        return {}
    roster = {
        user.get_username(): user
        for user in User.objects.filter(id__in=list(member_ids)).select_related(
            "profile"
        )
    }
    fellowship_ids = [
        s.content_id for s in scores if s.content.type == ContentItem.Type.FELLOWSHIP
    ]
    eligibility = _consented_eligibility(list(member_ids), fellowship_ids)
    ineligible = _ineligible_members(roster, scores)

    out: dict[str, list[dict]] = {}
    for score in scores:
        cid = str(score.content_id)
        blocked = ineligible.get(cid) or set()
        rows: dict[str, dict] = {}
        for entry in score.signals.get("member_fit") or []:
            username = entry.get("username")
            user = roster.get(username)
            if user is None or username in blocked:
                continue  # left the lab since the last scoring run, or cannot apply
            rows[username] = {
                "username": username,
                "name": display_name(user),
                "initials": initials(user),
                "profile_cosine": entry.get("fit"),
                "own_feed_verdict": None,
                "reason": entry.get("reason") or "",
                "source": entry.get("source") or "similarity",
                "basis": ["profile_fit"],
            }
        for member in interested.get(cid, []):
            username = member["username"]
            if username in blocked:
                continue
            row = rows.get(username)
            if row is None:
                row = {
                    "username": username,
                    "name": member["name"],
                    "initials": member["initials"],
                    "profile_cosine": None,
                    "own_feed_verdict": None,
                    "reason": "",
                    "source": "own_match",
                    "basis": [],
                }
                rows[username] = row
            row["basis"].append("own_match")
            row["own_feed_verdict"] = member["verdict"]
        for username, tier in (eligibility.get(cid) or {}).items():
            user = roster.get(username)
            if user is None or username in blocked:
                continue
            row = rows.get(username)
            if row is None:
                row = {
                    "username": username,
                    "name": display_name(user),
                    "initials": initials(user),
                    "profile_cosine": None,
                    "own_feed_verdict": None,
                    "reason": "",
                    "source": "eligibility",
                    "basis": [],
                }
                rows[username] = row
            row["basis"].append("eligible")
            row["tier"] = tier
        if rows:
            out[cid] = sorted(rows.values(), key=_member_sort_key)
    return out


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


def _window_counts(target_filter: dict, *, viewer=None) -> dict[str, dict[str, int]]:
    """Per-area today/week/month/year counts for a target's matched items.

    All four areas count the target's own suggested ``RelevanceScore`` rows by their
    insert time (``created_at`` — when Mylo scored/appended it for the target), the
    same reckoning :func:`_personal_window_counts` uses, so a lab's recency matrix
    means exactly what a person's does. Empty windows are still reported as zeroes.
    Items ``viewer`` ignored are left out, so the matrix cannot claim more than the
    feed beneath it shows.
    """
    now = timezone.now()
    ignored = _ignored_content_ids(viewer)
    counts: dict[str, dict[str, int]] = {}
    for key, ctype in (
        ("papers", ContentItem.Type.PAPER),
        ("grants", ContentItem.Type.GRANT),
        ("conferences", ContentItem.Type.CONFERENCE),
        ("fellowships", ContentItem.Type.FELLOWSHIP),
    ):
        rows = RelevanceScore.objects.filter(
            **target_filter, content__type=ctype
        ).values_list("created_at", "signals", "content_id")
        stamps = [
            ca
            for ca, sig, cid in rows
            if (sig or {}).get("suggested") and cid not in ignored
        ]
        counts[key] = _count_windows(stamps, now)
    return counts


def _personal_window_counts(user) -> dict[str, dict[str, int]]:
    """Per-area today/week/month/year counts for a user's own matched items.

    Unlike a lab, fellowships are already scored directly to ``target_user``
    (fellowships stay user-only), so all four areas read the same
    ``target_user`` filter — no member-union step needed. Manually ignored items are
    excluded, matching the feeds the matrix summarises.
    """
    now = timezone.now()
    ignored = _ignored_content_ids(user)
    counts: dict[str, dict[str, int]] = {}
    for key, ctype in (
        ("papers", ContentItem.Type.PAPER),
        ("grants", ContentItem.Type.GRANT),
        ("conferences", ContentItem.Type.CONFERENCE),
        ("fellowships", ContentItem.Type.FELLOWSHIP),
    ):
        rows = RelevanceScore.objects.filter(
            target_user=user, content__type=ctype
        ).values_list("created_at", "signals", "content_id")
        stamps = [
            ca
            for ca, sig, cid in rows
            if (sig or {}).get("suggested") and cid not in ignored
        ]
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
    from tools.recommendation.clustering import cluster_labels

    profile = getattr(user, "profile", None)
    return cluster_labels(getattr(profile, "interests", None))


def _target_cluster_labels(target_filter: dict) -> dict[str, str]:
    """``cluster_id -> current label`` for a lab / project paper feed.

    Labs carry clusters on their ``LabProfile.interests``; projects rarely do, so
    the serializer's frozen-label fallback covers them.
    """
    from tools.recommendation.clustering import cluster_labels

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
    from tools.recommendation.clustering import cluster_interests
    from tools.recommendation.ranking import focus_overlap

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


def _recommendations_payload(
    target_filter: dict,
    *,
    user,
    member_ids=(),
    digest: bool = False,
    reader=None,
) -> dict:
    """The combined papers + grants + conferences + fellowships a lab / project matched.

    ``counts`` powers the overview stat cards; the lists power the feeds. All four
    areas are the target's own ``RelevanceScore`` rows, serialized with the very
    same serializers the personal pages use — a lab feed is structurally identical
    to its personal counterpart, fellowships included (they rank on research fit;
    an institution has no citizenship or career stage to gate on).

    Who each item is *for* is a separate layer, not a filter on what the feed
    contains: ``interested`` names the members who personally matched an item
    strongly, and ``recommended_for`` is Mylo's read on which members it best suits
    (see :func:`_recommended_for`).

    ``digest`` returns the condensed short list — top ``DIGEST_CAPS`` per area —
    for the per-project "Mylo's picks" block. It no longer drops passed
    conferences itself: :func:`_accumulated_scores` now applies
    :func:`tools.retrieval.liveness.is_live` to every opportunity read, so a
    conference that is over never reaches this function on any surface, digest
    or not. ``counts`` stays the full totals so the UI can say "top 5 of N".
    Saves remain
    personal, so ``saved`` reflects the signed-in user regardless of scope.
    """
    today = timezone.now().date().isoformat()
    opp_context = {
        "today": today,
        "saved_ids": _saved_content_ids(user),
        "saved_labs": _saved_lab_slugs_by_content(user),
        # Same live label map the paper feed below already passes — a lab's
        # opportunity cards name their themes for the same reason its papers do.
        "cluster_labels": _target_cluster_labels(target_filter),
    }
    # Papers are fresh-only (latest gather batch); opportunities accumulate.
    papers = _latest_scores(target_filter, ContentItem.Type.PAPER, viewer=user)
    grants = _accumulated_scores(target_filter, ContentItem.Type.GRANT, viewer=user)
    conferences = _accumulated_scores(
        target_filter, ContentItem.Type.CONFERENCE, viewer=user
    )
    fellowships = _accumulated_scores(
        target_filter, ContentItem.Type.FELLOWSHIP, viewer=user
    )

    # Full counts (before any digest slice) so the UI can show "top N of total".
    counts = {
        "papers": len(papers),
        "grants": len(grants),
        "conferences": len(conferences),
        "fellowships": len(fellowships),
    }

    if digest:
        papers = papers[: DIGEST_CAPS["papers"]]
        grants = grants[: DIGEST_CAPS["grants"]]
        conferences = conferences[: DIGEST_CAPS["conferences"]]
        fellowships = fellowships[: DIGEST_CAPS["fellowships"]]

    scores = [*papers, *grants, *conferences, *fellowships]
    content_ids = [s.content_id for s in scores]
    interested = _interested_members(list(member_ids), content_ids)
    recommended = _recommended_for(scores, list(member_ids), interested)
    if reader is not None:
        # The "Can we use this?" strip: team coverage reads the same people the
        # strip already names, and fellowship counts never name anyone.
        opp_context["usability_reader"] = reader
        opp_context["usability_suited"] = {
            cid: [row["name"] for row in rows[:3]] for cid, rows in recommended.items()
        }
        from tools.delivery.announcement_links import for_target

        lab_target = target_filter.get("target_lab") or getattr(
            target_filter.get("target_project"), "scope_lab", None
        )
        opp_context["announcements"] = (
            for_target({"target_lab": lab_target}, content_ids) if lab_target else {}
        )
        opp_context["usability_fellowship_counts"] = usability.fellowship_counts(
            list(member_ids),
            [score.content for score in fellowships],
            timezone.now().date(),
        )
    return {
        "generated_at": _generated_at(scores),
        "counts": counts,
        # Per-area today/week/month/year totals for the overview stats block.
        "window_counts": _window_counts(target_filter, viewer=user),
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
        "fellowships": FellowshipSerializer(
            fellowships, many=True, context=opp_context
        ).data,
        "interested": interested,
        "recommended_for": recommended,
    }


class LabRecommendationsView(APIView):
    """A lab's matched papers/grants/fellowships/conferences (its aggregate interests).

    Any member of the lab may read them (``user_has_lab_access``); the lab overview
    reads ``counts`` and a lab feed reads the lists.
    """

    capabilities = {"GET": caps.MEMBERSHIP}

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
                {"target_lab": lab},
                user=request.user,
                member_ids=member_ids,
                reader=usability.reader_for_lab(lab),
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
                digest=digest,
                reader=(
                    usability.reader_for_lab(project.scope_lab)
                    if project.scope_lab_id is not None
                    else usability.reader_for_user(request.user)
                ),
            )
        )


class SaveOpportunityView(APIView):
    """Save (POST) or unsave (DELETE) a bookmarkable item for the Saves page."""

    permission_classes = [IsAuthenticated]

    _SAVEABLE_TYPES = BOOKMARKABLE_TYPES

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
        # Saving is the opposite intent to ignoring, so it clears any ignore on
        # the same item (see :class:`IgnoreItemView`). Only for a personal save:
        # a lab save is not this reader speaking about their own feed.
        IgnoredItem.objects.filter(user=user, content=item).delete()
    # Round-trip so date/enum fields are proper types (not the raw strings just
    # written) before the row is serialized back in the response.
    saved.refresh_from_db()
    return saved


class IgnoreItemView(APIView):
    """Ignore (POST) or stop ignoring (DELETE) an item, for the signed-in user.

    The counterpart of :class:`SaveOpportunityView`. Ignoring hides an entry from
    every feed *this reader* looks at — papers, grants, fellowships, conferences,
    and the lab and project feeds they read — without touching the item, its
    scores, or what anyone else is shown. Nothing here is a lab-scoped action: an
    ignore is a fact about the reader, so there is no ``lab_slug`` and no manager
    check to make.

    Ignoring an item also drops its **personal** save. The two controls sit next
    to each other and mean opposite things, so letting an item be both saved and
    ignored would only produce a Saves page that contradicts the feeds. A **lab**
    save is left alone — it belongs to the lab, not to whoever ignored the item.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_id = request.data.get("content_id")
        if not content_id:
            return Response(
                {"detail": "content_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item = ContentItem.objects.filter(
            id=content_id, type__in=BOOKMARKABLE_TYPES
        ).first()
        if item is None:
            return Response(
                {"detail": "No such paper, grant, conference, or fellowship."},
                status=status.HTTP_404_NOT_FOUND,
            )
        _, created = IgnoredItem.objects.get_or_create(
            user=request.user,
            content=item,
            defaults={"area": item.type},
        )
        SavedOpportunity.objects.filter(
            user=request.user, target_lab__isnull=True, content=item
        ).delete()
        if created:
            # A weak relevance label only. Nothing reads this stream back into
            # ranking today; it exists so the choice is on the record if it ever
            # should. Logged once per ignore, not on a repeat call.
            record_event(request.user, item, RelevanceEvent.Action.DISMISS)
        return Response(
            {"content_id": str(item.id), "ignored": True},
            status=(
                status.HTTP_201_CREATED if created else status.HTTP_200_OK
            ),
        )

    def delete(self, request, content_id):
        deleted, _ = IgnoredItem.objects.filter(
            user=request.user, content_id=content_id
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IgnoredItemsView(APIView):
    """Everything the signed-in user has ignored, newest first (the Ignored view).

    Reversibility is the point: an ignore that cannot be found again is
    indistinguishable from a deletion. Each row carries the same feed-parity
    ``card`` the Saves page renders, so the reader recognises what they dismissed
    rather than reading a bare title.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(
            IgnoredItem.objects.filter(user=request.user)
            .select_related("content")
            .prefetch_related("content__deadline_rows")
            .order_by("-created_at")
        )
        content_ids = [r.content_id for r in rows]
        scores_by_content = {
            score.content_id: score
            for score in RelevanceScore.objects.filter(
                target_user=request.user, content_id__in=content_ids
            )
            .select_related("content")
            .prefetch_related("content__deadline_rows")
        }
        today = timezone.now().date()
        context = {
            "today": today.isoformat(),
            "today_date": today,
            "saved_ids": set(),
            "saved_labs": _saved_lab_slugs_by_content(request.user),
            "scores_by_content": scores_by_content,
            "cluster_labels": _user_cluster_labels(request.user),
        }
        return Response(
            {"items": IgnoredItemSerializer(rows, many=True, context=context).data}
        )


class ItemCardView(APIView):
    """One corpus item as the card its own feed would show (``{area, card}``).

    How a link to an item opens when the item is not in the reader's loaded
    feed — Mylo cites anything in the corpus, not only today's slate. The
    reader's own latest score is used when there is one; otherwise the card is
    drawn from the live item with a neutral score, exactly as Saves does.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, content_id):
        item = get_object_or_404(
            ContentItem.objects.prefetch_related("deadline_rows"), pk=content_id
        )
        serializer_class = _SAVED_CARD_SERIALIZERS.get(item.type)
        if serializer_class is None:
            return Response({"detail": "Unknown item kind."}, status=404)
        score = (
            RelevanceScore.objects.filter(target_user=request.user, content=item)
            .order_by("-created_at")
            .first()
        )
        if score is None:
            score = RelevanceScore(content=item, score=0.0, signals={})
        else:
            score.content = item
        today = timezone.now().date()
        context = {
            "today": today.isoformat(),
            "today_date": today,
            "saved_ids": _saved_content_ids(request.user),
            "saved_labs": _saved_lab_slugs_by_content(request.user),
            "cluster_labels": _user_cluster_labels(request.user),
            "usability_reader": usability.reader_for_user(request.user),
        }
        return Response(
            {"area": item.type, "card": serializer_class(score, context=context).data}
        )


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

    capabilities = {"GET": caps.MEMBERSHIP}

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
    :mod:`tools.retrieval.search`) over the **global** corpus — the same items the
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

        # Query embedding, saved state and cluster attribution all live in
        # `search_service`, so Mylo's `/mylo search` runs the identical path and the
        # two surfaces cannot drift apart on the same query.
        from tools.delivery.search_service import search_for_user

        context = search_for_user(
            request.user,
            query,
            filters=filters,
            sort=params.get("sort", "relevance"),
            limit=params.get("limit"),
            offset=_parse_offset(params),
        )
        result = context.result
        from tools.delivery.announcement_links import discussed_for_user

        serializer = SearchResultSerializer(
            result.items,
            many=True,
            context={
                "saved_ids": context.saved_ids,
                "saved_labs": context.saved_labs,
                "ignored_ids": context.ignored_ids,
                "discord_links": discussed_for_user(
                    request.user, [item.id for item in result.items]
                ),
            },
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
        # The fused score, as itself. Scaling it by 100 and calling it a percent
        # match was the clearest case of the false precision this release removes:
        # a ranking score is not a similarity.
        "score": round(suggestion.score, 3),
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


# --------------------------------------------------------------------------- #
# Reflection proposals (plan 7.3)
# --------------------------------------------------------------------------- #
def _proposal_payload(row) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "project_name": row.project.name,
        "kind": row.kind,
        "proposal": row.proposal,
        "evidence": row.evidence,
        "status": row.status,
        "expires_on": row.expires_on.isoformat(),
        "created_at": row.created_at.isoformat(),
    }


class ReflectionProposalsView(APIView):
    """The caller's pending proposals — what Mylo thinks their state should say.

    Own proposals only. A proposal is a request to change what someone wrote
    about their own work, so it belongs to whoever wrote it and to nobody else.
    """

    def get(self, request):
        from tools.delivery.models import ReflectionProposal
        from tools.delivery.reflection import expire_stale

        # Lapsed on read as well as on the weekly run: a proposal that expired on
        # Tuesday should not still be offered on Wednesday because nothing has
        # run since.
        expire_stale()
        rows = (
            ReflectionProposal.objects.filter(
                target_user=request.user,
                status=ReflectionProposal.Status.PENDING,
            )
            .select_related("project")
            .order_by("created_at")
        )
        return Response([_proposal_payload(row) for row in rows])


class ReflectionProposalActionView(APIView):
    """Accept or reject one proposal.

    **Accepting is what applies it.** Nothing else in the product writes a
    proposal into a project's state (invariant 9), which is why this endpoint,
    and not the weekly run, is the only place the merge happens — and why it
    re-checks the edit permission rather than trusting that whoever was proposed
    to can still edit the project.
    """

    def post(self, request, pk):
        from apps.research.models import ProjectState
        from apps.research.permissions import user_can_edit_project as _user_can_edit

        from tools.delivery.models import ReflectionProposal

        action = str(request.data.get("action") or "").strip().lower()
        if action not in {"accept", "reject"}:
            raise ValidationError({"action": ['must be "accept" or "reject"']})

        row = get_object_or_404(
            ReflectionProposal.objects.select_related("project"),
            pk=pk,
            target_user=request.user,
        )
        if row.status != ReflectionProposal.Status.PENDING:
            raise ValidationError(
                {"non_field_errors": ["This proposal has already been decided."]}
            )

        if action == "accept":
            if not _user_can_edit(request.user, row.project):
                raise PermissionDenied("You cannot edit this project.")
            if row.proposal:
                state, _created = ProjectState.objects.get_or_create(
                    project=row.project
                )
                before = {
                    part: dict(getattr(state, part) or {}) for part in ("slow", "fast")
                }
                state.apply(row.proposal, actor=request.user)
                # Accepting is the reader saying the state is right, so it is a
                # confirmation as much as an edit.
                state.confirmed_at = timezone.localdate()
                state.save()
            row.status = ReflectionProposal.Status.ACCEPTED
            if row.proposal and (row.evidence or {}).get("source") == "conversation":
                # From ambient Plan 08: shown in "What changed", with undo.
                from apps.ambient.read import note_state_change

                part, _, name = str(row.evidence.get("field") or "").partition(".")
                if part in ("slow", "fast") and name:
                    note_state_change(
                        request.user,
                        row.project,
                        field=f"{part}.{name}",
                        old_value={name: before[part].get(name)},
                        new_value={name: (getattr(state, part) or {}).get(name)},
                        topic=str(row.evidence.get("topic") or ""),
                        proposal_id=str(row.pk),
                        explanation=str(row.evidence.get("explanation") or ""),
                        visibility=str(row.evidence.get("visibility") or "lab"),
                    )
        else:
            row.status = ReflectionProposal.Status.REJECTED
        row.decided_at = timezone.now()
        row.save(update_fields=["status", "decided_at"])
        return Response(_proposal_payload(row))
