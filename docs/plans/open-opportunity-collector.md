# Plan — Replace Pivot-RP / ProQuest with the open-source opportunity collector

**Status:** working document. Delete when shipped; record the outcome in
`docs/changelog.md`, `docs/repo-map.md`, `docs/architecture.md`, and
`docs/api-contract.md`.

**Branch:** `claude/open-source-grants-conferences-fb07a6` (worktree; merges to
`main`, worktree removed at the end).

---

## Objective

Retire Pivot-RP (ProQuest) as the source of grants and conferences and replace it
with the open collector at `/home/bdgr/Tools/Grant` — 6 grant adapters and 6 of
its 7 conference adapters (see D5), all public. Preserve every field the new data carries that
Pivot never had: CCF / CORE / THCPL ranks, trust tiers, **multiple deadlines per
record**, per-source links, and licence/attribution. Drive expiry from the
**written deadline**, never the posted date. Feed the result into the existing
recommendation stack, the nightly run, user reports, the website, and the Discord
bot.

Fellowships are **out of scope for replacement** — they come from the public
Illinois Fellowship Finder, not Pivot, and survive intact.

---

## Decisions taken (locked)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Deadlines: display all, remind on next.** `ContentDeadline` keeps its `(content, kind)` key and holds the next future occurrence per kind. The complete deadline array lives in `metadata["deadlines_structured"]` and renders in full. **A hover on the deadline reveals every round.** | User decision. Avoids touching the 12-file reminders stack; the display requirement and the reminder requirement are separable. |
| D2 | **Rankings are visual only.** CCF / CORE / THCPL badges render on the card, in filters, and in reports. They never affect relevance order, thresholds, or the LLM verdict. **Each badge has a hover explaining what that rank means.** | User decision. 75% of series carry no rank, so ranking on it would systematically bury non-CS venues. Also avoids re-deriving thresholds and re-running the eval harness. |
| D3 | **Trust tier is the always-present signal.** Every series has one (A: 334, B: 1,091). It renders on every conference card with a hover explaining what the tier means and, explicitly, that tier B is *not* a demotion — it is where every non-CS venue lives. | User decision. Correct: rankings cover 25% of series, trust tier covers 100%. |
| D4 | **All 5 active users are scored** by the migration re-scrape, bypassing the `SCHEDULED_REPORTS` entitlement gate for that one run. The nightly keeps its normal gating afterwards. | User decision. |
| D5 | **Six conference adapters + all six grant adapters are enabled**: `ccf_deadlines`, `openreview`, `miccai`, `ams_mathcal`, `society_pages`, `openresearch`. **Only `wikicfp` is dropped.** Per-record source + licence attribution is displayed regardless. | User decision. `wikicfp` costs ~2,811 requests against the site's published `Crawl-delay: 5` (~3.9 h), is user-submitted with a large predatory-spam share, and lands in `COMMUNITY_SOURCES` → **trust tier C, quarantined from default output** — so it would collect thousands of records that never surface. `openresearch` shares only that last property, and the dblp registry (D5a) resolves it for any venue dblp knows: it is **one request, 342 future-deadline records, 409 KB, 2.6 s, no auth**. Non-CS coverage comes from the `SOCIETY_SOURCES` trio, which land in tier B and do surface. |
| D5a | **Wire the dblp registry refresh** (`utils/conferences/collect/registry/dblp.py`) as a scheduled stage. | User decision. It is **one SPARQL POST, ~8 MB, ~5 s**, returning all 9,325 venues with indexed-proceedings-year counts, under **CC0**. Today `dblp_found = 0` on all 1,425 series, so no venue can reach tier A except via a CCF rank. The registry promotes venues on evidence (`indexed_years >= 3`) and fills `first_year` / `last_year` / `dblp_key`. Note `dblp.org/robots.txt` disallows `/search`, `/search/venue` and `/*.json` — SPARQL is the compliant route, not a preference. **CORE's registry adapter stays disabled**; its ranks already arrive via `ccf_deadlines`. |
| D5b | **`openresearch` is a secondary source, never authoritative on descriptive fields.** Its `venue_native = False`, so organiser-native text wins at merge. It contributes a deadline-and-location spine: no descriptions, no timezone (bare calendar dates, basis recorded honestly), no quality signals on future records. | The adapter's own recon. Its geographic skew (166 of 342 from China + Japan) is a signal for the trust layer to weigh, not grounds for the adapter to pre-judge. |
| D6 | **The collector is vendored into the backend** at `web/backend/apps/scraper/collect/`, and runs **in the backend container**. | It is pure HTTP; the host/container split existed only because Pivot needed Playwright + an SSO session. Deps are near-identical. `docs/architecture.md` gives `scraper` ingestion ownership. |
| D7 | **Conference expiry keys on the last written deadline**, with a parsed event date as fallback. Grants expire at `max(all rounds)`. | The user's directive ("expiration must be driven by the written deadline"), and `event_start` is NULL on 100% of collector rows so the current event-date rule would expire nothing. |
| D8 | **Fellowships are untouched** apart from relocating their code out of the `pivot/` directory. | The Illinois Fellowship Finder is public and free; only its *location* in the tree is a Pivot artefact. |
| D9 | **Every record's description is produced by an LLM under a structured-output contract, verified in a bounded agent loop, and that verified text is what gets embedded for search.** Universal — grants and conferences, not just records missing text. Unverified output is never shown. See Phase 8. | User decision. Raw source text is unusable as a uniform embedding basis: `description` averages 11,411 chars for `nsf` versus 894 for `nih_guide`, EU rows carry HTML fragments, and `cfp_text` is empty on all 2,234 conference rows. A schema-checked extraction makes every record's vector comparable. |
| D10 | **The extraction runs after ingest and before embedding**, as its own stage, at **16 workers with reasoning off**. The one-time backfill is **~41 minutes measured** (`EXP-2026-08-007`) and runs outside the nightly; the nightly extracts **only genuinely new records**. | Ordering follows from D9 — the embedded text is the extraction's output. The settings are measured, not assumed: an earlier 5–6 h estimate came from the collector's published table for a different endpoint and was out by an order of magnitude. |

