from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RelevanceScore
from .serializers import SuggestionSerializer


class DailyReportView(APIView):
    """The signed-in user's current research-article suggestions (own only).

    Returns the suggestions from the most recent pipeline run — the rows the
    daily pipeline flagged ``suggested`` and stamped with a shared ``run_at`` —
    ordered by rank. Earlier runs' suggestions are ignored, so re-running the
    pipeline replaces the digest rather than piling onto it. An empty list (with
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
            return Response({"generated_at": None, "suggestions": []})

        latest = max(score.signals.get("run_at", "") for score in scores)
        current = [s for s in scores if s.signals.get("run_at", "") == latest]
        current.sort(key=lambda s: s.signals.get("rank") or 999)
        return Response(
            {
                "generated_at": latest or None,
                "suggestions": SuggestionSerializer(current, many=True).data,
            }
        )
