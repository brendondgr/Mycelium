import re
from datetime import UTC, date, datetime

from rest_framework import serializers

from apps.content.formatting import normalize_amount

from .models import ContentItem, RelevanceScore, SavedOpportunity


class ClusterAttributionMixin:
    """The three cluster fields, shared by papers and opportunities.

    Cluster attribution is a property of a scored row, not of papers specifically —
    the matcher writes the same ``cluster_id``/``per_cluster``/``bridge_cluster_ids``
    signals whichever content type it scored. Keeping the readers here means a grant
    card and a paper card resolve a renamed cluster identically instead of drifting.
    """

    def _cluster_label(self, cluster_id: str, persisted: str = "") -> str:
        # Resolve a cluster id to its *current* label so a renamed cluster shows
        # its new name everywhere without a re-score; fall back to the label frozen
        # in the signals when the caller supplied no live map (e.g. saves feed).
        labels = self.context.get("cluster_labels") or {}
        return labels.get(cluster_id) or persisted or ""

    def get_cluster(self, score):
        # {id, label} of the attributed (argmax) cluster, or null on the flat /
        # single-cluster path (no cluster attribution).
        cluster_id = score.signals.get("cluster_id")
        if not cluster_id:
            return None
        label = self._cluster_label(cluster_id, score.signals.get("cluster_label", ""))
        return {"id": cluster_id, "label": label}

    def get_per_cluster(self, score) -> dict:
        # {cluster_id -> [0,1] combined score} across every cluster this item
        # cleared; empty on the flat path.
        return score.signals.get("per_cluster") or {}

    def get_bridge_clusters(self, score) -> list:
        # Secondary "also relevant to …" clusters (the item cleared the floor in
        # >= 2 clusters); each resolved to its current {id, label}.
        ids = score.signals.get("bridge_cluster_ids") or []
        return [{"id": cid, "label": self._cluster_label(cid)} for cid in ids]


class SuggestionSerializer(ClusterAttributionMixin, serializers.Serializer):
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
    embedding_match = serializers.SerializerMethodField()
    per_interest = serializers.SerializerMethodField()
    matched_interests = serializers.SerializerMethodField()
    cluster = serializers.SerializerMethodField()
    per_cluster = serializers.SerializerMethodField()
    bridge_clusters = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    headline = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    pinned = serializers.SerializerMethodField()
    saved = serializers.SerializerMethodField()
    saved_labs = serializers.SerializerMethodField()

    def get_content_id(self, score: RelevanceScore) -> str:
        return str(score.content_id)

    def _meta(self, score: RelevanceScore) -> dict:
        return score.content.metadata or {}

    def _today(self) -> str:
        return self.context.get("today", "")

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

    def get_embedding_match(self, score: RelevanceScore):
        # The transformer (embedding) cosine match, 0–100, that this paper cleared to
        # be surfaced — what the cross-embedding tail shows in place of the language
        # model's percent. ``None`` on legacy rows written before the threshold.
        match = score.signals.get("embedding_match")
        return round(match * 100) if isinstance(match, (int, float)) else None

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
        # Always the paper's real title. Earlier pipeline versions let the model
        # invent a "headline" rename; ignore any still persisted in old signals —
        # researchers cite and recognize papers by their actual titles.
        return self.get_title(score)

    def get_reason(self, score: RelevanceScore) -> str:
        return score.signals.get("reason") or ""

    def get_origin(self, score: RelevanceScore) -> str:
        # "llm" when the language model wrote the reason, else "fallback".
        return score.signals.get("source") or "fallback"

    def get_pinned(self, score: RelevanceScore) -> bool:
        # Pinned (and the "New" tag shows) while the one-week window is still open.
        pinned_until = score.signals.get("pinned_until")
        return bool(pinned_until and pinned_until >= self._today())

    def get_is_new(self, score: RelevanceScore) -> bool:
        return bool(score.signals.get("is_new")) and self.get_pinned(score)

    def get_saved(self, score: RelevanceScore) -> bool:
        # Whether the reader bookmarked this paper (``saved_ids`` in context;
        # feeds that don't pass it simply render the flag as false).
        return str(score.content_id) in self.context.get("saved_ids", set())

    def get_saved_labs(self, score: RelevanceScore) -> list[str]:
        # Slugs of the reader's managed labs that already saved this item.
        return self.context.get("saved_labs", {}).get(str(score.content_id), [])


#: A date the client may parse: exactly ``YYYY-MM-DD``, nothing else. Used to
#: refuse — rather than reshape — anything else that turns up in a field the
#: frontend documents as ISO (``ConferenceOpportunity["event_date"]`` drives a
#: date-window filter and sort, so a half-date or a free-text month there is
#: worse than an empty string).
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

#: Collector deadline kind -> the ``SavedOpportunity.DeadlineKind`` name it is
#: reported under. Two vocabularies meet here and neither is imported:
#:
#: * ``apps.scraper.collect.conferences.record.SUBMISSION_TYPES`` is
#:   ``{"abstract", "submission"}`` — the only two kinds that mean "I can still
#:   act on this venue", which is why ``mapping.py::_conference_deadlines``
#:   gates ``deadline_date`` on exactly those and never on the event date.
#: * ``deadlines_projection._STRUCTURED_KIND_MAP`` renames the collector's
#:   ``submission`` to MANUSCRIPT, because it is the full-paper deadline
#:   despite the name.
#:
#: ``"manuscript"`` is accepted as an input key too, so an array already
#: written in the projection's own vocabulary is read rather than silently
#: dropped. Copied rather than imported for the reason
#: :mod:`apps.content.deadlines_projection` gives for copying the same table:
#: the content app does not depend on the collector's package at read time.
#: Every other collector kind (notification, camera_ready, registration, the
#: rebuttal pair, supplementary, unknown, and anything a future adapter
#: invents) is deliberately absent — none of them is something a submitter can
#: still act on, so none may ever read as "open".
_SUBMISSION_KIND_NAMES: dict[str, str] = {
    "abstract": SavedOpportunity.DeadlineKind.ABSTRACT.value,
    "submission": SavedOpportunity.DeadlineKind.MANUSCRIPT.value,
    "manuscript": SavedOpportunity.DeadlineKind.MANUSCRIPT.value,
}


