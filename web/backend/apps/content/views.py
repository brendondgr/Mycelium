from collections import Counter, defaultdict
from datetime import date

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Lab, LabMembership
from apps.accounts.permissions import user_has_lab_access
from apps.core.people import display_name, initials
from apps.research.models import Project

from .collaboration import record_event
from .models import (
    ContentItem,
    MemberSuggestion,
    RelevanceEvent,
    RelevanceScore,
    SavedOpportunity,
)
from .onboarding_match import UnknownArea, onboarding_match_area
from .query_embedding import embed_query
from .search import SearchFilters, normalize_query, run_search
from .serializers import (
    ConferenceSerializer,
    FellowshipSerializer,
    GrantSerializer,
    SavedDeadlineSerializer,
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
    ``generated_at: null``) is the honest "no run yet" state.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
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
                {"generated_at": None, "summary": None, "suggestions": []}
            )

        latest = max(score.signals.get("run_at", "") for score in scores)
        current = [s for s in scores if s.signals.get("run_at", "") == latest]
        current.sort(key=lambda s: s.signals.get("rank") or 999)
        return Response(
            {
                "generated_at": latest or None,
                "summary": _build_summary(current),
                "suggestions": SuggestionSerializer(current, many=True).data,
            }
        )


def _build_summary(rows: list[RelevanceScore]) -> dict:
    """Roll the day's suggested papers up into the Daily Report summary.

    Deterministic on purpose: it reports what today's research scan surfaced
    (count, match strength, recurring focus themes, sources) without a second
    language-model call, so the summary is stable and always available.
    """
    matches = [
        m for m in (r.signals.get("match_percent") for r in rows) if isinstance(m, int)
    ]
    strong = sum(1 for m in matches if m >= STRONG_MATCH_THRESHOLD)

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
    return {
        "paper_count": count,
        "strong_matches": strong,
        "top_match": max(matches) if matches else None,
        "average_match": round(sum(matches) / len(matches)) if matches else None,
        "themes": themes,
        "sources": sources,
        "headline": _summary_headline(count, strong),
    }


def _summary_headline(count: int, strong: int) -> str:
    if count == 0:
        return "No new papers matched your research today."
    papers = "paper" if count == 1 else "papers"
    lead = f"{count} {papers} matched your research today"
    if strong:
        return f"{lead} — {strong} a strong match."
    return f"{lead}."


# --------------------------------------------------------------------------- #
# Opportunities (grants + conferences), saves, deadlines, notifications
# --------------------------------------------------------------------------- #

#: A saved deadline this many days out (or fewer) triggers a notification alert.
DEADLINE_ALERT_DAYS = 7


def _saved_content_ids(user) -> set[str]:
    """The content ids the user has saved (for the ``saved`` flag on each item)."""
    return {
        str(cid)
        for cid in SavedOpportunity.objects.filter(
            user=user, content__isnull=False
        ).values_list("content_id", flat=True)
    }


def _latest_scores(target_filter: dict, content_type: str) -> list[RelevanceScore]:
    """A target's matched items for the area, from the latest run, pinned-first.

    ``target_filter`` is the single ``target_*`` FK to read under —
    ``{"target_user": user}`` for a person, ``{"target_lab": lab}`` /
    ``{"target_project": project}`` for the institutional feeds.
    """
    scores = list(
        RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        ).select_related("content")
    )
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


def _latest_run_scores(user, content_type: str) -> list[RelevanceScore]:
    """The signed-in user's matched items for the area (the personal feeds)."""
    return _latest_scores({"target_user": user}, content_type)


