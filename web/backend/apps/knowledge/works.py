"""What a person's own papers show: one extraction per work, ever.

The demonstrated side of a person (collaboration-network plan CN-02). Each of
their imported works is read once, independent of any reader — the reader is
deliberately absent from the input, as it is for the corpus précis
(:mod:`apps.content.comprehension`) — and decomposed by facet (design §3):

* one **sentence** per facet — problem, method, setting, and what an outsider
  could reuse — which retrieval ranks, per work;
* a few short **terms** per facet, which the linker turns into concepts;
* the main method restated **without field vocabulary** (design §5.5), so a
  technique can be recognised in a field that names it differently.

The extractor follows the pattern this codebase trusts for turning prose into
structure (:mod:`apps.research.state_extract`): a fixed schema, deterministic
validation, a grounding check against the work's own title and abstract, one
repair naming what failed, then refusal — per field, so one ungrounded field
costs that field and not the work.

Cost: one model call per work, keyed on (prompt version, source fingerprint)
and never repeated for unchanged text. A work with no abstract is not sent at
all: there is nothing to ground a facet in, and it would produce no edge.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from django.conf import settings

from apps.content.embeddings import embed_texts
from apps.research.state_extract import grounding_failures

from .linker import normalise
from .models import WorkFacets

logger = logging.getLogger(__name__)

#: The name every call here is billed against in the daily LLM ledger.
COMPONENT = "work_facets"

#: Stamped on every row. **Bump this whenever the prompt changes**; rows with an
#: older stamp are re-read on their next visit, and only those.
PROMPT_VERSION = "w1"

#: One retry naming what failed, then refusal (the state extractor's measure).
MAX_ATTEMPTS = 2

FACETS = ("problem", "method", "setting", "reusable")
MAX_TERMS = {"problem": 2, "method": 3, "setting": 3, "reusable": 2}
MAX_TERM_WORDS = 8
MAX_TERM_CHARS = 80
MAX_SENTENCE_CHARS = 400
#: Below this many content words an abstract is a title with a sentence after
#: it: too little to ground four facets in.
MIN_ABSTRACT_WORDS = 20

#: Neutral phrasings so abstract they would match everything (design §5.5:
#: "abstracting too far makes everything match"). Refused outright.
EMPTY_ABSTRACTIONS = frozenset(
    {
        "uses statistics",
        "statistics",
        "statistical analysis",
        "statistical methods",
        "data analysis",
        "analysing data",
        "analyzing data",
        "machine learning",
        "deep learning",
        "modelling",
        "modeling",
        "a method",
        "an algorithm",
        "computational methods",
        "computation",
        "optimisation",
        "optimization",
        "learning from data",
    }
)
#: A neutral phrase must keep the operation, which takes a few content words.
MIN_NEUTRAL_WORDS = 3

_WORD = re.compile(r"[a-z0-9]+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_STOP = frozenset(
    "the and for with that this from are was were our its into than then they "
    "them their there which while will would can could has have had not but all "
    "any use used using new also may these those such been more most other some "
    "when of in on to a an by as at or is be it we".split()
)

SYSTEM = (
    "You read one research paper and report what it shows, for a reader whose "
    "interests you do not know. No audience, no relevance judgement, no "
    "enthusiasm. You report only what the title and abstract say, in their own "
    "wording where you can, and you leave a field empty rather than infer it. "
    "Reply with one JSON object and nothing else."
)

PROMPT = """Read the paper below and report it as JSON with exactly these keys:

  "problem": one sentence — the problem the work addresses.
  "method": one sentence — the method or approach it uses.
  "setting": one sentence — the data, cohort, instrument, or setting.
  "reusable": one sentence — what an outside researcher could concretely
      reuse (a method, dataset, baseline, protocol); "" if nothing.
  "problem_terms": 1-2 short noun phrases naming the problem.
  "method_terms": 1-3 short noun phrases naming the techniques.
  "setting_terms": 0-3 short noun phrases naming the data or setting.
  "reusable_terms": 0-2 short noun phrases naming what could be reused.
  "method_neutral": the main method restated without the field's vocabulary,
      keeping what it does — e.g. "data assimilation" becomes "estimating a
      hidden state from noisy observations". Not a category ("machine
      learning", "statistics"): a reader must be able to tell which operation
      it is. "" if the paper has no method.
  "thin": true only if the text is too sparse to answer.

Terms are at most {max_words} words each. Use the paper's own words for terms.
Do not invent numbers, datasets, or names.

PAPER
-----
{source}
"""

REPAIR = """Your previous answer had these problems:
{failures}