## Assumptions

- A1. The collector's code runs on Python 3.13. Its `>=3.12,<3.13` pin is
  conservative, not load-bearing. **Verified in Phase 1, not assumed past it.**
- A2. `bge-small-en-v1.5` vectors from the collector and from Mycelium occupy the
  same space (same model, same 384 dims, same L2 normalisation, no BGE prefix in
  fastembed 0.8.0). We re-embed anyway, so this is a convenience not a dependency.
- A3. The 8 existing saves that point at Pivot grants/conferences survive the wipe
  as snapshots (`SavedOpportunity.content` is `SET_NULL` with a display + deadline
  snapshot). They will not re-attach to the new records. Accepted.
- A4. The first nightly after the swap makes every reader's whole Top-25 "new"
  (empty prior slate). Expected and communicated, not suppressed.

---

## Phase 0 — Baseline and safety net

1. Record the pre-change test baseline so later failures are attributable.
2. Snapshot the live Postgres (`pg_dump`) before any destructive step.
3. Confirm the collector's stores are readable and record their row counts.

**Validation**
```bash
uv sync --project web/backend --extra scrapers --extra embeddings
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium \
  uv run --directory web/backend python -m pytest -q --no-header
```

### Baseline — recorded 2026-08-16 (DONE)

**`1583 passed in 219.24s`. Zero failures.**

Two notes that matter for reading later runs:

- The four failures the recon predicted do **not** occur. Three came from
  `test_opportunity_clusters.py` calling the real embedder without the
  `embeddings` extra installed, and one (`test_site_and_resume_merge`) from
  running on SQLite with no `LLM_MODEL`. Syncing the extra and pointing
  `DATABASE_URL` at the Compose Postgres removes all four. **Any failure from
  here is ours.**
- The recorded memory that `test_high_signal.py` date-flakes past ~2026-07-19 is
  **stale** — the fix landed; it passes on 2026-08-16.

### Live state — recorded 2026-08-16 (DONE)

| | count |
|---|---|
| Active users / labs / projects | **5** / 4 / 1 |
| `grant` from `pivot` | 2,143 |
| `conference` from `pivot` | 2,961 |
| `fellowship` from `illinois-fellowship-finder` | 829 (**survives**) |
| `paper` (OpenAlex / PubMed / SemanticScholar) | 35,209 (**survives**) |
| `RelevanceScore` / `ContentDeadline` / saves | 5,586 / 7,208 / 9 |

Collector stores: 2,190 grants; 1,425 series / 2,234 instances / 3,196 deadlines.

**Snapshot:** `/home/bdgr/Agents/mycelium-backups/mycelium-pre-opportunity-migration-20260816.dump`
(147 MB, `pg_dump -Fc`). Deliberately **outside** the repository —
`data/backups/` is not in `.gitignore` and would have been committed.

---

## Phase 1 — Vendor the collector, verified on 3.13

1. Copy `utils/collect_core/`, `utils/grants/collect/`, `utils/conferences/collect/`
   into `web/backend/apps/scraper/collect/` preserving module structure.
   Drop the retrieval engine (`utils/grants/{retrieval,embedding,suggest,ingest,
   corpus,writers,retrievers,normalizers}`), the Flask app, and `run.py` —
   Mycelium has its own ranking stack.
2. Rewrite the `MYCELIUM_*` env names to `COLLECT_*` — they collide with Django's
   own settings namespace.
3. Add `requests` and `pyyaml` to `web/backend/pyproject.toml`.
4. Port the collector's own tests for the vendored modules.

**Validation**
```bash
uv run --project web/backend python -c "from apps.scraper.collect.conferences.record import ConferenceInstance; print('import ok')"
uv run --project web/backend python -m pytest web/backend/apps/scraper/tests/collect -q
```
Acceptance: every vendored module imports on 3.13 and its tests pass. If any
3.12-only construct surfaces, fix it here — do not carry the pin forward.