class _OpportunityFeedView(APIView):
    """Shared GET for a matched-opportunity feed (grants or conferences)."""

    permission_classes = [IsAuthenticated]
    content_type: str = ""
    serializer_class = None

    def get(self, request):
        scores = _latest_run_scores(request.user, self.content_type)
        generated_at = scores[0].signals.get("run_at") if scores else None
        context = {
            "today": timezone.now().date().isoformat(),
            "saved_ids": _saved_content_ids(request.user),
        }
        return Response(
            {
                "generated_at": generated_at,
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


def _recommendations_payload(target_filter: dict, *, user, member_ids=()) -> dict:
    """The combined papers + grants + conferences a lab / project matched.

    Fellowships are omitted: they are an individual-eligibility area, so they never
    score against a lab or project. ``counts`` powers the lab overview stat cards;
    the three lists power the project feed and any lab feed. ``interested`` maps each
    item to the lab members who personally matched it strongly (from ``member_ids``),
    so the UI can suggest who to connect over a shared item. Saves remain personal
    (a user saves a deadline to *their* deadlines), so ``saved`` reflects the
    signed-in user regardless of whose recommendations these are.
    """
    today = timezone.now().date().isoformat()
    opp_context = {"today": today, "saved_ids": _saved_content_ids(user)}
    papers = _latest_scores(target_filter, ContentItem.Type.PAPER)
    grants = _latest_scores(target_filter, ContentItem.Type.GRANT)
    conferences = _latest_scores(target_filter, ContentItem.Type.CONFERENCE)
    run_ats = [
        rows[0].signals.get("run_at")
        for rows in (papers, grants, conferences)
        if rows
    ]
    content_ids = [s.content_id for s in (*papers, *grants, *conferences)]
    return {
        "generated_at": max(run_ats) if run_ats else None,
        "counts": {
            "papers": len(papers),
            "grants": len(grants),
            "conferences": len(conferences),
        },
        "papers": SuggestionSerializer(papers, many=True).data,
        "grants": GrantSerializer(grants, many=True, context=opp_context).data,
        "conferences": ConferenceSerializer(
            conferences, many=True, context=opp_context
        ).data,
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
        return Response(
            _recommendations_payload(
                {"target_project": project},
                user=request.user,
                member_ids=member_ids,
            )
        )


class SaveOpportunityView(APIView):
    """Save (POST) or unsave (DELETE) an opportunity to the user's deadlines."""

    permission_classes = [IsAuthenticated]

    _SAVEABLE_TYPES = [
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
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
                {"detail": "No such grant, conference, or fellowship."},
                status=status.HTTP_404_NOT_FOUND,
            )
        saved = _save_from_item(request.user, item, note=request.data.get("note", ""))
        context = {"today_date": timezone.now().date()}
        return Response(
            SavedDeadlineSerializer(saved, context=context).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, content_id):
        deleted, _ = SavedOpportunity.objects.filter(
            user=request.user, content_id=content_id
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _save_from_item(user, item: ContentItem, *, note: str) -> SavedOpportunity:
    """Create/update a save, snapshotting the display + deadline fields."""
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
    else:
        area = SavedOpportunity.Area.CONFERENCE
        title = meta.get("name") or "Untitled conference"
        subtitle = ", ".join(
            p for p in (meta.get("location"), meta.get("country")) if p
        )
        url = meta.get("website") or item.source_url or ""

    saved, _ = SavedOpportunity.objects.update_or_create(
        user=user,
        content=item,
        defaults={
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
        },
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


class NotificationsView(APIView):
    """Deadline alerts for the header bell: saves due within a week."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        alerts = []
        for saved in SavedOpportunity.objects.filter(
            user=request.user, deadline_date__isnull=False
        ):
            days = (saved.deadline_date - today).days
            if 0 <= days <= DEADLINE_ALERT_DAYS:
                content_id = str(saved.content_id) if saved.content_id else None
                alerts.append(
                    {
                        "id": str(saved.id),
                        "content_id": content_id,
                        "area": saved.area,
                        "title": saved.title,
                        "url": saved.url,
                        "deadline_date": saved.deadline_date.isoformat(),
                        "days_remaining": days,
                        "message": _alert_message(saved.title, days),
                    }
                )
        alerts.sort(key=lambda a: a["days_remaining"])
        return Response({"count": len(alerts), "items": alerts})


def _alert_message(title: str, days: int) -> str:
    when = "due today" if days == 0 else f"{days} day{'s' if days != 1 else ''} left"
    return f"“{title}” — less than a week left ({when})."


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
        serializer = SearchResultSerializer(
            result.items, many=True, context={"saved_ids": saved_ids}
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
