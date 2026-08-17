"""Recover missing fields from the venue's own website.

Measured on the stored corpus: 1,080 of 2,234 conference records carry no usable
description, and 1,073 of those come from OpenReview. That is not an extraction
bug. OpenReview's ``group.content`` is peer-review plumbing — reviewer roles,
invitation ids, email templates — and contains no abstract, scope or keyword
field at all. The same records are the ones with no topics, and a share of the
missing deadlines are missing for the identical reason. What every one of them
*does* carry is the venue's own website URL, already stored.

So the information exists and is one hop away. This module goes and gets it:

    detect   which record is missing which field          pure
    fetch    the site it points at, honouring robots.txt  network
    reduce   the page to its call-for-papers text         pure
    verify   every factual claim against the page         pure
    apply    the accepted fields onto the record          pure

**The model call used to be a sixth step here — ``generate()``, a single call
through a vendored client — and it is gone.** Per plan decision D9, every
record's description is now produced by a *universal* structured-extraction
stage that runs in Mycelium and drives ``apps.core.llm`` (plan Phase 8), not
by a conferences-only, gap-gated pass living inside the vendored collector.
That stage calls a model with its own schema and its own prompt; what it
reuses from here is everything below, unchanged:

**The division of labour is the design.** A model locates and summarizes;
deterministic code parses and checks. A date the model reports is accepted only
if its verbatim string is genuinely on the page, and the conversion to an instant
is then done by ``timezones.resolve_instant`` rather than taken from the model —
so a plausible-looking hallucinated timestamp has no path into the store.
``verify()`` takes the model's reply as a plain ``dict`` and never calls
anything itself, which is what makes it reusable by a caller with a
completely different model client and a completely different prompt.

Everything fetched is cached against the page's content hash, so a second run
makes no requests, and the pipeline stays replayable offline.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from apps.scraper.collect.conferences.record import ConferenceInstance, ConferenceSeries
from apps.scraper.collect.core.rawstore import utc_now
from apps.scraper.collect.core.text import clean_text, html_to_text

# --- what counts as a gap ------------------------------------------------
#
# These are the single definition of "missing", used both by the pipeline's
# validation stage and by this module's detection, so the two can never drift
# into disagreeing about what needs fixing.

#: Below this a description names the thing again instead of describing it.
MIN_DESCRIPTION_CHARS = 80

#: A venue name has to say more than its acronym to count as descriptive.
MIN_VENUE_NAME_CHARS = 20

_PLACEHOLDER = {"", "-", "--", "n/a", "na", "none", "null", "tbd", "tba", "untitled", "unknown"}


def text_ok(value: str, minimum: int = 1) -> bool:
    value = (value or "").strip()
    if value.lower() in _PLACEHOLDER:
        return False
    return len(value) >= minimum


def describes_something(value: str) -> bool:
    """Long enough to be a description, and not a pointer somewhere else."""
    value = (value or "").strip()
    if not text_ok(value, MIN_DESCRIPTION_CHARS):
        return False
    head = value[:40].lower()
    return not head.startswith(("see ", "refer to ", "click here", "n/a", "none", "tbd"))


def has_description(record: ConferenceInstance, series_by_key: dict[str, Any]) -> bool:
    """CFP prose, a generated summary, or a spelled-out venue name plus a topic.

    The last fallback is not a loophole. Two sources carry no call text at all and
    are right not to: ccf-deadlines publishes a deadline table, and OpenReview's
    group description is boilerplate identical across 601 of 1,075 venues, which
    that adapter deliberately refuses to store.
    """
    if describes_something(record.cfp_text):
        return True
    if describes_something(record.generated_summary):
        return True
    series = series_by_key.get(record.series_key)
    name = (getattr(series, "full_name", "") or record.title or "").strip()
    return len(name) >= MIN_VENUE_NAME_CHARS and bool(record.topics)


def has_usable_deadline(record: ConferenceInstance) -> bool:
    """At least one submission deadline resolved to an instant with a basis.

    The basis is the load-bearing half. "March 1" with no timezone is up to a day
    wrong in either direction, which for a submission deadline is the difference
    between submitting and not.
    """
    return any(d.is_submission and d.instant and d.basis for d in record.deadlines)


def has_topics(record: ConferenceInstance) -> bool:
    return bool(record.topics)


#: The three fields worth a network round trip. Ordered by how much a reader
#: loses without them, which is also the order the prompt asks for them in.
GAPS = ("description", "deadlines", "topics")


def gaps_for(
    record: ConferenceInstance, series_by_key: dict[str, Any]
) -> tuple[str, ...]:
    """Which of the three this record is missing. Empty means leave it alone."""
    missing = []
    if not has_description(record, series_by_key):
        missing.append("description")
    if not has_usable_deadline(record):
        missing.append("deadlines")
    if not has_topics(record):
        missing.append("topics")
    return tuple(missing)


# --- the unit of work ----------------------------------------------------


@dataclass
class EnrichmentTask:
    """One record, one URL, and the list of things we hope the page will supply."""

    instance_key: str
    url: str
    acronym: str
    title: str
    year_label: str
    gaps: tuple[str, ...]
    active: bool = True

    @property
    def is_fetchable(self) -> bool:
        """A URL, not a promise of one, and not two of them in a trench coat.

        OpenReview publishes whatever the organizers typed into a text box. One
        record's website field is the literal string ``TBD``; another holds
        ``glee-competition.com; https://...``, two URLs in one field, which
        reaches urllib as a control character and raises ``InvalidURL`` from
        inside the worker. Screening here keeps every one of those out of the
        fetch path instead of turning each into a crash to be caught.

        A bare hostname is fetchable, though, and organizers type those
        constantly: ``jmlr.org/tmlr``, ``slads.scichina.com``. Requiring a
        scheme reported 17 conferences as having "no fetchable URL" while
        holding a working address for each, so none of them was ever described.
        :attr:`fetch_url` supplies the scheme; this only decides whether there
        is an address at all. ``TBD``, ``internal (private)`` and an email
        address are still correctly refused — none has a dotted host.
        """
        return bool(self.fetch_url)

    @property
    def fetch_url(self) -> str:
        """The address to actually request, or "" if there isn't one.

        Mirrors ``mapping._normalize_url``, which already does this for the
        link a reader clicks. The two had drifted: the website shown on a card
        was reachable while the crawler considered the same record unfetchable.
        """
        url = (self.url or "").strip()
        if not url or any(c.isspace() or ord(c) < 32 for c in url):
            return ""
        if url.lower().startswith(("http://", "https://")):
            return url
        # Anything else must look like a host before we prepend a scheme:
        # a dotted label, no "@" (an email), and a plausible TLD.
        host = url.split("/", 1)[0]
        if "@" in url or "." not in host:
            return ""
        if not _BARE_HOST_RE.match(host):
            return ""
        return f"https://{url}"


@dataclass
class EnrichmentRecord:
    """What was learned about one record, verified fields and rejections alike."""

    instance_key: str
    url: str = ""
    status: str = "pending"
    detail: str = ""
    page_hash: str = ""
    fetched_at: str = ""
    generated_at: str = ""
    model: str = ""
    summary: str = ""
    purpose: str = ""
    audience: str = ""
    topics: list[str] = field(default_factory=list)
    submission_types: list[str] = field(default_factory=list)
    #: Verified deadlines only, in the shape ``Deadline.from_json`` accepts.
    deadlines: list[dict[str, Any]] = field(default_factory=list)
    #: What was thrown out and why. Counted and reported, never silently dropped.
    rejected: list[dict[str, str]] = field(default_factory=list)
    #: The model's verbatim reply, so any later dispute is settleable.
    raw_response: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "ok"

    def to_row(self) -> dict[str, Any]:
        return {
            "instance_key": self.instance_key,
            "url": self.url,
            "status": self.status,
            "detail": self.detail,
            "page_hash": self.page_hash,
            "fetched_at": self.fetched_at,
            "generated_at": self.generated_at,
            "model": self.model,
            "summary": self.summary,
            "purpose": self.purpose,
            "audience": self.audience,
            "topics": json.dumps(self.topics, ensure_ascii=False),
            "submission_types": json.dumps(self.submission_types, ensure_ascii=False),
            "deadlines": json.dumps(self.deadlines, ensure_ascii=False),
            "rejected": json.dumps(self.rejected, ensure_ascii=False),
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> EnrichmentRecord:
        return cls(
            instance_key=row["instance_key"],
            url=row["url"] or "",
            status=row["status"] or "pending",
            detail=row["detail"] or "",
            page_hash=row["page_hash"] or "",
            fetched_at=row["fetched_at"] or "",
            generated_at=row["generated_at"] or "",
            model=row["model"] or "",
            summary=row["summary"] or "",
            purpose=row["purpose"] or "",
            audience=row["audience"] or "",
            topics=json.loads(row["topics"] or "[]"),
            submission_types=json.loads(row["submission_types"] or "[]"),
            deadlines=json.loads(row["deadlines"] or "[]"),
            rejected=json.loads(row["rejected"] or "[]"),
            raw_response=row["raw_response"] or "",
        )


#: Verdicts that are about *us or the moment*, not about the page. These are
#: retried on the next run; everything else is a settled answer and is not.
#:
#: The distinction is load-bearing. A run at too much concurrency once wrote 321
#: ``model_failed`` rows in a single sitting, and treating those as answers would
#: have permanently excluded 321 records from ever being enriched again — a
#: transient server overload silently becoming a permanent data gap.
RETRYABLE_STATUSES = frozenset({"pending", "model_failed", "fetch_failed", "thin_page"})

STATUSES = (
    "ok",              # generated, verified, applied
    "no_url",          # the record points nowhere fetchable
    "robots_denied",   # the host's robots.txt forbids it
    "fetch_failed",    # dead, timed out, or refused
    "thin_page",       # fetched, but nothing worth reading came out
    "not_the_venue",   # the page does not mention this conference
    "model_failed",    # the server was unreachable or returned nothing usable
    "rejected",        # generated, but nothing survived verification
)


def page_hash(text: str) -> str:
    """Content hash of the reduced page. The cache key for everything downstream."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# --- fetch and reduce ----------------------------------------------------