---

## Phase 2 — Lift the non-Pivot code out of `pivot/` (must precede any deletion)

Four things inside `apps/scraper/pivot/` have nothing to do with Pivot. Move them
**first**, verbatim where possible, so the tree stays importable at every step.

| From | To | Why |
|---|---|---|
| `pivot/fellowships/constraints.py` | `apps/scraper/eligibility/constraints.py` | The fellowship eligibility rule engine. Consumed by `apps/content/fellowships.py::_constraint_gates` **through five JSON keys only** — the `metadata["constraints"]` block must stay byte-for-byte or gating silently stops. |
| `pivot/fellowships/parsers.py` | `apps/scraper/eligibility/parsers.py` | Provider-agnostic. Its seven-value deadline-type vocabulary is load-bearing for `deadlines_projection.py:36-44`. |
| `pivot/fellowships/illinois.py`, `__init__.py` | `apps/scraper/fellowships/` | The actual public source. Keeps Playwright. |
| `pivot/normalize.py::normalize_amount` | `apps/content/formatting.py` | **Module-level import at `apps/content/serializers.py:5`** — deleting the package without this first 500s every content API endpoint. |
| `pivot/deadlines.py` | (contract only) | `submission_status`'s 11 output keys and the three `ContentDeadline` kinds are what the reminders feature is built on. **Keep the contract, replace the parser** in Phase 5. |

Move the pure tests with them: `test_fellowship_constraints.py`,
`test_fellowships_parsers.py`.

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/scraper web/backend/apps/content -q
```
Acceptance: same pass/fail set as the Phase 0 baseline. Nothing new breaks.

---

## Phase 3 — The mapper: collector records → `ContentItem`

New module `apps/scraper/collect/mapping.py`, replacing `pivot/records.py`.

### 3.1 Grants — `Opportunity` → `ContentItem(type="grant")`

- `external_id` = `stable_key`; `source` = `grants:<adapter>`.
- **The deadline rule** (this is the core fix):
  ```
  rounds        = sorted({close_date} ∪ additional_due_dates) − {null}
  deadline_date = min(d for d in rounds if d >= today)  else  max(rounds)  else  ""
  prune_after   = max(rounds)                            else  ""     # "" = rolling, never expires
  ```
  `deadline_date` and `prune_after` differ on 173 of 2,190 rows. Conflating them
  is the current bug.
- `metadata["due_dates"]` carries the complete round array for the hover.
- `metadata["published_on"]` = `posted_date` — a **new key**, not `first_seen`.
  `GrantSerializer.get_posted` currently returns Mycelium's ingest date and labels
  it "Posted"; repoint it.
- `html.unescape()` every title — 95 of 2,190 carry entities including a
  zero-width space that breaks substring matching.
- `record_kind == "overlay"` (4 rows, NIH policy notices with no deadline) is
  filtered out of the feed.
- `metadata["license"]` = a per-source constant (US federal grants are public
  domain; the EU portal carries its own reuse framework string).

### 3.2 Conferences — `ConferenceInstance` + `ConferenceSeries` → `ContentItem(type="conference")`

Mycelium has no series concept: **denormalise the series onto every instance.**

- `external_id` = `instance_key`; `source` = `conf:<adapter>`.
- **The deadline rule:**
  ```
  submission      = [d for d in deadlines if d.kind in {abstract, submission} and d.instant]
  next_submission = min(d.instant for d in submission if d.instant >= now)
  deadline_date   = next_submission[:10]  else ""
  prune_after     = max(d.instant for d in deadlines)[:10]  else event_end/start  else ""
  open            = next_submission is not None
  ```
  Only `abstract` and `submission` gate openness. **Never the event date.**
  Parse instants with `datetime.fromisoformat(s.replace("Z","+00:00"))` — 24 of
  3,196 carry microseconds and `strptime("%Y-%m-%dT%H:%M:%SZ")` crashes on them.
- `metadata["deadlines_structured"]` = the full 8-key array, verbatim. Drives the
  hover.
- `metadata["rankings"]` = the series JSON verbatim; `metadata["rank_badges"]` =
  a flattened `[{system, rank, edition}]` so the frontend never parses a dict.
- `metadata["trust_tier"]`, `["red_flags"]`, `["quality_warnings"]`,
  `["series_key"]`, `["license"]`, `["source_links"]`.
- **`instances.active` is dropped** — it is a stale collection-time flag (400
  flagged active, 354 actually open, 6 wrong within hours). Liveness is recomputed.
- Scheme-normalise `url` (`www.foo.org` with no scheme resolves relative to our
  origin in an `<a href>`).
- De-duplicate year from acronym (OpenReview emits `"NOVAS 2026"` then a separate
  `year_label` of `2026`).
- Map `country_code` ISO alpha-2 → full name, or the conference rail's
  `continentOf()` buckets every record to "Other".

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/scraper/tests/test_collect_mapping.py -q
```
Acceptance: new unit tests cover the multi-round grant (`num:PAR25144`, 10 rounds),
the chemical-oceanography case (posted 2015, closes 2026), the 24-deadline
conference (VLDB 2027), the rolling grant (`close_date` NULL), the microsecond
instant, and the AoE conversion.

