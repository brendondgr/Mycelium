from datetime import date

from rest_framework import serializers

from apps.scraper.pivot.normalize import normalize_amount

from .models import RelevanceScore, SavedOpportunity


class SuggestionSerializer(serializers.Serializer):
    """One research-article suggestion for the daily report (read-only).

    Flattens a :class:`RelevanceScore` and its content item into what the Daily
    Reports UI needs: the paper's identity plus the digest payload (rank,
    headline, reason) the pipeline wrote into ``signals``.
    """

    content_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    abstract = serializers.SerializerMethodField()
    source = serializers.CharField(source="content.source")
    url = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    authors = serializers.SerializerMethodField()
    score = serializers.FloatField()
    match_percent = serializers.SerializerMethodField()
    per_interest = serializers.SerializerMethodField()
    matched_interests = serializers.SerializerMethodField()
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

    def get_abstract(self, score: RelevanceScore) -> str:
        # The paper's abstract (same metadata field the BM25 channel indexes);
        # the Research Papers page shows it and searches over it client-side.
        return self._meta(score).get("abstract") or ""

    def get_url(self, score: RelevanceScore) -> str:
        return self._meta(score).get("pdf_url") or score.content.source_url or ""

    def get_venue(self, score: RelevanceScore) -> str:
        return self._meta(score).get("venue") or ""

    def get_year(self, score: RelevanceScore):
        return self._meta(score).get("year")

    def get_authors(self, score: RelevanceScore) -> list[str]:
        authors = self._meta(score).get("authors")
        return authors[:6] if isinstance(authors, list) else []

    def get_match_percent(self, score: RelevanceScore):
        # The language model's 0–100 fit judgement for this researcher (a
        # similarity-derived proxy when the model was unavailable).
        return score.signals.get("match_percent")

    def get_per_interest(self, score: RelevanceScore) -> dict:
        # {interest label -> [0,1] fusion score} for the multi-interest path; the
        # page derives a per-interest "focus %" from this when the reader filters
        # by category. Empty on the single-vector fallback path (no declared areas).
        return score.signals.get("per_interest") or {}

    def get_matched_interests(self, score: RelevanceScore) -> list:
        # The interest labels this paper matched — the source of the page's chips.
        return score.signals.get("focus_areas") or []

    def get_rank(self, score: RelevanceScore):
        return score.signals.get("rank")

    def get_headline(self, score: RelevanceScore) -> str:
        return score.signals.get("headline") or self.get_title(score)

    def get_reason(self, score: RelevanceScore) -> str:
        return score.signals.get("reason") or ""

    def get_origin(self, score: RelevanceScore) -> str:
        # "llm" when the language model wrote the reason, else "fallback".
        return score.signals.get("source") or "fallback"


class _OpportunitySerializer(serializers.Serializer):
    """Shared read shape for a matched grant/conference (a :class:`RelevanceScore`).

    Flattens the score + its content item + the pipeline's ``signals`` into what the
    Opportunities / Conferences pages render: the ranking (percent, rank, reason),
    the "New"/pin state, the actionable deadline, and whether the user saved it.
    Subclasses add the area-specific display fields. ``today`` (ISO) is passed in
    the serializer context so the pin/deadline states are evaluated once per request.
    """

    content_id = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    score = serializers.FloatField()
    match_percent = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    headline = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    pinned = serializers.SerializerMethodField()
    deadline_date = serializers.SerializerMethodField()
    deadline_kind = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    saved = serializers.SerializerMethodField()

    def _meta(self, score: RelevanceScore) -> dict:
        return (score.content.metadata or {}) if score.content_id else {}

    def _today(self) -> str:
        return self.context.get("today", "")

    def get_content_id(self, score: RelevanceScore) -> str:
        return str(score.content_id)

    def get_url(self, score: RelevanceScore) -> str:
        return self._meta(score).get("website") or (
            score.content.source_url if score.content_id else ""
        )

    def get_match_percent(self, score: RelevanceScore):
        return score.signals.get("match_percent")

    def get_rank(self, score: RelevanceScore):
        return score.signals.get("rank")

    def get_headline(self, score: RelevanceScore) -> str:
        return score.signals.get("headline") or ""

    def get_reason(self, score: RelevanceScore) -> str:
        return score.signals.get("reason") or ""

    def get_origin(self, score: RelevanceScore) -> str:
        return score.signals.get("source") or "fallback"

    def get_pinned(self, score: RelevanceScore) -> bool:
        # Pinned (and the "New" tag shows) while the one-week window is still open.
        pinned_until = score.signals.get("pinned_until")
        return bool(pinned_until and pinned_until >= self._today())

    def get_is_new(self, score: RelevanceScore) -> bool:
        return bool(score.signals.get("is_new")) and self.get_pinned(score)

    def get_deadline_date(self, score: RelevanceScore) -> str:
        return score.signals.get("deadline_date") or ""

    def get_deadline_kind(self, score: RelevanceScore) -> str:
        return score.signals.get("next_kind") or ""

    def get_status_summary(self, score: RelevanceScore) -> str:
        return score.signals.get("status_summary") or ""

    def get_saved(self, score: RelevanceScore) -> bool:
        return str(score.content_id) in self.context.get("saved_ids", set())


