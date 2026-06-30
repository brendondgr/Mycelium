from rest_framework import serializers

from .models import RelevanceScore


class SuggestionSerializer(serializers.Serializer):
    """One research-article suggestion for the daily report (read-only).

    Flattens a :class:`RelevanceScore` and its content item into what the Daily
    Reports UI needs: the paper's identity plus the digest payload (rank,
    headline, reason) the pipeline wrote into ``signals``.
    """

    content_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    source = serializers.CharField(source="content.source")
    url = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    authors = serializers.SerializerMethodField()
    score = serializers.FloatField()
    rank = serializers.SerializerMethodField()
    headline = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()

    def get_content_id(self, score: RelevanceScore) -> str:
        return str(score.content_id)

    def _meta(self, score: RelevanceScore) -> dict:
        return score.content.metadata or {}

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("title") or "Untitled paper"

    def get_url(self, score: RelevanceScore) -> str:
        return self._meta(score).get("pdf_url") or score.content.source_url or ""

    def get_venue(self, score: RelevanceScore) -> str:
        return self._meta(score).get("venue") or ""

    def get_year(self, score: RelevanceScore):
        return self._meta(score).get("year")

    def get_authors(self, score: RelevanceScore) -> list[str]:
        authors = self._meta(score).get("authors")
        return authors[:6] if isinstance(authors, list) else []

    def get_rank(self, score: RelevanceScore):
        return score.signals.get("rank")

    def get_headline(self, score: RelevanceScore) -> str:
        return score.signals.get("headline") or self.get_title(score)

    def get_reason(self, score: RelevanceScore) -> str:
        return score.signals.get("reason") or ""

    def get_origin(self, score: RelevanceScore) -> str:
        # "llm" when the language model wrote the reason, else "fallback".
        return score.signals.get("source") or "fallback"