#
# A conference homepage is mostly navigation, sponsor logos and a countdown
# widget. Two reductions matter before any of it reaches the model: cut the
# chrome, and find the part that is actually the call for papers — which is very
# often not on the homepage at all but one click away behind a link that says so.


#: Link text that leads to the page actually worth reading. Ordered by how
#: reliably each lands on dates rather than prose.
CFP_LINK_TEXT = re.compile(
    r"(important\s+dates|key\s+dates|dates\s+(and|&amp;|&)\s+deadlines|call\s+for\s+papers"
    r"|submission\s+guidelines|calls?\b|cfp\b|submit\b|authors?\b)",
    re.IGNORECASE,
)
_HREF = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")

#: Markers for the region of a page that carries submission information. Used to
#: centre the excerpt when a page is longer than the model should be given.
CFP_MARKERS = re.compile(
    r"(important\s+dates|key\s+dates|submission\s+deadline|paper\s+submission"
    r"|call\s+for\s+papers|abstract\s+deadline|camera[- ]ready|deadlines?\b)",
    re.IGNORECASE,
)

#: How much page text the model is given. Enough for a full call for papers,
#: bounded so a wiki-sized page cannot blow the context window.
#: A dotted hostname with a plausible TLD, for deciding whether a bare
#: (scheme-less) website field is an address or a note to self. Rejects
#: "TBD" and "internal (private)" because neither has a dotted label.
_BARE_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$")