---

## Phase 4 — Ingest, dedupe, expiry

New `apps/scraper/collect/ingest.py`, replacing `pivot/ingest.py`.

**Runtime order is `ingest → extract (Phase 8) → embed`** (D10). Embedding is a
separate step at the end, not part of the upsert, because the text it embeds is
the extraction's verified output.

1. **Upsert keyed on `(source, external_id)`** — the existing partial unique
   constraint. A record already present is **updated, never re-inserted**. Keep
   the immutable `first_seen` contract and the `constraints["source"] == "llm"`
   preservation.
2. **`prune_expired`**: drop the hard-coded `OPPORTUNITY_SOURCES` allow-list and
   rely on `type__in`, so new source ids can never be silently skipped. Keep the
   `pre_delete` signal path so reminders are marked stale.
   Emit strictly zero-padded ISO — the comparison is lexicographic and
   `"2026-8-1" < "2026-08-16"` is `False`.
3. Rebuild the `ContentDeadline` projection from structured data (Phase 5).

### 4b — The embed step (runs after Phase 8)

4. **Embed from `metadata["search_text"]`**, which Phase 8 composes from the
   verified extraction (or from raw text for refused records, flagged
   `search_text_source = "raw"`).
5. **Re-embed everything** rather than lifting the collector's vectors: its
   conference vectors are series-level (1,420 distinct vectors for 2,234
   instances), so editions are indistinguishable.
6. **Record `metadata["embedding_model"]`** beside every vector. Mycelium stores
   none today, so a model change would leave the corpus silently in the old space
   with nothing to trigger a refit — a latent correctness bug, not an optimisation.
7. Re-embed only on `search_text` change (hash comparison), so a nightly that
   changes nothing costs no embedding.

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/scraper/tests/test_collect_ingest.py -q
```
Acceptance: a second ingest over unchanged input reports **0 created, 0 updated,
0 embedded** (idempotency). This also protects `run_analytics.collect_discovery`,
which counts `created_at` on the run day and would report a fake spike on
re-insert.

---

## Phase 5 — Deadline projection and the multi-deadline hover

1. Rewrite `deadlines_projection._conference_specs` to read
   `metadata["deadlines_structured"]` instead of lazily importing
   `pivot.deadlines.parse_deadlines`. **Keep the output contract** — the three
   `ContentDeadline` kinds and `submission_status`'s 11 keys.
2. Per D1: `ContentDeadline` holds the **next future occurrence per kind**.
   Kind mapping: `abstract → abstract`, `submission → manuscript`,
   grants' every round → `application`, everything else → `other` (never gates
   openness). `is_estimated` / `dates_inferred` → `confidence = "anticipated"`.
3. `_grant_specs` emits the next `application` round, not the only one.

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/content/tests/test_content_deadlines.py -q
```
Acceptance: all 12 existing assertions pass unchanged.

---

## Phase 6 — Delete Pivot

Only now, with everything lifted and the replacement working.

- **Delete:** `apps/scraper/pivot/` (16 files, 3,417 lines), root `pivot.py`
  (411), the commands `pivot_login` / `scrape_pivot` / `ingest_pivot`, and the
  three dedicated Pivot test files.
- **Edit:** `apps/content/serializers.py:5`, `prune_opportunities.py:17`,
  `deadlines_projection.py:141`, `opportunities.py:1179/1183/1195`,
  `manual_all.py:277-378`, `mylo/tests/test_daily_run_reporting.py:41`, and the
  36 `source="pivot"` literals across 26 files.
- **Drop deps:** `beautifulsoup4`. **Keep `playwright`** — the Illinois
  fellowship scraper still needs it.
- **Dead env:** `PIVOT_STORAGE_STATE`, `storage_state.json`, `data/pivot/`, and a
  hard-coded personal remote host in `pivot.py`.
- **Leave alone:** `docs/changelog.md` (append-only), `docs/chats/`,
  `docs/research/literature/grants-fellowships.md` (literature *about* the product).

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend -q
grep -rin "pivot\|proquest" web/backend web/app mylo --include='*.py' --include='*.ts' --include='*.tsx' | grep -v changelog
```
Acceptance: full suite back to the Phase 0 baseline; the grep returns only
intentional historical references.

---

## Phase 7 — Wipe and re-populate

1. New command `reset_opportunities --types grant,conference` — ORM-level delete
   so `pre_delete` fires and reminders are marked stale. **Fellowships, papers,
   users, labs, projects, saves, billing, and Discord links are untouched.**
2. Run the collector across all 13 adapters with **12 parallel workers**.
3. Ingest, embed, project deadlines.

**Parallelism.** The collector's `ThreadPoolExecutor` + per-host lock exists only
in stage 4 today; fetch across adapters is sequential. Extend the same pattern to
the fetch stage: 12 workers over the adapter list, per-host locks preserved so
concurrency never becomes 12 simultaneous hits on one site.

**Validation**
```bash
docker exec mycelium-postgres-1 psql -U mycelium -d mycelium -tAc \
  "select type, source, count(*) from content_contentitem group by 1,2 order by 1,3 desc;"
