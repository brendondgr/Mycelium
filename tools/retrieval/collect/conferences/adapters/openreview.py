"""OpenReview: typed, machine-readable deadlines, no HTML and no date guessing.

OpenReview (openreview.net) is the open peer-review platform behind most of the
ML conference world (ICLR, NeurIPS, ICML, AAAI, ACL/EMNLP workshops, CVPR/ECCV
tracks, CoRL, AAMAS, MICCAI...) plus a long tail of workshops and shared tasks.
Its v2 API exposes *groups* (venues) and *invitations* (submission calls) fully
anonymously. Deadlines live on the invitation as epoch-millisecond integers, not
scraped prose -- the only source in this collector with no timezone ambiguity
at all.

**Access is three batched stages, not two requests per venue.** Stage 3 needs
the `submission_id` each venue publishes in stage 2's payload, so all three
have to live inside ``fetch`` -- this is the exact "fetch may be many requests"
case ``base.py``'s module docstring names this adapter as the example of.

    1. ``GET /groups?id=active_venues``            -> ~1075 venue ids, 1 request
    2. ``GET /groups?ids=<chunk>``                  -> venue records, chunked
    3. ``GET /invitations?ids=<chunk>&expired=true`` -> typed deadlines, chunked

Measured live: 18 requests, ~7s unthrottled, for the whole active roster.

Two traps dominate this source and both are silent unless guarded against:
``ids=`` returns HTTP 200 with an *empty list* for anything not readable --
never a 403 -- so 46/1073 active venues yield no deadline with no error at
all; and 198/1075 "multi-round" venues publish the *abstract* deadline where
a naive reader would expect the paper deadline, because the real one lives on
a ``Full_Submission`` invitation that is not publicly readable for any of
them. Both are handled below, not silently absorbed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from tools.retrieval.collect.conferences.adapters.base import BaseConferenceAdapter
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
    DeadlineType,
    RecordKind,
)
from tools.retrieval.collect.conferences.timezones import (
    TimezoneBasisError,
    resolve_instant,
    to_iso_instant,
)
from tools.retrieval.collect.core.http import PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.core.text import clean_text, dedupe_preserving_order

#: Everything that could change lives here, so an API version bump is a
#: one-line fix. v1 (api.openreview.net) offers nothing v2 lacks for this
#: purpose and does not expose `content` on venues anonymously -- use v2 only.
BASE = "https://api2.openreview.net"
GROUPS_URL = f"{BASE}/groups"
INVITATIONS_URL = f"{BASE}/invitations"

#: `ids=` batching is capped by URL length, not item count: 500 ids returned
#: HTTP 414 Request-URI-Too-Large live, 200 worked. Chunk on a character
#: budget rather than a fixed count -- venue ids range from "TMLR" to a
#: fifty-character nested workshop path, and a fixed-count chunk would still
#: 414 on a batch of long ones.
URL_BUDGET = 6000

#: A bare local date/time plus an explicit "UTC-0" suffix, as `content.date`
#: writes it: "Submission Deadline: Jul 29 2026 11:59AM UTC-0". Anchored to
#: this one shape on purpose -- 470 non-TBD "Submission Deadline:" segments
#: probed live all matched it with no exceptions, but a free-text field can
#: change without notice, and a near-miss silently parsed wrong is worse than
#: one left as raw text.
_FREE_TEXT_DEADLINE = re.compile(
    r"Submission Deadline:\s*([A-Za-z]{3} \d{1,2} \d{4} \d{1,2}:\d{2}(?:AM|PM)) (UTC[+-]\d+)"
)

_YEAR_SEGMENT = re.compile(r"^(19|20)\d{2}$")
_VIRTUAL = re.compile(r"\b(virtual|online)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)


class OpenReviewAdapter(BaseConferenceAdapter):
    name = "openreview"
    #: The venue's own configuration record -- program chairs set `title`,
    #: `duedate`, `website` directly. Same standing as ccf-deadlines' curated
    #: YAML, just typed integers instead of hand-transcribed strings.
    venue_native = True
    phase = 2
    license = "CC0-1.0 (metadata) / CC-BY-4.0 (configuration records)"

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        active = client.get(f"{GROUPS_URL}?id=active_venues").json()
        roster = (active or {}).get("groups") or []
        venue_ids = list((roster[0].get("members") if roster else []) or [])
        if limit is not None:
            venue_ids = venue_ids[:limit]

        group_records: list[dict[str, Any]] = []
        for chunk in _chunk_ids(venue_ids):
            payload = client.get(f"{GROUPS_URL}?{urlencode({'ids': ','.join(chunk)})}").json()
            group_records.extend(payload.get("groups") or [])

        # The webfield JS blob is multi-KB of pure noise per venue -- eliding
        # it took a full dump from 10.8 MB to 8.6 MB in recon, and parse()
        # never reads it. Strip before it ever reaches storage.
        for group in group_records:
            group.pop("web", None)

        submission_ids = [
            sid
            for group in group_records
            if (sid := ((group.get("content") or {}).get("submission_id") or {}).get("value"))
        ]

        invitation_records: list[dict[str, Any]] = []
        for chunk in _chunk_ids(submission_ids):
            # expired=true is MANDATORY. Without it, an already-expired
            # invitation 400s (InvitationExpiredError) instead of returning
            # data, and PoliteClient never retries a 400 -- it raises
            # FetchError immediately and would kill the whole fetch on the
            # first venue whose deadline had already passed.
            params = urlencode({"ids": ",".join(chunk), "expired": "true"})
            payload = client.get(f"{INVITATIONS_URL}?{params}").json()
            invitation_records.extend(payload.get("invitations") or [])

        invitation_by_id = {inv["id"]: inv for inv in invitation_records if inv.get("id")}

        # Pair every group with its invitation now, while both are on hand.
        # `ids=` answers HTTP 200 with an empty list for anything not
        # readable -- not a 403 -- so `invitation_by_id.get(sid)` misses
        # exactly as silently as the wire does. Recording the miss as a
        # paired None (never dropping the venue outright) is what lets
        # parse() see the gap offline instead of just under-reporting.
        records: list[dict[str, Any]] = []
        for group in group_records:
            sid = ((group.get("content") or {}).get("submission_id") or {}).get("value")
            records.append(
                {"group": group, "invitation": invitation_by_id.get(sid) if sid else None}
            )

        return self.bundle(
            self.name,
            new_run_id(),
            utc_now(),
            records,
            base_url=BASE,
            # asked-for vs returned, per stage: the counts that make gotcha
            # #2 (silent empty-list misses) visible offline without a re-fetch.
            venues_requested=len(venue_ids),
            groups_returned=len(group_records),
            submissions_requested=len(submission_ids),
            invitations_returned=len(invitation_records),
        )

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        series_out: list[ConferenceSeries] = []
        instances_out: list[ConferenceInstance] = []

        for record in bundle.records:
            if not isinstance(record, dict):
                continue
            parsed = self._parse_record(record)
            if parsed is None:
                continue
            series, instance = parsed
            series_out.append(series)
            instances_out.append(instance)

        return series_out, instances_out

    # -- internals ----------------------------------------------------------

    def _parse_record(
        self, record: dict[str, Any]
    ) -> tuple[ConferenceSeries, ConferenceInstance] | None:
        group = record.get("group") or {}
        invitation = record.get("invitation")

        group_id = clean_text(group.get("id"))
        content = group.get("content")
        # Legacy groups (782/4566 across the full historical roster; 0/1075
        # of the *active* ones probed live) carry no `content` key and no
        # `domain` at all -- their metadata lives only in the `web` webfield
        # JS blob, which this adapter does not scrape. Checking both signals
        # and skipping early is what keeps a legacy-shaped record from being
        # silently half-parsed rather than cleanly absent.
        if not group_id or not group.get("domain") or not isinstance(content, dict):
            return None

        title = clean_text((content.get("title") or {}).get("value"))
        if not title:
            return None

        host = clean_text(group.get("host")) or group_id.split("/")[0]
        acronym = clean_text((content.get("subtitle") or {}).get("value")) or title

        series_key = _series_key(group_id, host)
        deadlines, warnings = _deadlines_for(content, invitation, self.name)
        place_text = clean_text((content.get("location") or {}).get("value"))
        website = clean_text((content.get("website") or {}).get("value"))
        source_url = f"https://openreview.net/group?id={quote(group_id, safe='')}"

        series = ConferenceSeries(
            series_key=series_key,
            acronym=acronym,
            # OpenReview has no venue-level title distinct from the edition's
            # own: `content.title` already carries an edition-specific
            # ordinal ("The 41st AAAI..."). Using it here means full_name
            # drifts year to year exactly as the venue's own name does --
            # accepted as-is rather than invented via ordinal-stripping that
            # would itself need evidence this source doesn't offer.
            full_name=title,
            # No dblp presence for this source; resolve stage tries a
            # name/acronym match instead, same as any `gen:` series key.
            contributing_sources=[self.name],
            license=self.license,
        )

        kind = _record_kind(group_id)
        instance = ConferenceInstance(
            source=self.name,
            source_record_id=group_id,
            series_key=series_key,
            record_kind=kind,
            # A workshop or track always has a parent conference; this adapter
            # just cannot name it, because the venue-id hierarchy is convention
            # rather than schema and stripping a trailing segment links the
            # wrong parent often enough to be dangerous. Saying so is the point
            # of the flag: leaving it False would claim the parent question was
            # settled when it was never asked.
            unresolved_parent=kind in {"workshop", "track"},
            title=title,
            acronym=acronym,
            year_label=_year_from_id(group_id),
            # `start_date` is free text ("Feb 16 2027"), one date, no range,
            # and 1060/1075 coverage. Kept verbatim and never parsed into
            # event_start, same policy as every other free-text date field in
            # this collector: a guessed format is a confidently wrong one.
            event_dates_text=clean_text((content.get("start_date") or {}).get("value")),
            place_text=place_text,
            is_virtual=bool(_VIRTUAL.search(place_text)),
            is_hybrid=bool(_HYBRID.search(place_text)),
            url=website or source_url,
            source_url=source_url,
            # cfp_text is left EMPTY on purpose. group.description is
            # boilerplate identical across 601/1075 active venues ("Set up
            # and customize the peer review process..."), and invitation
            # `instructions` has only 2 distinct values across the 549 that
            # carry it. Populating cfp_text from either would poison dedupe's
            # descriptive-field merge with hundreds of identical strings.
            deadlines=deadlines,
            quality_warnings=dedupe_preserving_order(warnings),
            contributing_sources=[self.name],
            license=self.license,
            raw={"group": group, "invitation": invitation},
        )
        return series, instance


# --- deadlines -------------------------------------------------------------


def _deadlines_for(
    content: dict[str, Any], invitation: dict[str, Any] | None, source_name: str
) -> tuple[list[Deadline], list[str]]:
    warnings: list[str] = []
    submission_id = clean_text((content.get("submission_id") or {}).get("value"))
    full_submission_id = clean_text(
        (content.get("full_submission_invitation_id") or {}).get("value")
    )
    date_text = clean_text((content.get("date") or {}).get("value"))

    if not submission_id:
        # 2/1075 active venues have no content.submission_id at all --
        # fetch() never had an id to look up, so there is nothing to join.
        warnings.append("no content.submission_id on this venue; deadline is not obtainable")
        return [], warnings

    if invitation is None:
        # Gotcha #2, and the worst trap in this source: an unreadable id
        # returns HTTP 200 with an empty list, not a 403 or 404. 46/1073
        # active venues silently yield no deadline this way and nothing about
        # the response looks unhealthy, so it is said here explicitly.
        warnings.append(
            f"submission invitation {submission_id!r} was requested but the API "
            "returned no result (HTTP 200, empty) -- not publicly readable"
        )
        return [], warnings

    due_ms = invitation.get("duedate")
    if due_ms is None:
        # 21/1006 readable invitations carry only `cdate` (submissions open)
        # with no `duedate` -- a round that has not been dated yet, not a
        # parse failure.
        warnings.append(f"invitation {submission_id!r} has cdate but no duedate yet")
        return [], warnings

    # `expdate` (a +30 minute grace period on 1002/1006 invitations) and
    # `tcdate`/`tmdate`/`mdate` (record-audit timestamps) sit right next to
    # `duedate` in the payload and are easy to grab by mistake. Neither is a
    # venue date a human cares about; neither is read anywhere here.
    instant = _epoch_ms_instant(due_ms)
    kind: DeadlineType = "submission"
    deadlines: list[Deadline] = []

    if full_submission_id:
        # Multi-round trap (198/1075 active venues): the Submission
        # invitation's `duedate` is the *abstract* deadline here, not the
        # paper deadline -- verified against AAAI 2027's own prose, where
        # duedate decodes to the "Abstract Registration" instant exactly. The
        # real deadline lives on Full_Submission, which returned
        # {"invitations": []} at HTTP 200 for all 198 probed live, never
        # publicly readable. Presenting this as kind="submission" would be a
        # confidently wrong paper deadline, so it is relabelled and flagged.
        kind = "abstract"
        warnings.append(
            f"{submission_id!r} is multi-round: duedate is the abstract-registration "
            f"deadline, not the paper deadline on {full_submission_id!r}, which "
            "OpenReview does not expose anonymously"
        )

    deadlines.append(
        Deadline(
            kind=kind,
            raw=str(int(due_ms)),
            instant=instant,
            # Epoch milliseconds, UTC, cross-checked live against the venue's
            # own prose and matching exactly -- the only source in this
            # collector with no timezone ambiguity, so "UTC" is a real claim,
            # never "inferred:...".
            basis="UTC",
            source=source_name,
        )
    )

    if kind == "abstract":
        fallback = _fallback_submission_deadline(date_text)
        if fallback is None:
            # Only 73/198 multi-round venues carry a usable fallback; for the
            # other 125 the real paper deadline is simply not obtainable
            # anonymously, and that absence must be visible, not silent.
            warnings.append(
                f"{submission_id!r}: no usable content.date fallback for the paper "
                "deadline -- only 73/198 multi-round venues have one"
            )
        else:
            raw_text, value, basis_label = fallback
            deadlines.append(
                Deadline(
                    kind="submission",
                    raw=raw_text,
                    instant=_instant(value, basis_label),
                    basis=basis_label,
                    round_label=(
                        "paper deadline, from content.date free text "
                        "(Full_Submission is not publicly readable)"
                    ),
                    source=source_name,
                )
            )

    return deadlines, warnings


def _fallback_submission_deadline(date_text: str) -> tuple[str, str, str] | None:
    """The only anonymous route to a real paper deadline on a multi-round
    venue. Matched strictly against the one shape recon verified live with no
    exceptions; free text that does not fit (including the common "TBD") is
    left unparsed rather than guessed at.
    """
    match = _FREE_TEXT_DEADLINE.search(date_text)
    if not match:
        return None
    raw_local, offset = match.group(1), match.group(2)
    try:
        parsed = datetime.strptime(raw_local, "%b %d %Y %I:%M%p")
    except ValueError:
        return None
    value = parsed.strftime("%Y-%m-%d %H:%M:%S")
    return f"{raw_local} {offset}", value, offset


def _epoch_ms_instant(value: Any) -> str | None:
    """`cdate`/`duedate` are already an absolute UTC instant -- unlike every
    other source in this collector, there is no local-time-plus-basis step at
    all.
    """
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return None
    return to_iso_instant(datetime.fromtimestamp(ms / 1000, tz=UTC))


def _instant(value: str, basis: str) -> str | None:
    try:
        return to_iso_instant(resolve_instant(value, basis))
    except TimezoneBasisError:
        return None


# --- identity ----------------------------------------------------------------


def _series_key(group_id: str, host: str) -> str:
    """A stable identity across years without merging unrelated venues.

    `host` alone collapses distinct venues: this adapter's own fixture has
    ACM.org hosting BCB, CHASE, CHI and SIGIR workshops, each a separate
    recurring venue. Stripping only the year segment(s) off the hierarchical
    id keeps everything OpenReview actually uses to tell venues apart (host,
    short name, Conference/Workshop/name) and drops only what changes every
    edition.
    """
    segments = [segment for segment in group_id.split("/") if not _YEAR_SEGMENT.match(segment)]
    return "gen:openreview:" + "/".join(segments) if segments else f"gen:openreview:{host}"


def _year_from_id(group_id: str) -> str:
    for segment in group_id.split("/"):
        if _YEAR_SEGMENT.match(segment):
            return segment
    return ""


def _record_kind(group_id: str) -> RecordKind:
    """Path-segment convention, not schema (no typed field distinguishes
    conference/workshop/track anywhere in this API) -- confirm before relying
    on it further.
    """
    lowered = group_id.lower()
    if "/workshop" in lowered:
        return "workshop"
    if "track" in lowered:
        return "track"
    return "conference"


# --- HTTP --------------------------------------------------------------------


def _chunk_ids(ids: Sequence[str], *, budget: int = URL_BUDGET) -> list[list[str]]:
    """Group ids into batches that fit the URL-length budget.

    500 ids in one `/groups?ids=` call returned HTTP 414 Request-URI-Too-Large
    live; 200 worked. The ceiling is characters, not item count, so chunking
    on encoded length (rather than a fixed batch size) is what keeps this
    correct even though ids range from four characters ("TMLR") to a
    fifty-character nested workshop path.
    """
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 200  # headroom for the base URL and the other query params
    for id_ in ids:
        piece_len = len(quote(id_, safe="")) + 3  # +3 for the encoded comma "%2C"
        if current and current_len + piece_len > budget:
            chunks.append(current)
            current = []
            current_len = 200
        current.append(id_)
        current_len += piece_len
    if current:
        chunks.append(current)
    return chunks