MAX_PAGE_CHARS = 12000

#: Under this, the fetch found navigation and nothing else.
MIN_PAGE_CHARS = 400


#: Wrapper elements that are chrome on essentially every site. Removed whole,
#: because their text is the same on every page of a site and drowns the part
#: that is not — the 3DV homepage is 60% menu by character count.
_CHROME = re.compile(
    r"<(nav|header|footer|aside)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: A date as a human writes one. Used to tell "this page states its deadlines"
#: from "this page has a menu item called Important Dates" — which is the
#: difference between fetching one page and fetching the one that has the answer.
_DATE_SHAPE = re.compile(
    r"(\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+20\d{2}\b"
    r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b)",
    re.IGNORECASE,
)


def strip_chrome(html_body: str) -> str:
    """Drop comments and site furniture before any text is extracted."""
    return _CHROME.sub(" ", _COMMENT.sub(" ", html_body))


def states_dates(text: str) -> bool:
    """True when a deadline word and a real date appear close together.

    Searching for the *word* alone is what a first attempt does and it is wrong:
    almost every conference site has a nav item reading "Important Dates", so the
    word matches on pages that contain no date at all — and the crawler then
    concludes it already has what it came for.
    """
    for marker in CFP_MARKERS.finditer(text):
        window = text[marker.start() : marker.start() + 400]
        if _DATE_SHAPE.search(window):
            return True
    return False