```
Acceptance: zero rows with `source='pivot'`; grants and conferences present under
`grants:*` / `conf:*`; fellowship count still 829; **no `prune_after` earlier than
its record's last written deadline.**

---

## Phase 8 — LLM structured extraction, verified in a loop (D9)

**This is the largest phase and the one the retrieval quality depends on.** It
runs **after ingest and before embedding**, because its verified output *is* the
embedded text.

### 8.1 Why every record, not just the ones missing text

The collector's own enrichment is conferences-only and gap-gated. Per D9 it
becomes universal, for a measurable reason: the raw source text is wildly
inconsistent and mostly boilerplate. Measured on the live store —
`description` averages **11,411 chars for `nsf`, 4,975 for `eu_portal`, 1,648 for
`grants_gov`, 894 for `nih_guide`**, EU rows carry literal `">` HTML fragments,
and conferences have **`cfp_text = ""` on all 2,234 rows**. Embedding that
directly means a grant's vector is dominated by whichever agency writes longest,
not by what it funds. The collector's author already fought half this battle —
`rank.embedding_text`'s "what NOT to embed" list exists because eligibility and
applicant-type boilerplate once made a third of the corpus embed 501(c)(3)
language.

A uniform, model-extracted, schema-checked description makes every record's
vector comparable.

### 8.2 The structured output contract

One JSON object per record, fixed schema, no free-form additions. The model is
told the schema and given only the source text; **it never sees another record.**

**Grants**
```json
{
  "summary":        "2-3 sentences: what this funds and why it exists",
  "purpose":        "one sentence: the funder's stated goal",
  "audience":       "one sentence: who this is for",
  "research_areas": ["...", "..."],
  "eligibility":    "one paragraph, or \"\" if the source does not state it",
  "award_summary":  "plain-language money line, or \"\"",
  "confidence":     "high | medium | low"
}
```

**Conferences**
```json
{
  "summary":        "2-3 sentences: what this venue is about",
  "purpose":        "one sentence",
  "audience":       "one sentence",
  "topics":         ["...", "..."],
  "field":          "the discipline in plain words",
  "confidence":     "high | medium | low"
}
```

Enforced by JSON-schema validation on the reply, not by prompt politeness. A
reply that does not parse, or that omits a required key, is a **failed attempt**,
not a partial result.

### 8.3 The agent loop

```
source text ──> EXTRACT ──> VALIDATE ──┬── pass ──> APPLY (store + embed + show)
     ▲                                 │
     └──── REPAIR (failures fed back) ─┴── fail ──> retry (bounded)
                                              │
                                    exhausted ─┴──> REFUSE (record reason, fall back, do not show)
```

1. **Source text.** Grants: `description` + `eligibility` from the record.
   Conferences: `cfp_text` where present, else the venue website fetched through
   the robots-aware `RobotsGate` with per-host locks.
2. **Extract.** One call, `temperature=0.0`, through `apps/core/llm.py` so every
   call lands in the `core.LLMUsageDaily` ledger.
3. **Validate — deterministic, no model.** Every check is code:

   | Check | Rule | Refusal |
   |---|---|---|
   | Schema | parses, every required key present, correct types | `malformed` |
   | Bounds | each field within its length limits; lists non-empty and de-duplicated | `out_of_bounds` |
   | Identity (conferences) | acronym (≥3 chars) on the page, else ≥50% of the title's >4-char content words | `not_the_venue` |
   | Prose grounding | `overlap_ratio(summary + purpose + audience, source) >= 0.45`, checked as **one atomic block** — the collector's docstring records why splitting it let a placeholder page's purpose and audience through unchecked | `ungrounded_prose` |
   | Topic grounding | every topic/area shares a word with the source | `ungrounded_topic` |
   | Dates | verbatim case-insensitive substring of the source, then **we** parse it, `2000 ≤ year ≤ 2035` | `date_not_on_page` / `unparseable` |
   | No-invention | no sentence asserting a number, date, or amount absent from the source | `unsupported_claim` |

4. **Repair.** On failure the specific failed checks are fed back — *"`topics[2]`
   does not appear in the source; `summary` overlaps the source at 0.31"* — and
   the model retries. **Bounded at `EXTRACTION_MAX_ATTEMPTS = 3`**, so a record
   can never spin.
5. **Apply or refuse.** Verified output is stored and embedded. An exhausted
   record records its last refusal reason, **falls back to the truncated raw
   source text so it stays retrievable**, and is **not shown as an AI summary**.

### 8.4 What gets embedded