class GrantSerializer(_OpportunitySerializer):
    """A matched funding opportunity for the Opportunities page (grants column)."""

    title = serializers.SerializerMethodField()
    sponsor = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    matched_topics = serializers.SerializerMethodField()
    posted = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("title") or "Untitled grant"

    def get_sponsor(self, score: RelevanceScore) -> str:
        return self._meta(score).get("sponsor") or ""

    def get_amount(self, score: RelevanceScore) -> str:
        # Distil at read time too: rows ingested before the normalizer existed
        # still carry a whole budget paragraph, which would spam the card.
        return normalize_amount(self._meta(score).get("amount") or "")

    def get_matched_topics(self, score: RelevanceScore) -> str:
        return self._meta(score).get("matched_topics") or ""

    def get_posted(self, score: RelevanceScore) -> str:
        # When Milo first surfaced this grant (ISO); drives the "Posted" line.
        return score.signals.get("first_seen") or ""

    def get_description(self, score: RelevanceScore) -> str:
        # A human-readable blurb: the AI summary if present, else the abstract.
        meta = self._meta(score)
        return meta.get("ai_summary") or meta.get("abstract") or ""


class ConferenceSerializer(_OpportunitySerializer):
    """A matched conference for the Conferences page (card format)."""

    title = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    event_dates = serializers.SerializerMethodField()
    deadlines = serializers.SerializerMethodField()
    keywords = serializers.SerializerMethodField()
    matched_subjects = serializers.SerializerMethodField()

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("name") or "Untitled conference"

    def get_location(self, score: RelevanceScore) -> str:
        meta = self._meta(score)
        return ", ".join(p for p in (meta.get("location"), meta.get("country")) if p)

    def get_country(self, score: RelevanceScore) -> str:
        return self._meta(score).get("country") or ""

    def get_event_dates(self, score: RelevanceScore) -> str:
        return self._meta(score).get("event_dates") or ""

    def get_deadlines(self, score: RelevanceScore) -> str:
        return self._meta(score).get("deadlines") or ""

    def get_keywords(self, score: RelevanceScore) -> str:
        return self._meta(score).get("keywords") or ""

    def get_matched_subjects(self, score: RelevanceScore) -> str:
        # Semicolon-delimited subject categories — clean, chippable topic tags
        # (unlike ``keywords``, which Pivot returns space-joined).
        return self._meta(score).get("matched_subjects") or ""