def page_text(html_body: str, *, max_chars: int = MAX_PAGE_CHARS) -> str:
    """Reduce a page to the text worth reading, centred on the submission section.

    Truncating from the top would be the obvious thing and is the wrong thing:
    the call for papers is almost never at the top, so a naive head-slice returns
    a sponsor list and drops every date on the page.
    """
    text = html_to_text(strip_chrome(html_body))
    if len(text) <= max_chars:
        return text

    marker = next(
        (m for m in CFP_MARKERS.finditer(text) if _DATE_SHAPE.search(text[m.start(): m.start() + 400])),
        None,
    ) or CFP_MARKERS.search(text)
    if marker is None:
        return text[:max_chars]
    # Keep some run-up so the excerpt starts at a heading rather than mid-sentence.
    start = max(0, marker.start() - max_chars // 4)
    return text[start : start + max_chars]


def _encode_url(url: str) -> str:
    """Make a URL scraped out of a page safe to hand to http.client.

    Venue sites write hrefs by hand, so spaces and stray control characters
    reach us verbatim. `quote` the path and query (leaving already-encoded
    sequences alone via `safe`) rather than rejecting the link: the page is
    pointing at something real, it is simply written the way a person types.
    Returns "" for anything still unusable.
    """
    from urllib.parse import quote, urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        url = "".join(c for c in url if ord(c) >= 32 and ord(c) != 127)
        try:
            parts = urlsplit(url)
        except ValueError:
            return ""
    if not parts.netloc:
        return ""
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe="/%:@&=+$,~"),
        quote(parts.query, safe="/%:@&=+$,~?"),
        quote(parts.fragment, safe="/%:@&=+$,~?"),
    ))


def cfp_links(html_body: str, base_url: str) -> list[str]:
    """Same-site links whose text promises dates or a call for papers."""
    from urllib.parse import urljoin, urlparse

    base_host = urlparse(base_url).netloc
    found: list[str] = []
    for href, label in _HREF.findall(html_body):
        label_text = _TAGS.sub(" ", label)
        if not CFP_LINK_TEXT.search(label_text):
            continue
        target = urljoin(base_url, href.strip())
        if not target.startswith(("http://", "https://")):
            continue
        # Percent-encode what the page actually wrote. A real href on a live
        # venue site is `/tiki-index.php?page=Call for Sponsors` -- spaces and
        # all -- and handing that to http.client raises InvalidURL from inside
        # the worker, which is not a FetchError and so killed an entire
        # extraction run rather than skipping one link.
        target = _encode_url(target)
        if not target:
            continue
        if urlparse(target).netloc != base_host:
            continue  # off-site: a publisher or a social link, not the CFP
        if target.rstrip("/") == base_url.rstrip("/"):
            continue
        if target not in found:
            found.append(target)
    return found


def fetch_page(
    client: Any, gate: Any, task: EnrichmentTask, *, follow_links: bool = True
) -> tuple[EnrichmentRecord, str]:
    """One record's page, plus at most one CFP subpage. Honours robots.txt.

    The subpage is not a nicety. Homepages routinely carry a countdown widget and
    a "Submit" button and no dates at all, while the page one click behind
    "Important Dates" carries every round.
    """
    from apps.scraper.collect.core.http import FetchError

    # `fetch_url`, not `url`: organizers type bare hostnames, and both the
    # robots check and the request itself need the scheme the raw field lacks.
    target = task.fetch_url
    record = EnrichmentRecord(instance_key=task.instance_key, url=target)

    permitted, reason = gate.allowed(target)
    if not permitted:
        record.status, record.detail = "robots_denied", reason
        return record, ""

    try:
        response = client.get(target, min_bytes=0)
    except FetchError as exc:
        record.status, record.detail = "fetch_failed", exc.reason
        return record, ""

    body = response.text()
    record.fetched_at = utc_now()
    text = page_text(body)

    # Only go looking for a second page when the first one is missing what we
    # came for. A homepage that already lists its dates costs one request.
    wants_dates = "deadlines" in task.gaps
    if follow_links and wants_dates and not states_dates(text):
        # `target`, not `task.url`: joining a relative href onto a
        # scheme-less base produces a nonsense address.
        for link in cfp_links(body, target)[:1]:
            allowed_link, _ = gate.allowed(link)
            if not allowed_link:
                continue
            try:
                extra = client.get(link, min_bytes=0)
            # Broad on purpose. This is an optional second page: no failure
            # reading it is worth losing the first page we already have, let
            # alone the rest of the batch.
            except Exception:  # noqa: BLE001
                continue
            text = f"{text}\n\n--- {link} ---\n\n{page_text(extra.text())}"
            record.detail = f"followed {link}"
            break

    if len(text.strip()) < MIN_PAGE_CHARS:
        record.status = "thin_page"
        record.detail = f"{len(text.strip())} chars of text after reduction"
        return record, ""

    record.page_hash = page_hash(text)
    record.status = "fetched"
    return record, text