`metadata["search_text"]` is composed from the **verified extraction**:
`summary + purpose + audience + research_areas|topics`, plus the identity fields
that must always be searchable (title, acronym, funder, opportunity number).
Refused records fall back to the old composition over raw text. The
distinction is recorded in `metadata["search_text_source"] ∈ {extracted, raw}`,
so retrieval quality can be measured against it later rather than guessed at.

### 8.5 Cost — measured, not estimated

**MEASURED: the backfill is ~41 minutes.** `EXP-2026-08-007`, 16 workers,
reasoning off: **1.798 records/s, 3.45 s median latency, 3.1 % refusal**
(0.0 % grants, 6.2 % conferences).

An earlier draft of this plan said 5–6 hours. That figure was extrapolated from
the standalone collector's published table (0.24 rec/s, 25–49 s median), which
measured a **different endpoint** — its own `localhost:9090` — not Mycelium's
LiteLLM proxy. It was wrong by roughly an order of magnitude. See
`EXP-2026-08-006` for the correction and `EXP-2026-08-007` for the final numbers.

**Settings that follow from the measurement:**

| Setting | Value | Why |
|---|---|---|
| Workers | **16** | No plateau at 12 (0.905 → 1.125 rec/s). The collector's table plateaued at 12; that describes its endpoint, not this one. |
| Reasoning | **off** (`LLM_REASONING=none`, already the `.env` default) | 5× faster than `thinking-medium` for one extra refusal in 32 records. |
| `MAX_ATTEMPTS` | 3 | Mean attempts per verified record is 1.16–1.23, so the cap is a backstop, not a budget. |

`effort-medium` is **strictly dominated** — slower than `thinking-medium`
(44.4 s vs 31.2 s median) *and* refusing far more. Never select it.

The nightly then extracts **only genuinely new records** — the newness gate the
collector's `plan_enrichment` never wired up (it filters on gaps and never reads
`new_items`). At a realistic tens-of-new-records-a-day that is seconds. Verdicts
are cached and settled statuses are never re-asked.

### 8.5b The grounding floor is source-length-aware (do not flatten it)

`EXP-2026-08-007` established that a single overlap floor cannot serve both
domains. Measured distinct content words in the source:

| domain | min / median / max |
|---|---|
| conference | 6 / **9** / 14 |
| grant | 12 / **484** / 1142 |

A 2–3 sentence summary carries ~35 content words, so overlap against a 9-word
conference stub tops out at ≈0.26. **The inherited 0.45 floor refused every
conference by construction** — it was measuring arithmetic, not honesty, and it
produced the fake 34 % refusal rate that nearly cost this plan a 5× slower
reasoning arm.

Two regimes, both verified to fire (RESULTS.md table):

- **≥ 80 source content words** → the 0.45 overlap floor, unchanged. Every grant.
- **< 80** → overlap is not tested; the prose must instead **invent no
  specifics**: every year, ordinal, integer and money token in the summary must
  appear in the source.

⚠️ **This is a loosening, and loosening a validator is how a check gets quietly
gutted.** The guard is the `unsupported_claim` counter: if the stub regime were
inert, invented specifics would sail through uncounted. It fired zero times on
live data, so it was exercised directly with hand-built cases — an invented year
and an invented attendance figure are both refused, a year present in the source
passes. Keep that test when porting.

### 8.6 Three defects to fix on port

- **Fix the multi-deadline collapse.** `apply_enrichment` dedupes verified
  deadlines by `(kind, round_label)` and the model returns `""` for the label
  every time, so one live record had **8 verified deadlines reduced to 4**.
- **Compare the page hash.** `page_hash` is stored and never read, so a page that
  moves its deadline after a settled `ok` verdict is never re-read.
- **Wire the newness gate** (§8.5).

### 8.7 Provenance never blurs