class FellowshipSerializer(_OpportunitySerializer):
    """A matched fellowship for the Fellowships page.

    Emits the frontend contract agreed in the fellowships-integration plan.
    All eligibility + facet fields come from ``metadata``; ranking fields come
    from ``signals`` (persisted by the rule engine in ``_persist_fellowships``).
    """

    title = serializers.SerializerMethodField()
    award_class = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    amount_note = serializers.SerializerMethodField()
    deadline_type = serializers.SerializerMethodField()
    fields = serializers.SerializerMethodField(method_name="get_field_facets")
    stages = serializers.SerializerMethodField()
    citizenship = serializers.SerializerMethodField()
    award_types = serializers.SerializerMethodField()
    limits = serializers.SerializerMethodField()
    eligibility = serializers.SerializerMethodField()
    contact_email = serializers.SerializerMethodField()
    posted = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()
    gates_failed = serializers.SerializerMethodField()
    reasons = serializers.SerializerMethodField()
    fit = serializers.SerializerMethodField()

    def get_url(self, score: RelevanceScore) -> str:
        meta = self._meta(score)
        return (
            meta.get("external_url")
            or meta.get("website")
            or (score.content.source_url if score.content_id else "")
        )

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("title") or "Untitled fellowship"

    def get_award_class(self, score: RelevanceScore) -> str:
        return self._meta(score).get("award_class") or "fellowship"

    def get_amount(self, score: RelevanceScore) -> str:
        """Human-readable amount: prefer amount_raw, else derive from min/max."""
        meta = self._meta(score)
        raw = meta.get("amount_raw") or ""
        if raw:
            return raw
        lo = meta.get("amount_min")
        hi = meta.get("amount_max")
        cur = meta.get("amount_currency") or ""
        kind = meta.get("amount_kind") or ""
        if lo is not None and hi is not None and lo != hi:
            return f"{cur}${lo:,}–${hi:,}"
        if hi is not None:
            return f"Up to {cur}${hi:,}"
        if lo is not None:
            return f"{cur}${lo:,}+"
        if kind == "varies":
            return "Varies"
        return ""

    def get_amount_note(self, score: RelevanceScore) -> str:
        return self._meta(score).get("amount_note") or ""

    def get_deadline_type(self, score: RelevanceScore) -> str:
        deadline = self._meta(score).get("deadline") or {}
        return deadline.get("type") or self._meta(score).get("deadline_type") or ""

    def _facets(self, score: RelevanceScore) -> dict:
        return self._meta(score).get("facets") or {}

    def get_field_facets(self, score: RelevanceScore) -> list:
        return self._facets(score).get("field") or []

    def get_stages(self, score: RelevanceScore) -> list:
        return self._facets(score).get("stage") or []

    def get_citizenship(self, score: RelevanceScore) -> list:
        return self._facets(score).get("citizenship") or []

    def get_award_types(self, score: RelevanceScore) -> list:
        return self._facets(score).get("award_type") or []

    def get_limits(self, score: RelevanceScore) -> list:
        return self._facets(score).get("limits") or []

    def get_eligibility(self, score: RelevanceScore) -> list:
        return self._meta(score).get("eligibility") or []

    def get_contact_email(self, score: RelevanceScore) -> str:
        return self._meta(score).get("contact_email") or ""

    def get_posted(self, score: RelevanceScore) -> str:
        first_seen = (
            score.signals.get("first_seen")
            or self._meta(score).get("first_seen")
            or ""
        )
        return first_seen[:10] if first_seen else ""

    def get_tier(self, score: RelevanceScore) -> str:
        return score.signals.get("tier") or ""

    def get_gates_failed(self, score: RelevanceScore) -> list:
        return score.signals.get("gates_failed") or []

    def get_reasons(self, score: RelevanceScore) -> list:
        return score.signals.get("reasons") or []

    def get_fit(self, score: RelevanceScore) -> float | None:
        return score.signals.get("fit")


class SavedDeadlineSerializer(serializers.Serializer):
    """One saved deadline for the Deadlines page (reads the save snapshot).

    Backed by the save snapshot, not the live item, so it survives the daily prune
    of expired opportunities. ``days_remaining`` / ``within_week`` are computed
    from ``today`` in the serializer context.
    """

    id = serializers.UUIDField(read_only=True)
    content_id = serializers.SerializerMethodField()
    area = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    subtitle = serializers.CharField()
    deadline_date = serializers.DateField()
    deadline_kind = serializers.CharField()
    note = serializers.CharField()
    days_remaining = serializers.SerializerMethodField()
    within_week = serializers.SerializerMethodField()

    def get_content_id(self, saved: SavedOpportunity):
        return str(saved.content_id) if saved.content_id else None

    def get_days_remaining(self, saved: SavedOpportunity):
        return _days_until(saved.deadline_date, self.context.get("today_date"))

    def get_within_week(self, saved: SavedOpportunity) -> bool:
        days = self.get_days_remaining(saved)
        return days is not None and 0 <= days <= 7


def _days_until(deadline, today_date) -> int | None:
    """Whole days from ``today_date`` to ``deadline`` (``None`` if no deadline).

    Tolerates a string deadline (a freshly-created row not yet round-tripped
    through the DB carries the ISO string it was saved with).
    """
    if not deadline or today_date is None:
        return None
    if isinstance(deadline, str):
        try:
            deadline = date.fromisoformat(deadline[:10])
        except ValueError:
            return None
    return (deadline - today_date).days