# --- prompt shaping and reply parsing (no model call lives here) ---------
#
# This used to be "generation": the same section also held a ``generate()``
# function that took an LLM client and actually placed the call. That function
# is gone — Mycelium's own structured-extraction stage (plan D9, Phase 8) is
# the one place that calls a model now, through ``apps.core.llm``, with its own
# prompt and its own JSON schema. What is left here is pure and reusable by
# that stage if it wants it: ``build_prompt`` shapes a request the same way
# this module always asked for it, and ``extract_json`` pulls a JSON object out
# of a reply that may be fenced or prefaced, regardless of which schema it
# encodes.
#
# The original design's key property survives the split intact: everything
# factual is asked for in a form that can be checked afterwards. The critical
# instruction is that ``date_text`` must be copied verbatim: it turns "did the
# model invent this date?" from an unanswerable question into a string search.
# The model locates; ``verify`` and ``resolve_instant`` (below) decide.

GENERATION_SYSTEM = """You extract structured facts about academic conferences from their own \
websites, for a research-opportunity database.

Return ONE JSON object and nothing else. No prose, no markdown fences.

{
  "is_this_venue": true,
  "summary": "",
  "purpose": "",
  "audience": "",
  "topics": [],
  "submission_types": [],
  "deadlines": [],
  "location": ""
}

Rules:
- "is_this_venue": false if the page is not about the conference named in the \
request (a parked domain, a different year, an unrelated site). When false, leave \
everything else empty. Do not guess.
- "summary": 2-4 sentences describing what the conference is about and what kind \
of work it publishes. Write it for a researcher deciding whether to submit. \
Describe the field and the scope. Do not copy marketing language, do not mention \
registration fees, sponsors, keynote speakers, or the host city's attractions.
- "purpose": one sentence on what the venue exists to advance.
- "audience": one sentence on who should submit.
- "topics": 5-12 short subject terms, lowercase, each 1-4 words. Research areas \
only - not "call for papers", not city names, not "conference".
- "submission_types": e.g. ["full paper", "short paper", "poster"]. Empty if unstated.
- "deadlines": one object per dated submission milestone:
    {"kind": "...", "round_label": "", "date_text": "...", "timezone_text": ""}
  "kind" must be one of: abstract, submission, supplementary, rebuttal_open, \
rebuttal_close, notification, camera_ready, registration.
  "date_text" MUST be copied character-for-character from the page. If you cannot \
copy it exactly, omit the entry. Never reformat, never normalise, never infer a \
date that is not written on the page.
  "timezone_text" is the timezone as the page writes it ("AoE", "11:00 am Pacific \
Time (PDT)", "23:59 UTC"), copied verbatim, or "" if the page does not say.
- Anything the page does not state: leave empty. An empty field is correct; an \
invented one is not."""


def build_prompt(task: EnrichmentTask, text: str) -> str:
    """Ask only for what is missing, and name the venue so identity can be judged."""
    wanted = {
        "description": "a summary, purpose and audience",
        "deadlines": "every dated submission milestone",
        "topics": "the subject topics",
    }
    asks = [wanted[gap] for gap in task.gaps if gap in wanted]
    return (
        f"Conference: {task.title or task.acronym}\n"
        f"Acronym: {task.acronym or '(none given)'}\n"
        f"Edition: {task.year_label or '(unknown)'}\n"
        f"Page URL: {task.url}\n"
        f"We are missing: {', '.join(asks) or 'anything the page states'}.\n\n"
        f"--- PAGE TEXT ---\n{text}\n--- END PAGE TEXT ---"
    )


def extract_json(reply: str) -> dict[str, Any]:
    """Pull the object out of a reply that may be fenced or prefaced.

    Instructing a model to emit bare JSON works most of the time, and "most" is
    not a parsing strategy.
    """
    body = reply.strip()
    if "```" in body:
        chunks = body.split("```")
        body = next(
            (c[4:] if c.lower().startswith("json") else c for c in chunks[1::2]), body
        )
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(body[start : end + 1])


# --- verification --------------------------------------------------------
#
# Trust, then verify. Everything above this line came from a language model and
# nothing below it takes the model's word for anything checkable.
#
# Three independent checks, in increasing order of how much they matter:
#
#   identity  is this page even about this conference?
#   summary   does the prose overlap the page, or was it written from nowhere?
#   dates     is the date string literally on the page — and if so, *we* parse it
#
# The last is the important one. The model is only ever asked to *locate* a date;
# converting it to an instant is done by ``resolve_instant``, the same
# deterministic code every adapter uses. A hallucinated timestamp therefore has
# no path into the store even if the model states one confidently.

#: Words too common to carry evidence of overlap.
_STOPWORDS = frozenset(
    """the and for with that this from will are was were has have been its their
    they them then than there here what when where which who whom whose about
    into over under between during through such other more most some any all
    both each few many much very can could would should may might must shall
    conference workshop symposium papers paper submission submissions research
    international""".split()
)

