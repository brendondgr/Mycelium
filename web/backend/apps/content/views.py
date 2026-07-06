from collections import Counter

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ContentItem, RelevanceScore, SavedOpportunity
from .serializers import (
    ConferenceSerializer,
    GrantSerializer,
    SavedDeadlineSerializer,
    SuggestionSerializer,
)

#: A suggestion at or above this percent match is called a "strong" match in the
#: daily summary. Kept here (not a setting) so the label logic stays with the view.
STRONG_MATCH_THRESHOLD = 75


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


def _latest_run_scores(user, content_type: str) -> list[RelevanceScore]:
    """This user's matched items for the area, from the latest run, pinned-first."""
    scores = list(
        RelevanceScore.objects.filter(
            target_user=user, content__type=content_type
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


class SaveOpportunityView(APIView):
    """Save (POST) or unsave (DELETE) a grant/conference to the user's deadlines."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_id = request.data.get("content_id")
        if not content_id:
            return Response(
                {"detail": "content_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item = ContentItem.objects.filter(
            id=content_id,
            type__in=[ContentItem.Type.GRANT, ContentItem.Type.CONFERENCE],
        ).first()
        if item is None:
            return Response(
                {"detail": "No such grant or conference."},
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
    area = (
        SavedOpportunity.Area.GRANT
        if item.type == ContentItem.Type.GRANT
        else SavedOpportunity.Area.CONFERENCE
    )
    if area == SavedOpportunity.Area.GRANT:
        title = meta.get("title") or "Untitled grant"
        subtitle = meta.get("sponsor") or ""
    else:
        title = meta.get("name") or "Untitled conference"
        subtitle = ", ".join(
            p for p in (meta.get("location"), meta.get("country")) if p
        )
    saved, _ = SavedOpportunity.objects.update_or_create(
        user=user,
        content=item,
        defaults={
            "area": area,
            "title": title,
            "url": meta.get("website") or item.source_url or "",
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