Extracted text goes to `metadata["ai_summary"]` / `["ai_fields"]` with
`metadata["summary_source"]`, **never** into `description` / `cfp_text`. Every
recovered deadline is `is_estimated=True`, `source="enrichment:<url>"`, basis
prefixed `inferred:`. The UI renders it under a `summary from website` marker,
and `docs/purpose.md`'s trust rule applies: a refused record says so rather than
showing a confident-looking summary nobody checked.

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/scraper/tests/test_collect_extract.py -q
```
Acceptance, all with a stubbed model and no network:
- a reply missing a required key is `malformed` and triggers a repair attempt;
- a hallucinated date, an ungrounded topic, a wrong venue, and prose written from
  priors each produce their own recorded refusal;
- a record that fails 3 attempts falls back to raw text, is marked
  `search_text_source = "raw"`, and renders **no** AI summary;
- a repair attempt that fixes the cited failure is accepted;
- the attempt counter is honoured — no record ever exceeds 3 calls.

**A refusal is a first-class outcome, counted and shown, never a silent drop.**

---

## Phase 9 — API surface

| File | Change |
|---|---|
| `serializers.py::_OpportunitySerializer` | `source`, `license`, `license_url`, `source_links` — all three areas inherit |
| `serializers.py::ConferenceSerializer` | `rankings`, `rank_badges`, `trust_tier`, `red_flags`, `quality_warnings`, `deadlines_structured`, `year_label`, `acronym` |
| `serializers.py::GrantSerializer` | `published_on`, `opportunity_number`, `due_dates`, `deadline_text`, `dates_inferred`, `original_deadline`, `loi_date`; repoint `get_posted` off `first_seen` |
| `migrations/000X` | Re-issue the FTS trigger — it hard-codes metadata key names. Keep `title` / `abstract` / `sponsor` / `matched_topics`; add `opportunity_number` and `activity_codes` at weight C |
| `docs/api-contract.md` | Document the new fields, and fix the existing `addressable_deadlines` entry (documented as `[{kind, date}]`, actually `{kind, due_date, confidence, label}`) |

**Validation**
```bash
uv run --project web/backend python -m pytest web/backend/apps/content/tests -q -k serializer
```

---

## Phase 10 — Frontend

Per `docs/styles.md`: **never colour alone** (WCAG 2.2 AA), and **gold
(`--accent`) is reserved for opportunity signals** — a quality rank must not use
it. Reuse the `EligibilityBadge` idiom (a `Record<key, {label, description,
token}>` lookup + `color-mix` pill + `aria-label`), not `MatchRing` (two
incomparable scales on one card).

1. **Rank badges** on the conference card (`conferences-section.tsx:136-143`),
   each with a **hover explaining what that rank means** — authored copy, since no
   explanation exists as data anywhere in the collector. `A*` carries a literal
   asterisk. `N` means "not ranked by this system", not a rank.
2. **Trust tier badge on every card** with a hover explaining the tier, stating
   plainly that **B is not a demotion** — it is where every non-CS venue lives.
3. **Deadline hover** showing all rounds — the multi-deadline surface. `metadata
   ["deadlines_structured"]` (conferences) and `metadata["due_dates"]` (grants).
   Keyboard-accessible and touch-accessible, not hover-only.
4. **Ranking filter group** in `conference-filters.tsx` — three places per facet
   (state key, `DEFAULT_*_FILTERS`, `hasActive*Filters`); missing one is the easy bug.
5. **Fix `COUNTRY_TO_CONTINENT`** for ISO alpha-2 codes.
6. **Source links + licence** in the card footer. Check `saves-filters.tsx:68-81`
   first — `searchableText` duck-types cards by field name, so an identically named
   field on two card types breaks the narrowing.
7. `types.ts`: new `ConferenceRanking`, `SourceLink`, `TrustTier`; widen
   `OpportunityBase`, `ConferenceOpportunity`, `GrantOpportunity`.

**Validation**: browser-verify via the preview tools — DOM reads, not screenshots
alone. Check loading, empty, populated, error, unranked, no-deadline, and
reduced-motion states, plus mobile width and dark theme.

---

## Phase 11 — Reports and Discord

`briefing._showcase_item` (`briefing.py:234-282`) is the choke point — every
downstream renderer sees only what this dict carries. Add there **first**.

1. `_showcase_item`: add `rankings`, `trust_tier`, `deadlines`, `license`,
   `source_name`.
2. `daily_report.ReportItem` + `_item_from_score`: carry them.
3. `daily_report_pdf._item_flowables`: `meta_bits` is a `"  ·  "`-joined list, so
   `CCF A · CORE A*` drops in with no layout change. `_chip_stack` is the stronger
   placement for a rank chip.
4. **Do not widen the markdown grammar.** Three independent parsers implement it
   (`briefing_sections`, `daily_report_pdf._split_item_line`, `markdown-prose.tsx`)
   and both consumers keep the *first* deadline and delete the rest. Multi-deadline
   detail goes in the **structured PDF listings**, which read `ReportItem` directly.
5. Discord: fix `discord_commands._search_row` — its url is
   `meta["pdf_url"] or item.source_url` and never consults `meta["website"]`, so a
   conference with only a website renders unlinked.
6. "New" in the report stays `top_feed.is_entrant` — entered *this reader's*
   Top-25. Not corpus arrival.

**Validation**
```bash
uv run --project web/backend python web/backend/manage.py render_sample_report --kind personal
uv run --project web/backend python -m pytest web/backend/apps/content/tests -q -k "briefing or report or digest"
```

---

## Phase 12 — Nightly run

1. Replace `manual_all.scrape_opportunities()` (stage 1) with the collector.
   Keep its `-> bool` contract and non-fatal failure semantics.
   Note `test_reminders_prune_ordering.py:125-151` **reads `manual_all.py` as
   data** — it regexes out `CONTAINER_STAGES` and asserts order and the presence
   of `--no-prune`. Renaming a stage fails a *reminders* test.
2. Grants + conferences move **into the container** (pure HTTP). The Illinois
   fellowship scrape stays on the host (Playwright).
3. **Add the dblp registry stage** (D5a) — one SPARQL POST, cached to
   `data/collect/registry/`. It must run **before** resolve, since resolve joins
   against it and `assign_trust_tier` reads `dblp_found` / `indexed_years`.
   Refresh on a slow schedule (weekly is ample — venue longevity does not move
   daily), not on every nightly.
4. Wire `select_targets()` into the new stage — the "250 papers, 0 new"
   regression was exactly this omission.
5. Set `COLLECT_CONTACT` to a real address; it is read at **import time** and
   defaults to `research-collector@example.org`.
6. Prune raw payload runs (`RawStore.prune_runs(keep)`) — ~25 GB/year otherwise.

**Validation**: a full dry run of `manual_all.py` against the live database.
Acceptance: completes inside the existing ~10-minute envelope (systemd cap is 4 h),
every stage exits 0, and `run_analytics_report` shows non-zero discovery and
recommendation counts.

---

## Phase 13 — Full-system verification

1. Re-score **all 5 active users** (D4) plus labs and projects.
2. Verify end to end: feed → filters → hovers → report PDF → Discord DM.
3. Update `docs/repo-map.md`, `docs/architecture.md`, `docs/api-contract.md`,
   `docs/goals.md` (the "Built / Ingestion" paragraph names Pivot-RP), and
   `docs/research/OPEN_QUESTIONS.md` W10 — which claims rebuilding from open
   sources "loses Pivot conference CFPs, which have no open equivalent". **This
   work refutes that**; amend it rather than flipping a status.
4. `docs/changelog.md` entry per the global schema.
5. Delete this plan file.

---

## Exclusions

- **No knowledge-graph, Neo4j, or MinIO work.**
- **No change to ranking, fusion, thresholds, or the eval harness.** D2 keeps
  rankings out of ordering precisely so the relevance regression suite is
  untouched.
- **No widening of `ContentDeadline`'s unique key** (D1). Reminders on a specific
  non-next round remain unavailable; the hover shows every round.
- **No fellowship source change.**
- **No WikiCFP** (D5) — ~3.9 h per pull against the site's published crawl delay,
  for records that land in tier C and do not surface. Revisit if the dblp
  registry promotes enough of its venues to justify the pull cost.
- **No CORE registry adapter.** Its ranks already arrive via `ccf_deadlines`, and
  its `robots.txt` names AI crawlers by hostname.
- **No billing/entitlement model change.** D4's override is scoped to the
  migration re-scrape only.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Deleting `pivot/` 500s every content API (module-level import at `serializers.py:5`) | Phase 2 lifts it before Phase 6 deletes anything |
| Fellowship eligibility gating silently stops | `metadata["constraints"]` block preserved byte-for-byte; its tests move with it |
| A multi-round grant is deleted at its first round, CASCADEing a paid-for LLM verdict | Phase 3's `prune_after = max(rounds)` |
| Nothing ever expires (conference `event_start` is NULL on 100% of rows) | Phase 3's conference rule keys on the last deadline |
| `prune_expired` silently skips new sources | Phase 4 drops the `source__in` allow-list |
| Non-zero-padded dates never expire (lexicographic compare) | Phase 4 emits strict ISO; asserted in tests |
| Every reader's whole slate reads "new" on the first run | Expected (A4); communicated, not suppressed |
| ~~The backfill is ~5–6 h~~ **RESOLVED: it is ~41 minutes** (`EXP-2026-08-007`: 1.798 rec/s at 16 workers, 3.1 % refusal) | The old figure came from the collector's table for a *different* endpoint. Still run once, outside the nightly, with per-record checkpointing so an interrupted run resumes |
| **A model outage during the backfill silently degrades the corpus to raw-text embeddings** | `metadata["search_text_source"]` records each record's basis, so the damage is queryable and re-runnable rather than invisible. `model_failed` stays **retryable**, never settled — the collector once wrote 321 `model_failed` rows in one over-concurrent run, and treating those as answers would have excluded 321 records permanently |
| **Extraction changes the embedding basis, so relevance moves** | Not a regression to hide. `search_text_source` keeps the two bases separable, and per `CLAUDE.md` any relevance claim is an experiment under `docs/research/experiments/`, never a number asserted in chat |
| **A verified-looking summary that nobody checked is worse than none** | Refusal is a first-class outcome: refused records show no AI summary and say so. `docs/purpose.md`'s trust rule — never hide uncertainty |
| ICML/KDD 2026 store an abstract-registration date as `submission` | `quality_warnings` is the only signal — surfaced in the UI (Phase 10) |
| `extract_fellowship_constraints` iterates an always-empty queryset (filters `source=PIVOT_SOURCE`, but fellowships are `illinois-fellowship-finder`) | Pre-existing latent bug; fix while relocating in Phase 2 |
| Compose run from the worktree creates empty volumes | Always `cd /home/bdgr/Agents/Mycelium` or pass `-p mycelium` |
| The worktree has no `.env`, so `manage.py` silently falls back to SQLite | Always pass `DATABASE_URL` explicitly |