Answer again with the same keys. Drop anything the paper does not support
rather than rewording it to pass."""

CompleteFn = Callable[[str, str], str | None]


def source_text(work) -> str:
    title = " ".join(str(work.title or "").split())
    abstract = " ".join(str(work.abstract or "").split())
    return f"Title: {title}\n\n{abstract}".strip()


def source_fingerprint(work) -> str:
    """A digest of exactly the text the model reads. A year or a citation count
    changing does not re-bill the model; an abstract arriving does."""
    payload = "␟".join((str(work.title or ""), str(work.abstract or "")))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def is_current(row: WorkFacets | None, work) -> bool:
    return (
        row is not None
        and row.prompt_version == PROMPT_VERSION
        and row.source_fingerprint == source_fingerprint(work)
    )


def _content_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall((text or "").lower())
        if word not in _STOP and len(word) > 2
    }


def _has_abstract(work) -> bool:
    return len(_content_words(work.abstract or "")) >= MIN_ABSTRACT_WORDS


@dataclass
class FacetOutcome:
    """What one work yielded, and why."""

    sentences: dict = field(default_factory=dict)
    terms: dict = field(default_factory=dict)
    method_neutral: str = ""
    thin: bool = False
    refused: list[str] = field(default_factory=list)
    attempts: int = 0


def _parse(raw: str | None) -> dict | None:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _term_ok(term: str, source: str) -> str | None:
    """Why a term fails, or ``None``. A term is short, so it is held to the
    narrow promise: at least one of its words is the paper's, and it invents no
    specifics."""
    words = term.split()
    if len(words) > MAX_TERM_WORDS or len(term) > MAX_TERM_CHARS:
        return f"term too long: {term[:60]!r}"
    if not (_content_words(term) & _content_words(source)):
        return f"term not in the paper: {term!r}"
    invented = grounding_failures(term, source)
    return invented[0] if invented else None


def _neutral_ok(phrase: str, source: str, method_terms: list[str]) -> str | None:
    key = normalise(phrase)
    if key in EMPTY_ABSTRACTIONS:
        return f"neutral phrase is a category, not an operation: {phrase!r}"
    if len(_content_words(phrase)) < MIN_NEUTRAL_WORDS:
        return f"neutral phrase too short to name an operation: {phrase!r}"
    if key in {normalise(term) for term in method_terms}:
        return f"neutral phrase repeats the method's own name: {phrase!r}"
    # Abstracted on purpose, so not held to word overlap — but it may not bring
    # in a number the paper does not have. Stricter than the shared specifics
    # check (years, amounts, ordinals): a neutral phrase has no business
    # carrying any figure of its own.
    invented = set(_NUMBER.findall(phrase)) - set(_NUMBER.findall(source))
    if invented:
        return f"neutral phrase invents {sorted(invented)}: {phrase!r}"
    return None


def validate(payload: dict, source: str) -> tuple[FacetOutcome, list[str]]:
    """Clean one reply. Returns what passed and what failed, field by field."""
    outcome = FacetOutcome()
    failures: list[str] = []

    for facet in FACETS:
        sentence = " ".join(str(payload.get(facet) or "").split())
        if len(sentence) > MAX_SENTENCE_CHARS:
            failures.append(f"{facet}: longer than one sentence")
            sentence = ""
        problems = grounding_failures(sentence, source) if sentence else []
        if problems:
            failures.append(f"{facet}: {problems[0]}")
            sentence = ""
        outcome.sentences[facet] = sentence

        raw_terms = payload.get(f"{facet}_terms") or []
        if isinstance(raw_terms, str):
            raw_terms = [raw_terms]
        kept: list[str] = []
        seen: set[str] = set()
        for raw in raw_terms if isinstance(raw_terms, list) else []:
            term = " ".join(str(raw or "").split())
            if not term or normalise(term) in seen:
                continue
            problem = _term_ok(term, source)
            if problem:
                failures.append(f"{facet}_terms: {problem}")
                continue
            seen.add(normalise(term))
            kept.append(term)
        if len(kept) > MAX_TERMS[facet]:
            failures.append(f"{facet}_terms: more than {MAX_TERMS[facet]}")
            kept = kept[: MAX_TERMS[facet]]
        outcome.terms[facet] = kept

    neutral = " ".join(str(payload.get("method_neutral") or "").split())
    if neutral and outcome.terms["method"]:
        problem = _neutral_ok(neutral, source, outcome.terms["method"])
        if problem:
            failures.append(f"method_neutral: {problem}")
            neutral = ""
    else:
        neutral = ""
    outcome.method_neutral = neutral[:200]

    outcome.thin = bool(payload.get("thin")) or not (
        outcome.terms["problem"] or outcome.terms["method"]
    )
    return outcome, failures


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


def extract(work, *, complete: CompleteFn | None = None) -> FacetOutcome | None:
    """One work into facets. ``None`` means the model could not be reached and
    the work should simply be tried again on the next run. Never raises."""
    if not _has_abstract(work):
        return FacetOutcome(thin=True, refused=["no abstract to read"])
    ask = complete if complete is not None else _settings_complete
    source = source_text(work)
    prompt = PROMPT.format(max_words=MAX_TERM_WORDS, source=source)
    best: FacetOutcome | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = ask(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001 - unavailable, not broken
            logger.warning("work facets unavailable for %s (%s)", work.pk, exc)
            if best is None:
                return None
            break
        payload = _parse(raw)
        if payload is None:
            failures = ["the reply was not one JSON object"]
            outcome = FacetOutcome(thin=True)
        else:
            outcome, failures = validate(payload, source)
        outcome.attempts = attempt
        outcome.refused = failures
        best = outcome
        if not failures:
            break
        prompt = (
            PROMPT.format(max_words=MAX_TERM_WORDS, source=source)
            + "\n"
            + REPAIR.format(failures="\n".join(f"- {f}" for f in failures))
        )
    return best


def extract_many(
    works: Sequence, *, complete: CompleteFn | None = None
) -> dict[int, FacetOutcome]:
    """Extract each work; pure with respect to the database, so it may run in
    threads (up to ``WRITEUP_LLM_CONCURRENCY``, as the précis stage does)."""
    if not works:
        return {}
    workers = max(1, min(int(settings.WRITEUP_LLM_CONCURRENCY), len(works)))
    if workers == 1:
        results = [(work, extract(work, complete=complete)) for work in works]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(
                zip(
                    works,
                    pool.map(lambda w: extract(w, complete=complete), works),
                    strict=True,
                )
            )
    return {work.pk: outcome for work, outcome in results if outcome is not None}


_VECTOR_FIELDS = (
    ("problem", "problem_vec"),
    ("method", "method_vec"),
    ("method_neutral", "method_neutral_vec"),
    ("setting", "setting_vec"),
    ("reusable", "reusable_vec"),
)


def missing_vectors():
    """Rows with a facet sentence whose vector is missing — found in SQL, so the
    nightly pass does not load every stored vector to discover the few gaps."""
    from django.db.models import Q

    gap = Q()
    for text_field, vec_field in _VECTOR_FIELDS:
        gap |= Q(**{f"{vec_field}__isnull": True}) & ~Q(**{text_field: ""})
    return WorkFacets.objects.filter(thin=False).filter(gap)


def fill_vectors(rows: Iterable[WorkFacets]) -> int:
    """Embed every facet sentence a row has and its vector lacks.

    Kept apart from extraction so an embedder that was down when a work was
    read costs a night's delay on its vectors, not a second model call.
    """
    wanted: list[tuple[WorkFacets, str, str]] = []
    for row in rows:
        if row.thin:
            continue
        for text_field, vec_field in _VECTOR_FIELDS:
            text = getattr(row, text_field)
            if text and getattr(row, vec_field) is None:
                wanted.append((row, vec_field, text))
    if not wanted:
        return 0
    vectors = embed_texts([text for _, _, text in wanted])
    if not vectors:
        return 0
    touched: dict[int, tuple[WorkFacets, list[str]]] = {}
    for (row, vec_field, _), vector in zip(wanted, vectors, strict=True):
        setattr(row, vec_field, vector)
        touched.setdefault(row.pk, (row, []))[1].append(vec_field)
    for row, fields in touched.values():
        row.save(update_fields=[*fields, "updated_at"])
    return len(wanted)


def store(work, outcome: FacetOutcome) -> WorkFacets:
    """Write one outcome, stamped so it is never re-read for unchanged text."""
    row, _ = WorkFacets.objects.update_or_create(
        author_work=work,
        defaults={
            **{facet: outcome.sentences.get(facet, "") for facet in FACETS},
            "terms": {facet: outcome.terms.get(facet, []) for facet in FACETS},
            "method_neutral": outcome.method_neutral,
            "thin": outcome.thin,
            "refused": outcome.refused,
            "openalex_field_id": work.openalex_field_id,
            "prompt_version": PROMPT_VERSION,
            "source_fingerprint": source_fingerprint(work),
            # A re-read replaces the text, so its old vectors no longer match.
            **{vec: None for _, vec in _VECTOR_FIELDS},
        },
    )
    fill_vectors([row])
    return row


def pending(works: Iterable) -> list:
    """The works whose facets are missing or were read under an older prompt."""
    works = list(works)
    rows = {
        row.author_work_id: row
        for row in WorkFacets.objects.filter(author_work__in=[w.pk for w in works])
    }
    return [work for work in works if not is_current(rows.get(work.pk), work)]