_WORD = re.compile(r"[a-z][a-z-]{3,}")

#: Below this share of its own content words appearing on the page, a summary is
#: not a summary of that page.
MIN_SUMMARY_OVERLAP = 0.45

#: Topic strings that are not subjects.
_NOT_A_TOPIC = re.compile(
    r"^(call for papers?|conference|workshop|symposium|submissions?|deadlines?"
    r"|important dates|registration|proceedings|papers?)$",
    re.IGNORECASE,
)

#: A date outside this window is a parse artifact, not a deadline.
MIN_YEAR, MAX_YEAR = 2000, 2035


#: "May 25th, 2026" — how a person writes a date and an API never does, so the
#: shared date parser has never needed to handle it.
_ORDINAL_SUFFIX = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
#: A clock time trailing the date: "May 23, 2026 23:59 PT".
_TRAILING_TIME = re.compile(r"\s+\d{1,2}:\d{2}\b.*$")


def normalize_date_text(value: str) -> str:
    """Formatting only — never interpretation.

    Both transformations are lossless with respect to *which day is meant*, which
    is the line this must not cross. Measured on a trial: 9 of 19 unparseable
    dates were one of these two shapes. The rest stay refused and should — a
    month with no day, "the week of March 25th", and rows carrying an original
    and an extended date at once are all genuinely ambiguous, and guessing at
    them would put a wrong deadline in front of a reader.
    """
    return _TRAILING_TIME.sub("", _ORDINAL_SUFFIX.sub(r"\1", value)).strip()


def _normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if w not in _STOPWORDS}


def overlap_ratio(summary: str, page: str) -> float:
    """Share of the summary's content words that actually occur on the page."""
    words = _content_words(summary)
    if not words:
        return 0.0
    page_words = _content_words(page)
    return len(words & page_words) / len(words)


def venue_matches(task: EnrichmentTask, page: str) -> bool:
    """Is this page about the conference we asked about?

    Checked independently of the model's own ``is_this_venue`` answer, because a
    parked domain or a rehomed URL is exactly the situation where the model has
    the least to go on and the most reason to be agreeable.
    """
    haystack = _normalize_for_search(page)
    acronym = task.acronym.strip().casefold()
    if len(acronym) >= 3 and acronym in haystack:
        return True
    title_words = {w for w in _content_words(task.title) if len(w) > 4}
    if not title_words:
        return bool(acronym) and acronym in haystack
    hits = sum(1 for word in title_words if word in haystack)
    return hits / len(title_words) >= 0.5