def _instant(value) -> datetime | None:
    """Parse a collector deadline ``instant`` (``2026-09-15T11:59:00Z``), or None.

    Same tolerant handling as ``mapping.py::_parse_instant`` and
    ``deadlines_projection._parse_structured_instant``: swap the trailing ``Z``
    for an explicit offset before ``fromisoformat``, which also accepts the
    microsecond-precision instants a minority of live rows carry, and assume UTC
    for a naive value so two parsed moments are always comparable.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_today(today: str) -> date | None:
    """The serializer context's ``today`` as a date, or None if it carries none.

    Every feed view passes ``today`` (one clock read per request, so a page of
    cards cannot disagree with itself about what day it is). None here means a
    caller built this serializer without it — a question about "still upcoming"
    that genuinely has no answer, not a licence to read the clock here.
    """
    if not today:
        return None
    try:
        return date.fromisoformat(str(today)[:10])
    except ValueError:
        return None


def _event_dates_line(meta: dict) -> str:
    """A conference's human "when is it" line, as its source wrote it.

    Chained the same way as the venue line: the collector writes
    ``event_dates_text`` (deliberately verbatim — one source alone produces 131
    distinct date-format skeletons, so the string as written is the truth),
    Pivot wrote ``event_dates``. Both shapes coexist during the migration, so
    every reader chains rather than choosing.

    A bare run of digits is refused rather than shown: the ``openreview``
    adapter passes its source's ``start_date`` through untouched and that value
    is a millisecond epoch, so 261 of the 893 conferences carrying this key hold
    something like ``"1797552000000"``. That is not a date a reader can read,
    and a serializer is the wrong place to learn to parse one — the fix belongs
    in the adapter. Refusing it leaves those rows exactly as empty as they
    already were, instead of making them confidently wrong.
    """
    text = " ".join(str(meta.get("event_dates_text") or "").split())
    return (text if not text.isdigit() else "") or meta.get("event_dates") or ""


def _topic_list(meta: dict, ai_key: str, *collector_keys: str) -> list[str]:
    """The best available topic list for an item, in preference order.

    ``metadata["ai_fields"][ai_key]`` first: those are the topics ``extract.py``
    pulled from the venue's or funder's own page and then *verified* against it
    (grounding check, 2-6 entries, no duplicates), so they are both the richest
    and the only ones that were checked. The collector's own keys follow, in the
    order the caller lists them. Returns ``[]`` — never a string, never None —
    so a caller only has to decide the delimiter.
    """
    ai_fields = meta.get("ai_fields") or {}
    for candidate in (ai_fields.get(ai_key), *(meta.get(k) for k in collector_keys)):
        if isinstance(candidate, list) and candidate:
            cleaned = [" ".join(str(t).split()) for t in candidate]
            return [t for t in cleaned if t]
    return []


class _OpportunitySerializer(ClusterAttributionMixin, serializers.Serializer):
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
    embedding_match = serializers.SerializerMethodField()
    # Which of the reader's research themes this opportunity belongs to. The cards
    # have rendered a cluster badge since the cluster sprint; until the matcher
    # started scoring opportunities per cluster there was never anything to put in it.
    cluster = serializers.SerializerMethodField()
    per_cluster = serializers.SerializerMethodField()
    bridge_clusters = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    headline = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    pinned = serializers.SerializerMethodField()
    deadline_date = serializers.SerializerMethodField()
    deadline_kind = serializers.SerializerMethodField()
    # The addressable per-kind deadlines (ContentDeadline projection, R0). Named
    # distinctly from the conference ``deadlines`` raw string so a subclass can't
    # shadow it — every opportunity type exposes this array consistently.
    addressable_deadlines = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    saved = serializers.SerializerMethodField()
    saved_labs = serializers.SerializerMethodField()
    # Provenance, universal since the open-collector migration (plan Phase 9):
    # every area now carries which adapter produced the row, what it may be
    # reused under, and who to credit. Pivot never carried any of this — a
    # matched item's origin was invisible past its outbound link.
    source = serializers.SerializerMethodField()
    license = serializers.SerializerMethodField()
    license_url = serializers.SerializerMethodField()
    source_links = serializers.SerializerMethodField()
    summary_source = serializers.SerializerMethodField()
    search_text_source = serializers.SerializerMethodField()

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

    def get_summary_source(self, score: RelevanceScore) -> str:
        """Where ``description`` came from: ``""`` (the source) or a URL.

        Provenance must never blur. A model-written summary and a funder's own
        prose read identically once they are both a paragraph of text, so the
        client cannot be left to guess — it renders the "summarised from" marker
        off this field. An extraction that failed verification is refused and
        falls back to source text, and this field stays empty for it, which is
        the honest answer rather than a confident-looking one nobody checked.
        """
        return self._meta(score).get("summary_source") or ""

    def get_search_text_source(self, score: RelevanceScore) -> str:
        """``"extracted"`` or ``"raw"`` — which basis this row was embedded on.

        Exposed because a corpus mid-backfill contains both, and a relevance
        comparison that does not separate them is measuring two things at once.
        """
        return self._meta(score).get("search_text_source") or "raw"

    def get_source(self, score: RelevanceScore) -> str:
        # e.g. "grants:nsf", "conf:ccf_deadlines", "illinois-fellowship-finder" —
        # which adapter/provider produced this row. Namespaced by area (plan D6)
        # so a card can always tell a Pivot-era leftover from an open-collector
        # one mid-migration, and the frontend can credit the right source.
        return score.content.source if score.content_id else ""

    def get_license(self, score: RelevanceScore) -> str:
        # A short label ("MIT", "CC0-1.0", "US Government Work — …"), not a URL.
        # ``mapping.py`` carries this for grants (a per-source constant table)
        # and conferences (copied off the adapter); a fellowship carries none.
        return self._meta(score).get("license") or ""

    def get_license_url(self, score: RelevanceScore) -> str:
        # DISCREPANCY (see phase report): no source in the vendored collector
        # publishes a machine-readable licence URL onto any record the mapper can
        # read — ``openresearch``'s ``LICENSE_URL`` lives on the raw fetch bundle
        # (adapters/openresearch.py), a provenance record ``mapping.py`` never
        # sees, not on ``ConferenceSeries``/``ConferenceInstance``. Reading the
        # key here rather than hand-writing a lookup table keeps this field
        # honest — "" today, and it starts working the day a mapped field exists,
        # with no serializer change required.
        return self._meta(score).get("license_url") or ""

    def get_source_links(self, score: RelevanceScore) -> list[dict]:
        """Per-source attribution footer: one ``{source, url}`` per contributor.

        Conferences carry this ready-built — ``mapping.py::_source_links``
        already flattens ``contributing_sources`` onto ``metadata["source_links"]``
        because the collector's own dedupe stage can merge several adapters'
        records into one instance. Grants carry no such key (every federal/EU
        source publishes one record per opportunity number, so ``mapping.py``
        never needed the helper) but do carry the same ``contributing_sources``
        bookkeeping, so it is built here on the fly instead of leaving grants
        with no attribution at all. A fellowship has neither key and correctly
        renders an empty list — a single-source area with nothing to attribute.
        """
        meta = self._meta(score)
        links = meta.get("source_links")
        if links:
            return links
        sources = meta.get("contributing_sources") or []
        if not sources:
            return []
        url = self.get_url(score)
        return [{"source": src, "url": url} for src in sources]

    def get_match_percent(self, score: RelevanceScore):
        return score.signals.get("match_percent")

    def get_embedding_match(self, score: RelevanceScore):
        # The transformer (embedding) cosine match, 0–100, a threshold-gated
        # opportunity cleared to be surfaced — shown on the tail (no model percent).
        # ``None`` for fixed-slice areas and legacy rows written before the threshold.
        match = score.signals.get("embedding_match")
        return round(match * 100) if isinstance(match, (int, float)) else None

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
        """What kind of deadline ``deadline_date`` is — never a different one.

        ``signals["next_kind"]`` is written at match time from
        ``metadata["next_kind"]``, and only the fellowship ingest
        (``apps.scraper.fellowships.records``) ever writes that key. The open
        collector's mapper writes none, so every grant and conference in the
        rebuilt corpus serialized "" here while its ``deadline_date`` sat right
        next to it — the field the grant page's "kind" facet is built from was
        empty for 100% of rows, and nothing failed.

        The fallback is delegated to :meth:`_derive_deadline_kind` per area
        rather than guessed generically: the one rule that matters is that the
        kind must name *the same deadline* ``deadline_date`` points at. A kind
        that names a different round is worse than none at all — it would tell a
        reader the abstract closes on the manuscript's date — so an area that
        cannot prove the correspondence returns "" and this stays empty.
        """
        return score.signals.get("next_kind") or self._derive_deadline_kind(score)

    def _derive_deadline_kind(self, score: RelevanceScore) -> str:
        """Name ``deadline_date``'s kind from metadata; "" unless it is provable.

        The base answer is "" — a fellowship reaches this only when its ingest
        wrote no ``next_kind``, which it does exactly when the record carries no
        date either, so there is nothing to name.
        """
        return ""

    def get_addressable_deadlines(self, score: RelevanceScore) -> list[dict]:
        """Every addressable deadline (the ContentDeadline projection, R0).

        One entry per **round**, not per kind: a conference routinely carries a
        workshop deadline, more than one full-paper round, a camera-ready and its
        event date, and each of those is separately remindable. Chronological, so
        a client can render the list without re-sorting; ``is_next`` marks the
        one a card's headline reads.

        Additive to the scalar ``deadline_date``/``deadline_kind`` (which existing
        cards still read). Reads a prefetched ``deadlines_by_content`` context map
        when the view provides one, else falls back to the item's related rows.
        """
        if not score.content_id:
            return []
        by_content = self.context.get("deadlines_by_content")
        if by_content is not None:
            rows = by_content.get(score.content_id, [])
        else:
            rows = list(score.content.deadline_rows.all())
        return [
            {
                "kind": row.kind,
                # Which round of that kind, for an item carrying several. A
                # client sends this back verbatim to set a reminder on *that*
                # round; "" is the single-round case.
                "round_key": row.round_key,
                "round_label": row.round_label,
                "is_next": row.is_next,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "confidence": row.confidence,
                "label": row.label,
            }
            for row in sorted(
                rows, key=lambda r: (r.due_date is None, r.due_date, r.kind)
            )
        ]

    def get_status_summary(self, score: RelevanceScore) -> str:
        return score.signals.get("status_summary") or ""

    def get_saved(self, score: RelevanceScore) -> bool:
        return str(score.content_id) in self.context.get("saved_ids", set())

    def get_saved_labs(self, score: RelevanceScore) -> list[str]:
        return self.context.get("saved_labs", {}).get(str(score.content_id), [])


class GrantSerializer(_OpportunitySerializer):
    """A matched funding opportunity for the Opportunities page (grants column)."""

    title = serializers.SerializerMethodField()
    sponsor = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    matched_topics = serializers.SerializerMethodField()
    posted = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    # The open-collector fields (plan Phase 3/9) that Pivot never carried: the
    # funder's own identifiers and dates, and the full multi-round array behind
    # the single ``deadline_date`` the base class already exposes.
    opportunity_number = serializers.SerializerMethodField()
    due_dates = serializers.SerializerMethodField()
    deadline_text = serializers.SerializerMethodField()
    dates_inferred = serializers.SerializerMethodField()
    original_deadline = serializers.SerializerMethodField()
    loi_date = serializers.SerializerMethodField()
    published_on = serializers.SerializerMethodField()

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("title") or "Untitled grant"

    def get_sponsor(self, score: RelevanceScore) -> str:
        # Chained, not swapped, and in the same order ``daily_report._source_line``
        # already reads a grant's provenance line: Pivot wrote ``sponsor``, the
        # open collector writes ``funder``. Reading only the Pivot key blanked
        # the sponsor on all 2,171 rebuilt grants — the funder is the single
        # most identifying thing on a funding card, and it was missing from the
        # card, the sponsor facet and the search extra alike.
        # ``funder_canonical`` is last and is *not* preferred over ``funder``:
        # keeping the raw name first is what makes a card and its report line
        # say the same thing. It differs on 208 of 2,171 rows (a normalised
        # parent-agency name), so it is worth having as a last resort rather
        # than rendering nothing for a row that somehow carries only it.
        meta = self._meta(score)
        return (
            meta.get("sponsor")
            or meta.get("funder")
            or meta.get("funder_canonical")
            or ""
        )

    def get_amount(self, score: RelevanceScore) -> str:
        # Distil at read time too: rows ingested before the normalizer existed
        # still carry a whole budget paragraph, which would spam the card.
        return normalize_amount(self._meta(score).get("amount") or "")

    def get_matched_topics(self, score: RelevanceScore) -> str:
        """The grant's topic tags, semicolon-delimited (the shape the page splits).

        Same Pivot-key-outlives-Pivot failure as ``sponsor`` above:
        ``matched_topics`` is Pivot's key and no rebuilt grant carries it, so
        the Opportunities page's whole topic facet was derived from an empty
        string on every row. The delimiter is load-bearing —
        ``grant-filters.tsx::splitTopics`` splits on ``";"`` — so the type and
        the separator are preserved exactly; only where the values come from
        changed.

        ``ai_fields["research_areas"]`` (2,150 of 2,171 rows) is preferred over
        the source's own ``categories`` (1,833) because it is verified against
        the funder's page and reads like a research area rather than a funding
        bucket ("Artificial Intelligence" vs "Science and Technology and other
        Research and Development").

        ``topic_keywords`` is deliberately **not** in this chain, despite being
        the collector's most topic-sounding key. All 579 rows that carry it are
        ``grants:eu_portal``, and every value is a call identifier
        (``HORIZON-JU-EUROHPC-2026-QTI-13-01``), not a topic; feeding those into
        a facet list would fill the sidebar with machine codes. Exactly one live
        grant would gain a value from it, and that value would be a code.
        """
        meta = self._meta(score)
        topics = _topic_list(meta, "research_areas", "categories")
        return "; ".join(topics) or meta.get("matched_topics") or ""

    def get_published_on(self, score: RelevanceScore) -> str:
        # The funder's own publication date (``mapping.py``'s ``posted_date``),
        # not when Mylo first ingested the row. Exposed separately from
        # ``posted`` (below) because the two questions genuinely differ once the
        # feed carries pre-migration Pivot leftovers with no such key.
        return self._meta(score).get("published_on") or ""

    def get_posted(self, score: RelevanceScore) -> str:
        # Repointed (plan Phase 9 — this was the bug): a grant genuinely posted
        # by its funder in 2015 used to show the day *Mycelium* ingested it,
        # because this read ``signals["first_seen"]`` unconditionally. Prefer
        # the funder's own ``metadata["published_on"]`` and fall back to the old
        # behaviour only for a row that carries no such key — a pre-migration
        # Pivot leftover still living in the corpus, not a genuine "unknown".
        published_on = self._meta(score).get("published_on")
        if published_on:
            return published_on
        return score.signals.get("first_seen") or ""

    def get_description(self, score: RelevanceScore) -> str:
        # A human-readable blurb: the verified extraction if one survived, else
        # the source's own text. ``summary_source`` below is what tells the two
        # apart — never infer it from this string.
        meta = self._meta(score)
        return meta.get("ai_summary") or meta.get("abstract") or ""

    def get_opportunity_number(self, score: RelevanceScore) -> str:
        return self._meta(score).get("opportunity_number") or ""

    def get_due_dates(self, score: RelevanceScore) -> list[str]:
        # The complete application-round array behind the single next-due
        # ``deadline_date`` — what the multi-deadline hover (plan D1) renders.
        return self._meta(score).get("due_dates") or []

    def get_deadline_text(self, score: RelevanceScore) -> str:
        # The funder's own free-text deadline line, kept verbatim alongside the
        # parsed ``deadline_date`` for a reader who wants the source wording.
        return self._meta(score).get("deadline_text") or ""

    def get_dates_inferred(self, score: RelevanceScore) -> bool:
        # True when the collector estimated this record's dates rather than
        # reading them verbatim — the grant-side twin of a conference's
        # ``confidence: "anticipated"`` (see deadlines_projection.py).
        return bool(self._meta(score).get("dates_inferred"))

    def get_original_deadline(self, score: RelevanceScore) -> str:
        # The first-ever recorded close date, kept even after a funder moves it
        # — lets a reader see that a deadline shifted, not just what it is now.
        return self._meta(score).get("original_deadline") or ""

    def get_loi_date(self, score: RelevanceScore) -> str:
        # Letter-of-intent date, when the funder requires one ahead of the
        # full application — absent for the large majority of grants.
        return self._meta(score).get("loi_date") or ""

    def _derive_deadline_kind(self, score: RelevanceScore) -> str:
        """A dated grant's deadline is always its application deadline.

        The correspondence the base class insists on holds by construction here
        rather than by matching: a grant's ``deadline_date`` is
        ``select_next_due(rounds, today)`` over ``close_date`` plus
        ``additional_due_dates`` (``mapping.py::_grant_deadlines``), and every
        one of those rounds is a round of the *same* application. That is why
        ``deadlines_projection._grant_specs`` also projects exactly one
        APPLICATION row per grant, whichever round is next. Naming the round
        (round 3 of 10) is not something this field can carry — the unique key
        on the projection is ``(content, kind)`` precisely so a single round is
        never separately addressable — and ``due_dates`` already exposes the
        full array for the hover.

        No date means no deadline to name: a grant with an empty
        ``deadline_date`` is rolling (mapping.py's ``"" = rolling, never
        expires``), and calling that an application deadline would invent one.
        """
        if not self.get_deadline_date(score):
            return ""
        return SavedOpportunity.DeadlineKind.APPLICATION.value


#: A short "what this system is" line per ranking system, keyed the same
#: lowercase way the collector itself does (``adapters/ccf_deadlines.py``'s
#: ``RANK_SYSTEMS = ("ccf", "core", "thcpl")`` — verified against the vendored
#: source, not guessed). No explanation of any of these three exists as data
#: anywhere in the open collector (grepped the vendored tree for "rank" prose;
#: zero hits), so this is authored copy, not a port of anything.
RANK_SYSTEM_INFO: dict[str, dict[str, str]] = {
    "ccf": {
        "label": "CCF",
        "about": (
            "The China Computer Federation's recommended venue list — the most "
            "widely cited computer-science ranking outside China. Roughly a "
            "third of ranked venues sit in each of its three bands; most "
            "computing venues carry no CCF rank at all."
        ),
    },
    "core": {
        "label": "CORE",
        "about": (
            "The Computing Research and Education Association of Australasia's "
            "conference ranking, historically used across Australia and New "
            "Zealand and referenced informally worldwide. Its top band splits "
            "further into A*, one level above plain A."
        ),
    },
    "thcpl": {
        "label": "THCPL",
        "about": (
            "Tsinghua University's Computer Science Conference and Journal "
            "Recommendation List — internal guidance on which venues count "
            "toward a strong publication record, since referenced by several "
            "other institutions' own lists."
        ),
    },
}

#: Per-rank hover prose, keyed ``{system: {rank: text}}``. Only the ranks the
#: live corpus actually carries are covered (plan Phase 9: CCF A/B/C, CORE
#: A*/A/B/C, THCPL A/B) — "N" ("not ranked by this system") is deliberately
#: excluded here because ``mapping.py::_rank_badges`` already drops it before a
#: badge is ever built, so a client resolving a badge against this map will
#: never look up "N".
#:
#: Every entry is careful to say nothing about *when* a rank was assigned.
#: ``edition`` is "" on every ranking in this dataset (mapping.py denormalises
#: ``ConferenceSeries.rankings`` verbatim, and the source never populates the
#: field) — so this copy states what a rank means, never what year it was
#: decided, and a client must not print a year next to it either.
RANK_EXPLANATIONS: dict[str, dict[str, str]] = {
    "ccf": {
        "A": (
            "CCF's top band: the flagship venues of their subfield, the ones a "
            "hiring or tenure committee will recognise by name alone."
        ),
        "B": (
            "CCF's second band: well-established, competitive venues — a solid "
            "target, one step below the handful that define a subfield."
        ),
        "C": (
            "CCF's entry band: recognised and reviewed, but not yet judged to "
            "carry the weight of an A or B venue on its own."
        ),
    },
    "core": {
        "A*": (
            "CORE's highest band, reserved for a small set of exceptional "
            "flagship venues — a level above plain A, not a variant of it."
        ),
        "A": "CORE's top general band: excellent, competitive venues widely "
        "regarded within their field.",
        "B": (
            "CORE's second band: good, respected venues — a legitimate target, "
            "one step below the top rank."
        ),
        "C": "CORE's entry band: known and reviewed, sitting below A and B.",
    },
    "thcpl": {
        "A": (
            "THCPL's top band — venues the list treats as carrying full weight "
            "for a strong publication record."
        ),
        "B": (
            "THCPL's second band — respected and countable, one step below the "
            "list's top tier."
        ),
    },
}

#: Exposed once at ``GET /api/opportunities/ranking-reference/``
#: (``views.RankingReferenceView``) rather than repeated on every conference
#: row: the prose above is identical for every card sharing a rank, and a
#: single feed page can carry dozens of conferences — duplicating it per row
#: would multiply payload size for zero new information per item. A card only
#: needs to carry *which* rank it has (``rank_badges``, small); the client
#: resolves the hover text from this table once and caches it, the same
#: pattern the frontend already uses for the static ``FEATURE``
#: entitlement-slug table.


class ConferenceSerializer(_OpportunitySerializer):
    """A matched conference for the Conferences page (card format)."""

    title = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    event_dates = serializers.SerializerMethodField()
    event_date = serializers.SerializerMethodField()
    deadlines = serializers.SerializerMethodField()
    keywords = serializers.SerializerMethodField()
    matched_subjects = serializers.SerializerMethodField()
    abstract_open = serializers.SerializerMethodField()
    manuscript_open = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    # Quality signals the open collector carries that Pivot never did (plan
    # D2): rankings are visual-only badges. See RANK_EXPLANATIONS above for the
    # hover copy a client resolves them against.
    acronym = serializers.SerializerMethodField()
    year_label = serializers.SerializerMethodField()
    rankings = serializers.SerializerMethodField()
    rank_badges = serializers.SerializerMethodField()
    red_flags = serializers.SerializerMethodField()
    quality_warnings = serializers.SerializerMethodField()
    deadlines_structured = serializers.SerializerMethodField()

    def get_title(self, score: RelevanceScore) -> str:
        return self._meta(score).get("name") or "Untitled conference"

    def get_acronym(self, score: RelevanceScore) -> str:
        return self._meta(score).get("acronym") or ""

    def get_year_label(self, score: RelevanceScore) -> str:
        return self._meta(score).get("year_label") or ""

    def get_rankings(self, score: RelevanceScore) -> dict:
        # The raw ``{system: {rank, edition}}`` map verbatim, "N" entries
        # included — a real "not ranked by this system" statement (plan D2),
        # distinct from the field being absent. ``rank_badges`` below is the
        # display-ready flattening that drops "N", for a client that only
        # wants to render claimed ranks.
        return self._meta(score).get("rankings") or {}

    def get_rank_badges(self, score: RelevanceScore) -> list[dict]:
        # ``[{system, rank, edition}]``, "N" already excluded by
        # ``mapping.py::_rank_badges`` — what the card's badge row renders.
        # ``edition`` is always "" in this data (see RANK_EXPLANATIONS' note);
        # a client must not read a year into it.
        return self._meta(score).get("rank_badges") or []

    def get_red_flags(self, score: RelevanceScore) -> list[str]:
        return self._meta(score).get("red_flags") or []

    def get_quality_warnings(self, score: RelevanceScore) -> list[str]:
        return self._meta(score).get("quality_warnings") or []

    def get_deadlines_structured(self, score: RelevanceScore) -> list[dict]:
        # The full multi-round deadline array (plan D1) — what the hover on the
        # scalar ``deadline_date``/``deadlines`` shows in full, every kind and
        # every round, not just the one the base class gates openness on.
        return self._meta(score).get("deadlines_structured") or []

    def get_location(self, score: RelevanceScore) -> str:
        meta = self._meta(score)
        # Chained: the collector writes ``place_text``, Pivot wrote ``location``,
        # and both shapes coexist during the migration. Swapping rather than
        # chaining would blank the venue for every record already in the table.
        place = meta.get("place_text") or meta.get("location")
        return ", ".join(p for p in (place, meta.get("country")) if p)

    def get_country(self, score: RelevanceScore) -> str:
        return self._meta(score).get("country") or ""

    def get_event_dates(self, score: RelevanceScore) -> str:
        # Chained (see :func:`_event_dates_line`): the collector writes
        # ``event_dates_text``, Pivot wrote ``event_dates``, and reading only
        # the Pivot key left every rebuilt conference card with no date line.
        return _event_dates_line(self._meta(score))

    def get_deadlines(self, score: RelevanceScore) -> str:
        return self._meta(score).get("deadlines") or ""

    def get_keywords(self, score: RelevanceScore) -> str:
        """Pivot's space-joined keyword blob — same shape, new source.

        ``keywords`` is Pivot's key and no rebuilt conference carries it. The
        collector's equivalent is ``topics``, and the verified extraction's
        ``ai_fields["topics"]`` is better still (see :func:`_topic_list`): it
        covers 776 of 912 conferences against ``topics``' 70, and it carries
        real subject words rather than the CCF area names the code table
        expands to.

        Space-joined, not semicolon-joined, on purpose — this field's whole
        contract is that it is the loose blob and ``matched_subjects`` is the
        chippable one. Anything that splits this on a delimiter is already
        wrong; changing the join here would only hide that.
        """
        meta = self._meta(score)
        return " ".join(_topic_list(meta, "topics", "topics")) or (
            meta.get("keywords") or ""
        )

    def get_matched_subjects(self, score: RelevanceScore) -> str:
        # Semicolon-delimited subject categories — clean, chippable topic tags
        # (unlike ``keywords``, which Pivot returns space-joined). Same source
        # chain and same silent-emptiness fix as ``keywords`` above; the
        # delimiter is load-bearing (``conference-filters.tsx::subjectTags`` and
        # the card both split on ";"), so only the source of the values changed.
        meta = self._meta(score)
        return "; ".join(_topic_list(meta, "topics", "topics")) or (
            meta.get("matched_subjects") or ""
        )

    def get_event_date(self, score: RelevanceScore) -> str:
        """The (first) event date as ISO ``YYYY-MM-DD``, or "".

        Drives the event-date window filter and sort; ``event_dates`` above
        remains the human display string. Chained: the collector writes
        ``event_start``, Pivot wrote ``event_date``.

        Only an already-ISO value is passed through. The collector's own
        ``event_start`` is ISO on all 347 live rows that carry one, so the
        guard costs nothing today; what it buys is the guarantee that no
        free-text date ever reaches a client that will parse this and sort by
        it. ``event_dates_text`` is deliberately not a fallback here — turning
        "February 22 - March 1, 2022" into a date needs a parser, and a
        mis-parsed date silently reorders the feed, which is a worse failure
        than an absent one.
        """
        meta = self._meta(score)
        value = str(meta.get("event_start") or meta.get("event_date") or "").strip()
        return value if _ISO_DATE.fullmatch(value) else ""

    def get_abstract_open(self, score: RelevanceScore) -> bool:
        # True while an abstract-submission deadline is still upcoming.
        return self._submission_open(
            score, SavedOpportunity.DeadlineKind.ABSTRACT.value
        )

    def get_manuscript_open(self, score: RelevanceScore) -> bool:
        # True while a full-paper (manuscript) submission deadline is still upcoming.
        return self._submission_open(
            score, SavedOpportunity.DeadlineKind.MANUSCRIPT.value
        )

    def _submission_open(self, score: RelevanceScore, family: str) -> bool:
        """Is a still-future deadline of ``family`` on this record?

        ``metadata["abstract_open"]`` / ``["manuscript_open"]`` are Pivot keys
        that the open collector never writes, so both flags read False for the
        whole rebuilt corpus while the dates that decide them sat in
        ``metadata["deadlines_structured"]`` — 174 abstract and 750 submission
        entries across the live conferences. Derived here rather than added to
        the mapper because openness is a function of *when it is read*: a flag
        frozen at ingest is wrong the morning after the deadline passes, and
        this serializer already gets the request's ``today`` in its context for
        exactly that reason (the same one ``pinned`` uses).

        Only ``abstract`` and ``submission`` count — the domain rule the whole
        deadline stack is built on (``SUBMISSION_TYPES``; see
        :data:`_SUBMISSION_KIND_NAMES`). A notification or camera-ready date is
        something the venue does *to* a submitter, and the event date is not a
        deadline at all, so neither can make a venue read as open.

        Deadline day itself counts as open, matching
        ``deadlines_projection._conference_specs``' ``due < today_date`` cut. A
        context with no usable ``today`` cannot answer the question at all and
        returns the Pivot flag alone rather than a guess.
        """
        meta = self._meta(score)
        legacy = bool(
            meta.get(
                "abstract_open"
                if family == SavedOpportunity.DeadlineKind.ABSTRACT.value
                else "manuscript_open"
            )
        )
        today = _iso_today(self._today())
        if today is None:
            return legacy
        for entry in meta.get("deadlines_structured") or []:
            if not isinstance(entry, dict):
                continue
            if _SUBMISSION_KIND_NAMES.get(entry.get("kind") or "") != family:
                continue
            moment = _instant(entry.get("instant"))
            if moment is not None and moment.date() >= today:
                return True
        return legacy

    def _derive_deadline_kind(self, score: RelevanceScore) -> str:
        """Name the deadline ``deadline_date`` points at — or nothing.

        ``deadline_date`` is the date part of the earliest *future*
        submission-family instant on the record, chosen by
        ``mapping.py::_conference_deadlines`` over exactly the kinds
        :data:`_SUBMISSION_KIND_NAMES` covers. This re-reads that same array and
        names the entry that produced it: the earliest submission-family instant
        whose own date equals the date being shown.

        Matching on the date rather than recomputing "next future" is what makes
        the answer correspond to the deadline the card actually displays. The
        two can differ — ``deadline_date`` was snapshotted into ``signals`` at
        match time and today is a later day — and in that case the honest
        result is "": no entry matches, nothing is named, and the reader is
        never told the abstract closes on the manuscript's date.
        """
        due = self.get_deadline_date(score)
        if not due:
            return ""
        winner: tuple[datetime, str] | None = None
        for entry in self._meta(score).get("deadlines_structured") or []:
            if not isinstance(entry, dict):
                continue
            named = _SUBMISSION_KIND_NAMES.get(entry.get("kind") or "")
            moment = _instant(entry.get("instant")) if named else None
            if moment is None or moment.date().isoformat() != due:
                continue
            if winner is None or moment < winner[0]:
                winner = (moment, named)
        return winner[1] if winner else ""

    def get_status(self, score: RelevanceScore) -> str:
        # Submission status: "open" | "closed" | "unknown". Persisted in signals at
        # match time; fall back to the item metadata for rows written before it.
        return score.signals.get("status") or self._meta(score).get("status") or ""

    def get_scope(self, score: RelevanceScore) -> str:
        # Pivot's "Scope" section verbatim — in practice the venue's own prose
        # description of the call, not a one-word label. Kept for compatibility;
        # ``description`` is the cleaned-up field the card renders.
        return self._meta(score).get("scope") or ""

    def get_description(self, score: RelevanceScore) -> str:
        """The conference blurb, preferring the verified extraction.

        This override exists because Pivot filed a conference's blurb under
        ``scope`` rather than ``abstract``, so the base implementation's
        fallback was wrong for this one type. That reason expired with Pivot:
        the open collector writes no ``scope`` at all, and the description a
        reader should see is the LLM extraction that ``extract.py`` verified
        and that the record was embedded on.

        Reading ``scope`` alone made this silently return "" for every one of
        912 conferences while 776 of them held a verified ``ai_summary`` --
        the same shape as the ``location``/``place_text`` regression, a
        Pivot-era key outliving Pivot inside an override. ``scope`` stays last
        in the chain for as long as any Pivot-era row survives; drop it, and
        this whole override, once none do.

        Whitespace-collapsed; "" when nothing carries a blurb, which the card
        must still render without.
        """
        meta = self._meta(score)
        text = meta.get("ai_summary") or meta.get("description") or meta.get("scope")
        return " ".join(str(text or "").split())


class FellowshipSerializer(_OpportunitySerializer):
    """A matched fellowship for the Fellowships page.

    Emits the frontend contract agreed in the fellowships-integration plan.
    All eligibility + facet fields come from ``metadata``; ranking fields come
    from ``signals`` (persisted in ``_persist_fellowships``). ``origin`` is
    ``"llm"`` when Mylo wrote the tailored report over the eligibility-gated list,
    or ``"rules"`` when the model was unavailable and the rule engine's own
    eligibility summary is shown. ``tier`` (qualified/conditional) carries the
    eligibility verdict independent of the reason's origin.
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
    description = serializers.SerializerMethodField()

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

    def get_description(self, score: RelevanceScore) -> str:
        # The fellowship's own blurb from the source listing (Illinois Fellowship
        # Finder "description" section) — distinct from the eligibility bullets.
        # Prefer the fuller ``description``, fall back to the shorter ``blurb``;
        # whitespace-collapsed (source descriptions carry newlines/odd spacing).
        meta = self._meta(score)
        text = meta.get("description") or meta.get("blurb") or ""
        return " ".join(str(text).split())


#: Metadata keys tried (in order) for the outbound link, per content type.
_URL_KEYS = ("pdf_url", "external_url", "website", "url")

#: Metadata keys tried (in order) for the result summary/snippet.
_SUMMARY_KEYS = ("abstract", "ai_summary", "search_text", "description")

#: How long a summary snippet may get before it is trimmed for the card.
_SUMMARY_MAX = 400


class SearchResultSerializer(serializers.Serializer):
    """One search hit, read straight off a :class:`ContentItem` (no score row).

    The query-first search path (:mod:`apps.content.search`) ranks the corpus
    directly, so — unlike the digest/opportunity serializers — this reads the
    global item, not a per-target :class:`RelevanceScore`. It exposes one unified
    shape (id/type/title/summary/url/created_at + the fused ``score`` and
    which ``matched_on`` channels) plus the compact type-specific extras the
    result card renders. ``score``/``matched_on`` come from transient attributes
    the search module tags onto each item; ``saved`` reads ``saved_ids`` from the
    serializer context.
    """

    content_id = serializers.SerializerMethodField()
    type = serializers.CharField()
    title = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    score = serializers.SerializerMethodField()
    matched_on = serializers.SerializerMethodField()
    cluster = serializers.SerializerMethodField()
    saved = serializers.SerializerMethodField()
    saved_labs = serializers.SerializerMethodField()
    # Compact type-specific extras (mostly null off-type; the card branches).
    authors = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    sponsor = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    event_dates = serializers.SerializerMethodField()
    award_class = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()

    def _meta(self, item: ContentItem) -> dict:
        return item.metadata or {}

    def get_content_id(self, item: ContentItem) -> str:
        return str(item.id)

    def get_title(self, item: ContentItem) -> str:
        meta = self._meta(item)
        return meta.get("title") or meta.get("name") or "Untitled"

    def get_summary(self, item: ContentItem) -> str:
        meta = self._meta(item)
        for key in _SUMMARY_KEYS:
            value = meta.get(key)
            if value:
                text = str(value).strip()
                if len(text) > _SUMMARY_MAX:
                    text = text[:_SUMMARY_MAX].rstrip() + "…"
                return text
        return ""

    def get_url(self, item: ContentItem) -> str:
        meta = self._meta(item)
        for key in _URL_KEYS:
            if meta.get(key):
                return str(meta[key])
        return item.source_url or ""

    def get_score(self, item: ContentItem) -> float:
        return float(getattr(item, "_search_score", 0.0) or 0.0)

    def get_matched_on(self, item: ContentItem) -> list:
        return list(getattr(item, "_search_matched_on", []) or [])

    def get_cluster(self, item: ContentItem):
        # {id, label} of the reader's cluster this result best fits (lexical
        # overlap; see SearchView), or null when the reader has < 2 clusters or the
        # result overlaps none of them. Lets search cards carry the same "· Cluster"
        # attribution as the feed.
        return getattr(item, "_cluster", None)

    def get_saved(self, item: ContentItem) -> bool:
        return str(item.id) in self.context.get("saved_ids", set())

    def get_saved_labs(self, item: ContentItem) -> list[str]:
        return self.context.get("saved_labs", {}).get(str(item.id), [])

    def get_authors(self, item: ContentItem) -> list:
        authors = self._meta(item).get("authors")
        return authors[:6] if isinstance(authors, list) else []

    def get_venue(self, item: ContentItem) -> str:
        return self._meta(item).get("venue") or ""

    def get_year(self, item: ContentItem):
        return self._meta(item).get("year")

    def get_sponsor(self, item: ContentItem) -> str:
        # The same chain, and the same reason for it, as
        # ``GrantSerializer.get_sponsor``: Pivot's ``sponsor`` outlived Pivot in
        # this reader too, so a grant hit in unified search carried no funder.
        meta = self._meta(item)
        return (
            meta.get("sponsor")
            or meta.get("funder")
            or meta.get("funder_canonical")
            or ""
        )

    def get_amount(self, item: ContentItem) -> str:
        meta = self._meta(item)
        if item.type == ContentItem.Type.GRANT:
            return normalize_amount(meta.get("amount") or "")
        return meta.get("amount_raw") or ""

    def get_location(self, item: ContentItem) -> str:
        meta = self._meta(item)
        # Chained: the collector writes ``place_text``, Pivot wrote ``location``,
        # and both shapes coexist during the migration. Swapping rather than
        # chaining would blank the venue for every record already in the table.
        place = meta.get("place_text") or meta.get("location")
        return ", ".join(p for p in (place, meta.get("country")) if p)

    def get_event_dates(self, item: ContentItem) -> str:
        # Chained exactly as the conference card's own field is; see
        # :func:`_event_dates_line`. A search hit and a feed card showing
        # different dates for one venue is the drift this shared helper avoids.
        return _event_dates_line(self._meta(item))

    def get_award_class(self, item: ContentItem) -> str:
        if item.type != ContentItem.Type.FELLOWSHIP:
            return ""
        return self._meta(item).get("award_class") or "fellowship"

    def get_deadline(self, item: ContentItem) -> str:
        """A best-effort deadline string from whatever key the type carries."""
        meta = self._meta(item)
        deadline = meta.get("deadline")
        if isinstance(deadline, dict):
            deadline = deadline.get("date") or deadline.get("type")
        return str(
            meta.get("deadline_date") or deadline or meta.get("deadlines") or ""
        )


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


#: Which feed serializer renders each saved area's ``card`` payload — the same
#: classes the area's own page uses, so saved cards match their feeds exactly.
_SAVED_CARD_SERIALIZERS = {
    SavedOpportunity.Area.GRANT: GrantSerializer,
    SavedOpportunity.Area.CONFERENCE: ConferenceSerializer,
    SavedOpportunity.Area.FELLOWSHIP: FellowshipSerializer,
    SavedOpportunity.Area.PAPER: SuggestionSerializer,
}


class SavedItemSerializer(SavedDeadlineSerializer):
    """One bookmark for the Saves page: the snapshot plus a feed-parity card.

    ``card`` is the exact payload the item's own feed page serializer emits. It is
    built from the target's :class:`RelevanceScore` row (passed in the context as
    ``scores_by_content``) when one exists; otherwise — while the source item is
    still live in the corpus — it falls back to a neutral, in-memory score over the
    live item so the full card still renders. ``card`` is ``null`` **only** once the
    item was pruned (``content`` is ``SET_NULL``), and the snapshot fields on the
    envelope are then the fallback display.
    """

    saved_at = serializers.DateTimeField(source="created_at", read_only=True)
    card = serializers.SerializerMethodField()

    def get_card(self, saved: SavedOpportunity):
        serializer_class = _SAVED_CARD_SERIALIZERS.get(saved.area)
        # No live item left (pruned → SET_NULL) or an unknown area: only the
        # snapshot remains, so signal "listing closed" with a null card.
        if not saved.content_id or serializer_class is None:
            return None
        score = (self.context.get("scores_by_content") or {}).get(saved.content_id)
        if score is None:
            # The item is still live but was never scored for this target — e.g. a
            # grant saved to a lab the daily match never surfaced it for. Render the
            # real card from the live item with a neutral (unscored) placeholder;
            # this is NOT the pruned case, so it must not read as "listing closed".
            score = RelevanceScore(content=saved.content, score=0.0, signals={})
        return serializer_class(score, context=self.context).data


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
