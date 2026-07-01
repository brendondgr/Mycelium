from collections import Counter

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RelevanceScore
from .serializers import SuggestionSerializer

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
        scores = [
            score
            for score in RelevanceScore.objects.filter(
                target_user=request.user
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