def basis_from(timezone_text: str) -> tuple[str, str]:
    """(basis, time-of-day) read out of the page's own timezone wording.

    Returns an ``inferred:`` basis when the page states no zone. Inferring is
    allowed; inferring *silently* is not, which is why the prefix is part of the
    stored value and every downstream comparison keys on it.
    """
    text = (timezone_text or "").strip()
    if not text:
        return "inferred:unstated", "23:59:59"

    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
    hour, minute = 23, 59
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = (time_match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            hour, minute = 23, 59
    clock = f"{hour:02d}:{minute:02d}:00" if time_match else "23:59:59"

    upper = text.upper()
    if "AOE" in upper or "ANYWHERE ON EARTH" in upper:
        return "AoE", clock
    offset = re.search(r"UTC\s*([+-])\s*(\d{1,2})", upper)
    if offset:
        return f"UTC{offset.group(1)}{int(offset.group(2))}", clock
    for token in ("PDT", "PST", "PT", "EDT", "EST", "ET", "CEST", "CET", "JST"):
        if re.search(rf"\b{token}\b", upper):
            return token, clock
    if re.search(r"\b(UTC|GMT)\b", upper):
        return "UTC+0", clock
    if "PACIFIC" in upper:
        return "PT", clock
    if "EASTERN" in upper:
        return "ET", clock
    return "inferred:unstated", clock


def verify(
    task: EnrichmentTask, payload: dict[str, Any], page: str, record: EnrichmentRecord
) -> EnrichmentRecord:
    """Accept only what the page supports. Everything rejected is recorded."""
    from apps.scraper.collect.conferences.record import DEADLINE_TYPES
    from apps.scraper.collect.conferences.timezones import (
        TimezoneBasisError,
        resolve_instant,
        to_iso_instant,
    )
    from apps.scraper.collect.core.text import to_iso_date

    record.raw_response = str(payload.get("_raw", ""))[:20000]
    record.model = str(payload.get("_model", ""))
    record.generated_at = utc_now()

    if payload.get("is_this_venue") is False or not venue_matches(task, page):
        record.status = "not_the_venue"
        record.detail = "the page does not identify itself as this conference"
        return record

    haystack = _normalize_for_search(page)

    # -- prose ------------------------------------------------------------
    #
    # Summary, purpose and audience are checked together and accepted or refused
    # together, because they are one generation. Checking only the summary is
    # what a first attempt does, and it produced exactly the failure it was meant
    # to catch: ACL 2027's site is a placeholder, the summary was refused at 20%
    # overlap for being written from the model's priors rather than the page —
    # and the purpose and audience sentences, written from those same priors in
    # the same breath, sailed through unchecked.
    summary = clean_text(payload.get("summary"))
    purpose = clean_text(payload.get("purpose"))
    audience = clean_text(payload.get("audience"))
    prose = " ".join(part for part in (summary, purpose, audience) if part)
    if prose:
        ratio = overlap_ratio(prose, page)
        if ratio < MIN_SUMMARY_OVERLAP:
            record.rejected.append(
                {"field": "prose", "value": prose[:120],
                 "why": f"only {ratio:.0%} of its content words are on the page"}
            )
        else:
            record.summary, record.purpose, record.audience = summary, purpose, audience
            record.detail = f"prose overlap {ratio:.0%}"

    # -- topics -----------------------------------------------------------
    page_words = _content_words(page)
    for topic in payload.get("topics") or []:
        value = clean_text(topic).lower()
        if not value or len(value) > 40 or len(value.split()) > 4 or _NOT_A_TOPIC.match(value):
            record.rejected.append({"field": "topic", "value": value[:60], "why": "not a subject term"})
            continue
        # A topic is an abstraction, so it is not required to appear verbatim —
        # but it must be grounded in the page somewhere. A topic sharing no word
        # at all with the text it supposedly summarizes came from the model's
        # priors about the venue's name, not from reading anything.
        words = _content_words(value)
        if words and not (words & page_words):
            record.rejected.append(
                {"field": "topic", "value": value[:60], "why": "no word of it appears on the page"}
            )
            continue
        if value not in record.topics:
            record.topics.append(value)

    record.submission_types = [
        clean_text(t).lower() for t in (payload.get("submission_types") or []) if clean_text(t)
    ][:6]

    # -- deadlines --------------------------------------------------------
    for entry in payload.get("deadlines") or []:
        if not isinstance(entry, dict):
            continue
        raw_text = clean_text(entry.get("date_text"))
        kind = clean_text(entry.get("kind")).lower()
        zone_text = clean_text(entry.get("timezone_text"))

        if kind not in DEADLINE_TYPES:
            record.rejected.append({"field": "deadline", "value": f"{kind} {raw_text}",
                                    "why": f"unknown deadline kind {kind!r}"})
            continue
        if not raw_text:
            continue
        # The check the whole design rests on: the string must be on the page.
        if _normalize_for_search(raw_text) not in haystack:
            record.rejected.append({"field": "deadline", "value": f"{kind} {raw_text}",
                                    "why": "date string is not on the page"})
            continue

        # Verification ran against the verbatim string above; normalization here
        # only affects whether *we* can read it, never whether it was on the page.
        iso_day = to_iso_date(raw_text) or to_iso_date(normalize_date_text(raw_text))
        if iso_day is None:
            record.rejected.append({"field": "deadline", "value": f"{kind} {raw_text}",
                                    "why": "we could not parse the date ourselves"})
            continue
        year = int(iso_day[:4])
        if not (MIN_YEAR <= year <= MAX_YEAR):
            record.rejected.append({"field": "deadline", "value": f"{kind} {raw_text}",
                                    "why": f"implausible year {year}"})
            continue

        basis, clock = basis_from(zone_text)
        # An inferred basis still has to resolve to *something*, and UTC is the
        # only defensible neutral choice. The label keeps saying it was inferred,
        # so the store's basis-downgrade guard and every reader can tell.
        resolving_basis = "UTC+0" if basis.startswith("inferred:") else basis
        try:
            instant = to_iso_instant(resolve_instant(f"{iso_day} {clock}", resolving_basis))
        except (TimezoneBasisError, ValueError) as exc:
            record.rejected.append({"field": "deadline", "value": f"{kind} {raw_text}",
                                    "why": f"basis {basis!r} unusable: {exc}"})
            continue

        record.deadlines.append(
            {
                "kind": kind,
                "raw": f"{raw_text}{f' ({zone_text})' if zone_text else ''}",
                "instant": instant,
                "basis": basis,
                "round_label": clean_text(entry.get("round_label")),
                "source": f"enrichment:{task.url}",
                "is_estimated": True,
                "extension_count": 0,
            }
        )

    accepted = bool(record.summary or record.topics or record.deadlines)
    record.status = "ok" if accepted else "rejected"
    if not accepted:
        record.detail = "nothing survived verification"
    return record


# --- application ---------------------------------------------------------


def compose_summary(record: EnrichmentRecord) -> str:
    """The three prose fields as one block, in the order a reader needs them.

    Kept as prose rather than a dict because this is what gets embedded and what
    gets shown; the structured parts stay in the enrichment table for anyone who
    wants them separately.
    """
    parts = [record.summary, record.purpose, record.audience]
    return "\n\n".join(part for part in parts if part).strip()


def apply_enrichment(
    instances: list[ConferenceInstance], results: dict[str, EnrichmentRecord]
) -> dict[str, int]:
    """Fold verified fields onto the records. Pure; no network, no model.

    Deadlines go through the record's own list rather than a side channel, so the
    store's existing merge — match on ``(kind, round_label)``, update in place,
    count extensions — applies to them unchanged.
    """
    from apps.scraper.collect.conferences.record import Deadline

    applied = {"summaries": 0, "topics": 0, "deadlines": 0, "records": 0}
    for record in instances:
        result = results.get(record.instance_key)
        if result is None:
            continue
        record.enrichment_status = result.status
        if not result.usable:
            continue

        touched = False
        summary = compose_summary(result)
        if summary and not record.generated_summary:
            record.generated_summary = summary
            applied["summaries"] += 1
            touched = True
        if result.topics and not record.generated_topics:
            record.generated_topics = list(result.topics)
            applied["topics"] += 1
            touched = True

        known = {(d.kind, d.round_label.strip().lower()) for d in record.deadlines}
        for entry in result.deadlines:
            candidate = Deadline.from_json(entry)
            if candidate.identity in known:
                continue  # the source already published this round; it wins
            record.deadlines.append(candidate)
            known.add(candidate.identity)
            applied["deadlines"] += 1
            touched = True

        if touched:
            applied["records"] += 1
    return applied


def worth_enriching(record: ConferenceInstance, now: Any) -> bool:
    """Could this record still be submitted to, as far as we can tell?

    Deliberately not ``record.active``. That flag is computed at *persist* time by
    ``mark_inactive``, so a freshly parsed record carries the dataclass default of
    ``True`` and filtering on it silently does nothing — a full run then queued
    1,037 records while reporting "0 inactive (skipped)", three quarters of them
    past editions nobody can submit to.

    The second clause matters as much as the first: a record with no usable
    deadline is not evidence that the call is closed, it is evidence that we do
    not know — and finding out is precisely what the website is being read for.
    """
    dated = [d for d in record.submission_deadlines if d.instant]
    if not dated:
        return True
    return record.is_relevant(now)


def plan_enrichment(
    instances: list[ConferenceInstance],
    series: list[ConferenceSeries],
    *,
    cache: dict[str, EnrichmentRecord] | None = None,
    limit: int | None = None,
    active_only: bool = True,
    now: Any = None,
) -> tuple[list[EnrichmentTask], dict[str, int]]:
    """Decide what to fetch, and account for everything not fetched.

    Returns the work list and a census of why records were left out, so the run
    can report "skipped 704 past editions" rather than quietly doing less than it
    looked like it would.
    """
    from datetime import UTC, datetime

    cache = cache or {}
    now = now or datetime.now(UTC)
    census = {"complete": 0, "closed": 0, "no_url": 0, "cached": 0, "queued": 0}
    by_key = {s.series_key: s for s in series}
    tasks: list[EnrichmentTask] = []

    for record in instances:
        gaps = gaps_for(record, by_key)
        if not gaps:
            census["complete"] += 1
            continue
        if active_only and not worth_enriching(record, now):
            census["closed"] += 1
            continue

        task = EnrichmentTask(
            instance_key=record.instance_key,
            url=clean_text(record.url),
            acronym=record.acronym,
            title=record.title,
            year_label=record.year_label,
            gaps=gaps,
            active=record.active,
        )
        if not task.is_fetchable:
            census["no_url"] += 1
            continue
        # A settled verdict is an answer, not a gap: re-asking a host that told us
        # no is how a polite crawler becomes an impolite one. A transient failure
        # is not a verdict, and is queued again.
        cached = cache.get(record.instance_key)
        if cached is not None and cached.status not in RETRYABLE_STATUSES:
            census["cached"] += 1
            continue

        tasks.append(task)
        census["queued"] += 1
        if limit is not None and len(tasks) >= limit:
            break

    return tasks, census
