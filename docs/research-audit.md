# Mycelium — Research Audit

**Repository:** `/home/bdgr/Agents/Mycelium` · **Audited:** 3 August 2026 · **Commit:** `e8c95a2`
**Scope:** ~113,400 lines of first-party code (Python, TypeScript, Astro), 426 commits over 9 weeks (31 May – 2 Aug 2026).
**Inferred inputs:** `PROJECT_NAME` = Mycelium (stated in README). `DOMAIN_HINT` = scholarly information access / research-lab operations (inferred from code; no domain was supplied). `TARGET_HORIZON` = ~12 months, workshop or conference (user-supplied).

> **This document is a dated snapshot, not a live tracker.** It was written on
> 3 August 2026 and is not updated as work lands — read it for the reasoning,
> not for current status. The parts of it that must stay current were moved into
> [`research/`](research/) and are maintained there:
>
> | Audit section | Now tracked in |
> |---|---|
> | §1.6 implicit claims C1–C7 | [`research/CLAIMS.md`](research/CLAIMS.md) — same IDs, plus evidence and status |
> | §6.5 workstreams W0–W12 | [`research/OPEN_QUESTIONS.md`](research/OPEN_QUESTIONS.md) — same IDs, plus what is done |
> | §3 closest prior work, §9 bibliography | [`research/RELATED_WORK.md`](research/RELATED_WORK.md) — the works that bear on a claim, plus a scoop watch |
> | §7 reshaping paths, §8 venue strategy | Kept privately, outside this repository |
>
> W2 — the audit's "cheapest decisive next action" — has since been run. Its
> falsifier fired; see
> [`EXP-2026-08-001`](research/experiments/EXP-2026-08-001-longeval-retrieval-baseline/RESULTS.md).
>
> W10 has since been done for grants and conferences, and **this document's
> stated cost for it was wrong**: the corpus was rebuilt from public sources
> without losing conference CFPs, which the audit believed had no open
> equivalent (§6.5, risk row #4, §1.5). Six public conference sources now feed
> it. The reasoning below is left as written; the correction is the W10
> amendment in
> [`research/OPEN_QUESTIONS.md`](research/OPEN_QUESTIONS.md).

---

## 0. Executive Summary

**What it is.** Mycelium is a deployed, single-tenant *lab intelligence platform*: a Django/Next.js system that ingests hundreds to low thousands of new papers per run from OpenAlex, PubMed, and Semantic Scholar; scrapes grant, fellowship, and conference-CFP records from ProQuest Pivot-RP and the Illinois Fellowship Finder behind institutional SSO; embeds everything with a 384-dimensional general-purpose sentence encoder; retrieves candidates per declared research interest by cosine similarity; reorders them with BM25 and Reciprocal Rank Fusion; and hands the top ten to a large language model that writes a prose rationale and a 0–100 "match %". It delivers the result as a daily digest through a web app and a Discord bot, and routes each item to the lab member it appears most relevant to.

It is genuinely built. 1,379 tests, 55 migrations, systemd-scheduled production runs, a durable Discord outbox, a Playwright scraper that survives a Blazor SignalR handshake. The engineering discipline is well above the norm for a research repository.

**Novelty verdict — blunt.** *Mycelium is not currently a research contribution. It is a well-engineered product with no research claim, no measurement, and no baseline, whose paper-recommendation half is substantially anticipated by a system that was published with an evaluation and a public 800,000-rating dataset (Scholar Inbox, ACL 2025 System Demonstrations [B1]).* Every mechanism in the ranking stack is standard or below standard practice: RRF is Cormack et al. 2009 [B2]; one-vector-per-interest retrieval with cross-interest fusion is the MIND/ComiRec multi-interest pattern [B3, B4]; LLM reranking of a top-*k* set is RankGPT [B5]; hard-eligibility-then-soft-relevance is constraint-based recommendation with a cascading strategy [B6], solved far more rigorously in clinical-trial matching [B7, B8]. The "multi-agent" framing in the code and changelog does not survive contact with the source: there is no planner, no tool use, no loop, no reflection, and no framework — five prompt strings fanned out and concatenated once. Three 2025–2026 papers find that multi-agent LLM scaffolds do not beat well-prompted single agents — [B10] at matched thinking-token budgets, [B11] at up to 10× the cost, [B9] attributing the shortfall to system design rather than model capability. Claiming that framing would be scooped *against*.

**Where the real opportunity is.** Two things in this repository sit in genuinely thin literature. First, **funding-opportunity recommendation**: two independent sources call grant recommendation the least-studied scholarly recommender task [B12, B39], there is no shared benchmark, no leaderboard, and the commercial systems (Pivot-RP, Dimensions, GrantForward) have published nothing. Second, **lab-level rather than individual-level scholarly recommendation, with routing to team members** — a good-faith search found no active academic group working on it, and the reviewer-assignment literature that is closest to it has never been applied to this direction. Both are real gaps. Neither is claimed by this project yet, because the project makes no claims at all.

**Readiness — verbatim line for extraction:**

> **Readiness: L1 — near from demo track, far from applied conference and far from top-tier archival; blocked by claim clarity, evaluation rigor, baseline coverage, and positioning (all scored 0/4); critical path 10–16 weeks to a credible applied/workshop submission; cheapest next action: run the existing retrieval stack on the openly-downloadable LongEval-Sci 2026 collection against its published BM25 and Qwen3-Embedding-4B baselines (~1 week).**

**Recommended action.** Stop adding product features. Spend one week producing a number — any number — against an external baseline. Neither of the framings the audit weighed requires writing more of the system — only measuring it.

---

## 1. Project Characterization

### 1.1 Identity

**Name.** Mycelium. Internal codenames found in the repository: **Mylo** (the LLM persona and the Discord bot — `mylo/`, `mylo-bot.service`, `_SYSTEM_PROMPT = "You are Mylo, a research scout..."` at `content/suggest.py:55`), and **pivot** (the ProQuest scraping subsystem — `pivot.py`, `scraper/pivot/`).

**One sentence, non-specialist.** Mycelium watches the flood of new scientific papers, grants, fellowships, and conference calls, decides which ones a particular research lab and its individual members should care about, and delivers a short daily briefing explaining why.

**One paragraph, technical peer in an adjacent field.** Mycelium is a content-based, cold-start-only recommender over a continuously refreshed corpus of scholarly and funding artifacts. A researcher, lab, or project is represented as a set of short declared "research interests," optionally grouped into 2–6 LLM-composed *clusters* (a cluster is a named theme grouping several interests — e.g. "AI for threat intelligence" covering three related interest strings). Each interest is embedded independently, so a user is a small bag of vectors rather than one. Retrieval is exact cosine over a pgvector column, per interest; BM25 rescores the retrieved pool; the two rankings are fused by Reciprocal Rank Fusion (RRF — a rank-only fusion method that scores a document Σ 1/(k+rank) across the lists it appears in, deliberately discarding raw scores so no channel's scale dominates); per-interest scores are min-max normalized and combined across interests by a hand-derived "softened CombMNZ." Items are *admitted* to the feed by an absolute cosine threshold — a different quantity from the one used to rank them — and the top ten are passed to an LLM that emits a prose rationale and an integer match percentage, which becomes both the user-visible score and the final ranking key. A parallel deterministic rule engine gates fellowships on hard eligibility before relevance scoring. Delivery is a daily digest via web app, PDF, and Discord.

### 1.2 The problem

**Stated as a problem.** A research lab cannot read everything. Hundreds to low thousands of relevant-ish papers per run appear across three preprint and indexing services for even a narrow watch list; funding calls, fellowships, and conference CFPs arrive on independent schedules through incompatible portals with hard eligibility rules and hard deadlines. The cost of missing a fellowship deadline is asymmetric and irreversible. Meanwhile the *lab* — not the individual — is the unit that holds the goals, but every existing tool personalizes to an individual account.

**Who has it.** Principal investigators running groups of 3–20; graduate students who do not know which fellowships they are eligible for; research administrators. Existing tools fail them in specific ways worth naming: Google Scholar alerts are keyword-triggered and produce no ranking or explanation; Semantic Scholar Research Feeds and Scholar Inbox personalize to an individual and cover papers only; Pivot-RP covers funding but is a search portal, not a push feed, and its relevance model is unpublished and unevaluated; nothing covers papers *and* funding *and* CFPs in one profile, and nothing recommends to a group.

**Why it is hard.** Five distinct difficulties, and they are not equally hard:
1. **Profile sparsity.** A user is described by a handful of short interest strings. There is no interaction history to learn from. This is the cold-start regime, permanently.
2. **Query–document mismatch.** A watch topic ("agentic knowledge graphs") is a 3-word query; a paper is a 200-word abstract. Document-centric embeddings are trained on document–document similarity, and the granularity/focus/training-signal mismatch with short question-style queries is a named problem [B16].
3. **Heterogeneous relevance.** "Relevant paper" and "fellowship I can actually win" are different predicates. The second has *hard constraints* (citizenship, career stage, institution) that no amount of topical similarity can override.
4. **Group vs. individual.** A lab's interests are a union, not an average. Naive aggregation lets the theme with the densest literature eat the whole feed.
5. **Evaluation.** There is no ground truth for "should this researcher have read this paper," and constructing one requires either user labels or a proxy.

**Is the problem well-posed?** Mostly, with one exception worth flagging. Difficulties 1, 3, 4 are well-posed and are the interesting ones. Difficulty 2 is well-posed and already actively worked on. Difficulty 5 is well-posed and is where the project's value would be created. But the *product* framing — "a living AI profile for a research lab" (`docs/purpose.md:15`) — is not a research problem; it dissolves on inspection into the five above plus a large amount of UI. ⚠️ The gap between the repository's stated purpose and its extractable research problem is the single largest reason this project currently reads as a startup rather than a thesis chapter.

### 1.3 The solution

#### Core mechanism

Reconstructible from this description: **Represent a user as N independent interest vectors. For each, retrieve the top 100 items by exact cosine over a pgvector column. Union the pools. Build a BM25 index over the union only, and rank each interest's query text against it. For each interest, fuse the BM25 ranking and that interest's vector ranking by RRF at k=60, min-max normalize within the interest, and drop anything below 0.15. Combine across interests as `mean(scores) × (1 + 0.15·(n_matched − 1))`. Separately track, for each item, the maximum raw cosine it earned in any interest. Admit to the feed every item whose max raw cosine ≥ 0.5 (papers) or 0.4 (opportunities), ordered by the combined score. Send the top 10 to an LLM with the profile text; take its integer match percentage as the display score and the final sort key; hide anything it scores below 60. Everything below rank 10 gets a template rationale and no percentage.**

#### Architecture

```mermaid
flowchart TB
  subgraph Ingest["Ingestion (host, systemd mylo-daily.timer)"]
    A1[OpenAlex / PubMed / Semantic Scholar<br/>asyncio, TCPConnector limit=32] --> A2[Deduplicator<br/>DOI/PMID/PMCID/arXiv cascade<br/>+ normalized title|author|year]
    A3[Pivot-RP + Illinois Fellowship Finder<br/>Playwright + SSO + Blazor SignalR] --> A2
    A2 --> A4[fastembed BGE-small-en-v1.5<br/>384-dim, L2-normalized, ONNX]
    A4 --> A5[(Postgres + pgvector<br/>ContentItem.embedding<br/>NO ANN index)]
  end
  subgraph Match["Matching (Django, per MatchTarget)"]
    B1[Profile: N interest strings<br/>→ N vectors] --> B2[Per-interest cosine top-100]
    A5 --> B2
    B2 --> B3[BM25 over retrieved pool ONLY]
    B3 --> B4[RRF k=60 per interest<br/>min-max, floor 0.15]
    B4 --> B5["Softened CombMNZ<br/>mean × (1+0.15·(n−1))<br/>cluster-scoped if ≥2 clusters"]
    B2 -.max raw cosine.-> B6{Threshold gate<br/>≥0.5 papers / 0.4 opps}
    B5 --> B6
    B6 --> B7[Top 10 → LLM]
    B6 --> B8[Rank 11+ → template reason<br/>match_percent = None]
  end
  subgraph LLM["LLM layer (vLLM, OpenAI-compatible)"]
    B7 --> C1[suggest.py: match % + reason<br/>free-text JSON, brace-scraped]
    C1 --> C2[Floor at 60%, re-sort by %]
    C2 --> C3[member_fit.py: cosine top-3<br/>+ remove-only LLM veto]
    C3 --> C4[briefing_agents.py:<br/>4 section prompts → 1 summary prompt]
  end
  C4 --> D1[Web app / PDF / Discord outbox]
  B8 --> C2
```

Component responsibilities and where state lives:

| Component | Path | Responsibility | State |
|---|---|---|---|
| Scraper | `web/backend/apps/scraper/` | Fetch, parse, dedupe, embed, upsert | `ContentItem` rows |
| Pivot subsystem | `scraper/pivot/` | Playwright/SSO scraping of Pivot-RP + Illinois | `data/pivot/*.json`, then `ContentItem` |
| Retrieval + fusion | `content/retrieval.py`, `lexical.py`, `fusion.py` | Candidate generation and ranking | Stateless |
| Match orchestration | `content/pipeline.py`, `opportunities.py` | Per-target run, thresholding, persistence | `RelevanceScore` rows |
| LLM layer | `core/llm.py`, `content/suggest.py`, `opportunity_llm.py`, `member_fit.py`, `briefing_agents.py` | Rationale + score generation | `RelevanceScore.signals` JSON |
| Eligibility engine | `content/fellowships.py` | Deterministic hard gating | Stateless |
| Team profile | `content/team_profile.py` | Engagement-weighted project vector | `research.Project.embedding` |
| Delivery | `content/briefing.py`, `daily_report_pdf.py`, `integrations/` | Digest assembly, Discord outbox | `data/outbox/`, outbox table |

Control flow is a straight line with no loops. The daily production run is **not** on Celery — `config/settings.py:244-250` explains that it was moved to the host via `ops/nightly/manual_all.py` under `mylo-daily.timer` because the Pivot scrape needs host-only Playwright. Celery beat retains four secondary jobs.

#### Key design decisions and the alternatives available

| Decision | What was chosen | Alternative available | Evidence of reasoning |
|---|---|---|---|
| Ranking vs. admission | Rank on normalized fused score, **gate on raw cosine** — two different quantities | Threshold the fused score | Explicit and correct: only an absolute similarity is calibrated enough to serve as a threshold — stated at `fanout.py:7-8` and `member_fit.py:166-168`; the per-interest normalization rationale itself at `fusion.py:9-11`. **This is the best-reasoned decision in the codebase.** |
| Feed length | Variable — everything above threshold, capped at 250 | Fixed top-K | `pipeline.py:919-924`, `opportunities.py:87-90` |
| Cross-interest fusion | `mean × (1 + β(n−1))`, β=0.15 | Sum (CombMNZ), max, learned | `fusion.py:19-23`: mean so one weak match doesn't drag down a strong multi-match; linear breadth bonus instead of raw CombMNZ multiply. β self-labelled "a placeholder pending tuning" (`fusion.py:52-53`) |
| Cluster scoping | CombMNZ within cluster, **max** across clusters | Global ranking | `fusion.py:150-153`: prevents a paper matching one interest in each of three clusters from out-breadthing a strong single-cluster match |
| BM25 scope | Index only the vector-retrieved pool | Independent lexical retrieval | `lexical.py:8-12` justifies it by "targeted, bounded ingestion." ⚠️ Consequence: lexical recall ⊆ vector recall. It is not a second retrieval channel. |
| LLM coverage | Top 10 only; carry-forward freezes verdicts permanently | Sliding-window listwise over the full list | `opportunity_llm.py:88-118`; cost amortization with a stated UX rationale |
| Percent semantics | Refuse to fabricate a percent for un-LLM'd items (`match_percent=None`) | Scale the fusion score | `suggest.py:193-197`, `369-380`. Epistemically honest; also means ~92% of the feed shows no score |
| Member veto | LLM may remove from the cosine shortlist, never add | Let the LLM propose members | `member_fit.py:394-399`, enforced by index-bounded parsing at `:287-293`, not by prompt |

#### What differs from the obvious baseline

Honestly assessed: **at the mechanism level, almost nothing.** The obvious baseline — embed the user's interests, cosine-retrieve, show the top 20 — is 80% of this system's behaviour. The genuine deltas are:

1. Gating on a calibrated quantity while ranking on an uncalibrated one (a real and non-obvious separation).
2. Cluster-scoped max-pooling, which addresses a specific, correctly diagnosed failure mode of multi-interest fusion for broad-profile targets.
3. Hard eligibility gating before relevance for fellowships.
4. Item→member routing with a monotone (remove-only) LLM veto.

Items 1 and 2 are ideas. Items 3 and 4 are architectural patterns that exist elsewhere under other names (constraint-based recommendation [B6]; reviewer assignment [B15, B17]). None has been measured.

### 1.4 How the mechanism addresses each difficulty

| Difficulty (§1.2) | Component intended to address it | Does the repository's evidence support it? |
|---|---|---|
| 1. Profile sparsity / cold start | Content-based retrieval from declared interests; the "generalise up" cluster prompt that abstracts résumé-level specifics into searchable topics | **Partially.** The generalise-up instruction (`accounts/intake/clusters.py:74-81`) documents a real, diagnosed failure (over-narrow topics starved retrieval). But there is no mechanism to ever *acquire* a preference signal: **no personal engagement is logged at all.** Every `record_event` call site passes a real project (`research/views.py:739,760,892`; `content/collaboration.py:123`; `content/views.py:1437`, whose `MemberSuggestion.project` FK is non-nullable at `content/models.py:647-651`), and the personal save/dismiss endpoints (`content/views.py:933,1095`) never call it. The nullable `project` column is dead capacity, and `team_profile.py` — the only consumer — writes solely to `research.Project.embedding`. ⚠️ `content/models.py:471-475` describes `RelevanceEvent` as "the ground-truth stream a future team-relevance recompute (and the evaluation harness) will read." No evaluation harness exists, and for personal targets no stream exists either. |
| 2. Query–document mismatch | Per-interest embedding; BM25 rescoring | **Not established.** No measurement. The literature says the mismatch is real and named [B16], and that BM25 alone trails dense retrieval by 24.8 points Recall@5 on realistic literature-search queries [B18] — but here BM25 cannot add recall at all. |
| 3. Heterogeneous relevance / hard constraints | `fellowships.py` deterministic eligibility engine, then 0.65·cosine + 0.35·rule blend | **Architecturally yes, empirically no.** The cascade is the right shape [B6]. But the rule vocabulary is hardcoded to the Illinois Fellowship Finder's facet strings with a 4-entry career-stage map, there is no relaxation path when the feasible set empties, and no per-criterion provenance — both of which the clinical-trial analogues treat as required [B7, B8]. |
| 4. Group vs. individual | Cluster-scoped fusion, per-theme slates, `member_fit.py` | **The most interesting and least evidenced part.** The per-theme slate (`pipeline.py:504-522`) correctly diagnoses that one theme's vocabulary can monopolize a lab feed. Nothing measures whether it works. |
| 5. Evaluation | — | **Nothing.** See §1.5. |

### 1.5 Current state

#### Maturity and honesty audit

| Component | Status | Evidence |
|---|---|---|
| Multi-source paper ingest (OpenAlex/PubMed/S2) | **Implemented and exercised** | 30 production logs, `data/logs/daily-suggestions/`; `20260720T180617Z-cli.log`: 723 raw → 560 unique → 313 new → 313 embedded in 24.5 s |
| Cross-source deduplication | **Implemented and exercised** | `sources/dedup.py`; ~23% collapse rate on live data (723→560) |
| fastembed embedding (BGE-small, 384-d) | **Implemented and exercised** | `scraper/embedding.py`; 66 MB ONNX model on disk at `models/fastembed/` |
| pgvector cosine retrieval | **Implemented and exercised** | `content/retrieval.py:58-60`, `CosineDistance` |
| ⚠️ ANN index (HNSW/IVFFlat) | **Aspirational** | Docstrings at `search.py:20,225`, `pipeline.py:77` call it "ANN." Grep for `hnsw\|ivfflat\|vector_cosine_ops` across all Python returns **zero hits**. Every vector query is an exact sequential scan. |
| BM25 + RRF fusion | **Implemented and exercised** | `lexical.py`, `fusion.py`; degrades to vector-only if `rank_bm25` absent |
| ⚠️ "Hybrid retrieval" (as two recall channels) | **Overstated** | `pipeline.py:978` builds the BM25 index over the vector-retrieved pool. Lexical recall ⊆ vector recall. |
| Cluster-scoped fusion, per-theme slates | **Implemented and exercised** | `fusion.py:165-245`, `pipeline.py:1053-1068` |
| Pivot-RP / Illinois scraping | **Implemented and exercised** | `data/pivot/`: 2,989 conference records (5.0 MB), 946 fellowships (2.6 MB), real scraped text |
| Fellowship eligibility rule engine | **Implemented and exercised** | `fellowships.py:43-64`; vendored from a prior tool (`fellowships.py:3-4`) |
| LLM rationale + match % | **Implemented and exercised, at ~8% coverage** | `suggest.py`, `opportunity_llm.py`. Aggregated across all 30 production logs excluding the loadtest day: **433 LLM-scored vs. 4,818 fallback = 8.2%**. Range per run 0–100%; nine runs are `0 llm`. Typical line: `[brendondgr] suggestions: 116 (10 llm / 106 fallback)` |
| Member fit routing | **Implemented and exercised** | `member_fit.py` |
| Discord bot + durable outbox | **Implemented and exercised** | `mylo/`, `integrations/services/outbox.py`, boundary enforced by `test_import_graph.py` |
| Billing, admin, auth, onboarding | **Implemented and exercised** | 8 Django apps, 55 migrations |
| ⚠️ "Multi-agent" briefing writer | **Overstated** | `briefing_agents.py:1` says "Multi-agent daily-report writer." It is 5 prompt strings, a `for` loop over 4 categories, and one string concatenation into a summary prompt (`briefing_agents.py:172-193`, `481-484`). No planner, no tool use, no loop, no reflection, no framework. `pyproject.toml` contains no agent library; the first week of git history includes "Remove LangGraph compatibility aliases." |
| ⚠️ "ReAct loop" / planner | **Aspirational** | Described in `docs/changelog.md:52`; `docs/architecture.md:91` lists `planner` under *planned*. Grep for `ReAct` in code: zero hits. `accounts/intake/agent.py` is a deterministic 4-question form state machine whose own docstring says "the form flow needs no LLM." |
| ⚠️ Knowledge graph / Neo4j | **Aspirational** | README:1-6 describes a "**planned** lab intelligence platform" that is "**meant to**… maintain a living knowledge graph of people, projects, claims, opportunities." `neo4j>=5.28.0` is installed; `NEO4J_URI/USERNAME/PASSWORD` settings exist; the container runs in `compose.yaml:291`. **Grep for `GraphDatabase\|from neo4j\|import neo4j\|MERGE (\|MATCH (` across all Python: zero hits.** The project's own `docs/goals.md:140` has `- [ ] Choose and implement a graph approach` unchecked. There is no graph. |
| ⚠️ S3 / MinIO object storage | **Implemented but unexercised** (infra only) | Container + 4 settings; zero `boto3`/`django-storages`. PDFs go to the local filesystem. |
| ⚠️ Cytoscape.js graph visualization | **Aspirational** | README:12, under a heading literally titled "## Planned Stack"; absent from frontend source |
| ⚠️ Grants.gov / NIH RePORTER / NSF retrievers | **Implemented but unexercised** | `ops/scrapers/grants/` (527 lines) has working API clients for `api.grants.gov/v1/api/search2`, `api.reporter.nih.gov/v2/projects/search`, `api.nsf.gov/services/v1/awards.json`. Grep for any import outside `ops/scrapers/grants/`: **zero**. Output is three 10-row sample CSVs. **These are exactly the three APIs that W7 and Path A require to build award-linkage ground truth — the client layer already exists. This is the repository's most reusable dormant asset, not dead code.** |
| Structured LLM output enforcement | **Absent** | No `response_format`, no JSON schema, no guided decoding. JSON is extracted by `raw.find("{")` … `raw.rfind("}")` + `json.loads` (`suggest.py:323-329`, duplicated at `opportunity_llm.py:458-464`). Retries deliberately disabled (`core/llm.py:108-111`). |
| Cost / token accounting | **Absent** | `LLMResponse.usage` is parsed at `core/llm.py:361` and read by nothing. **Worth fixing in W1:** per-item token cost is precisely the number the W6 ablations need, and the matched-compute framing that decides the multi-agent argument [B10, B11] is unanswerable without it. |
| Feedback learning loop | **Stubbed** | Events logged with weights; only consumer is `team_profile.py`, filtered to `project=project`. Personal engagement is unreachable. A user can dismiss every item and the next digest is identical. |
| **Evaluation of output quality** | **Absent** | See below |

#### The evaluation situation

This is the decisive finding and it deserves its own statement. Using the three-tier distinction:

- **Tier (a) — correctness tests ("does the code run"): excellent.** 1,379 `def test_` functions (verified by direct grep) across 147 files. Every external seam is injectable, so the suite runs fully offline. `content` alone has 582 tests.
- **Tier (b) — evaluation ("is the output good"): zero.** A grep across all `.py` for `ndcg|mrr@|precision@|recall@|ground.?truth|qrel|ablation` returns exactly one hit, and it is the aspirational docstring at `content/models.py:474`. There is no relevance-judgment set, no labeled pair, no held-out set, no IR metric, no human rating, no eval script, no `evals/` directory, no golden output.
- **Tier (c) — comparative evaluation ("is it better than an alternative"): zero.** No baseline exists. No BM25-only vs. hybrid, no embedding-only vs. LLM-reranked, no cluster vs. no-cluster comparison. ⚠️ The `_force_fallback` seam (`pipeline.py:149-155`) *creates* a natural A/B — the deterministic path is a baseline sitting in the code — but it exists solely as a billing-tier gate (`pipeline.py:763-774`) and no run ever compares the arms.

The closest thing to an evaluation test is `test_llm_report_is_grounded_sectioned_and_counts_are_correct` (`test_daily_briefing.py:81`). It asserts that the paper title appears **in the prompt** (`:112-118`), with a fake `complete` returning a fixed string. That is a correctness test of prompt assembly, not a measurement of grounding.

Every tuning constant is a self-declared placeholder. `fusion.py:29-30`: "β and the floor are placeholders pending engagement/relevance data." `settings.py:425-430` on `HIGH_SIGNAL_FLOOR`: "a PLACEHOLDER pending shadow-mode calibration… do NOT trust the default 90 until it is measured." The candour is genuine and to the project's credit. It is also the point: **this codebase has been rigorously tested for whether it runs and never once tested for whether it works.**

The one thing measured is throughput. `ops/loadtest/loadtest.py` (972 lines) + `docs/loadtest.md` report latency p95 and LLM-vs-fallback *counts*. `data/loadtest/` contains two files of ~980 bytes each; both runs were `INTERRUPTED by user (KeyboardInterrupt)` and neither produced a report.

#### Scale — what this has actually been run on

The production logs are unambiguous.

```
2026-06-30  daily run start: 2 user(s)
2026-07-06  daily run start: 3 user(s)
2026-07-10  daily opportunities start: 383 user(s)   ← loadtest residue
2026-07-12  daily run start: 2 user(s), 1 lab(s), 1 project(s)
2026-07-20  ingest: 11 unique term(s) across 2 user(s)
```

Every non-synthetic identifier appearing in any log: `brendondgr`, `bdgr`, `nicoler`, `pulse-lab`, plus three test artifacts. **That is the developer, a second account for the developer, one other person, and one lab.** The 383-user spike is loadtest residue, and on that day the fellowship path returned `error (0 scored, 0 new)` for essentially every synthetic user.

Corpus scale is the one axis where the project has a genuine asset, and the README undersells it. Across the 26 non-loadtest logged runs, new papers ingested and embedded per run ranges **0 to 3,452, median ~870** (the 313 in `20260720T180617Z-cli.log` is a low day); a full run of 723 raw → 560 unique → 313 new completes in 25 seconds from 11 watch terms. 946 fellowships and 2,989 conference records sit on disk. Per-run candidate pools range **100–375** items.

**What would break first at 100×.** Not throughput — the exact cosine scan. With no ANN index, `retrieve_for_vector` is O(corpus) per interest per target. At 2 users × ~5 interests over ~30k items this is invisible; at 200 users × 5 interests over 3M items it is the whole runtime. Second failure: `ContentItem.embedding` is declared `VectorField(null=True, blank=True)` with **no `dimensions=`** (`content/models.py:56`), so the column accepts any width — an encoder swap silently produces a mixed-dimension table that errors at query time, and no HNSW index can be added without a migration.

#### Reproducibility

A third party **cannot** currently reproduce this end to end, though the packaging hygiene is good. Blockers: (i) `LLM_MODEL` defaults to the empty string (`settings.py:314`) and `complete()` raises `LLMConfigurationError` when unset (`core/llm.py:310-313`) — the system's most important component has no recorded identity, so its behaviour is unpinned and a contamination check cannot be run; (ii) `LLM_TEMPERATURE` defaults to 0.2 (`settings.py:325`), so the scoring layer is nondeterministic run-to-run *even after* the model is pinned — pinning is necessary but not sufficient; (iii) Pivot-RP requires institutional SSO credentials to a commercial Clarivate product; (iv) the Illinois Fellowship Finder scrape requires host-side Playwright/Chromium; (v) no seeds are set in the pipeline (`ops/loadtest/loadtest.py` does seed at 1337, but nothing in the matching path does). What *is* present and good: `uv.lock` (192 KB, pinned), Docker Compose for the full stack, a documented README, 1,379 offline-runnable tests, and `seed_demo.py` for synthetic users.

### 1.6 Implicit research claims

These are derived from what the code does, not what the documentation asserts. They are the units searched against the literature in §2–§4.

| # | Claim (falsifiable form) | Evidence in repo | Evidence that would establish it |
|---|---|---|---|
| **C1** | Fusing a BM25 rescoring of the vector-retrieved pool with the vector ranking via RRF (k=60) orders a paper feed better than vector retrieval alone, for a user described by 2–6 short declared interests. | None. ⚠️ Note the claim is weaker than it appears: `build_bm25_index(list(pool.values()))` at `pipeline.py:978` indexes only what vector retrieval already found, so this is a reordering claim, not a recall claim. | nDCG@10 / Recall@20 on a scholarly collection with qrels, hybrid vs. vector-only vs. BM25-only. LongEval-Sci 2026 ships BM25 and Qwen3-Embedding-4B baselines and is downloadable now. |
| **C2** | Rewarding breadth across a user's declared interests — `mean × (1 + 0.15·(n−1))` — produces more useful recommendations than ranking by the single best-matching interest. | One synthetic 2-document unit test confirming the arithmetic (`test_pipeline.py:187`). | Ablation over β ∈ {0, 0.15, 0.3, …} plus a max-pooling arm, on relevance judgments from multi-interest users. |
| **C3** | For a lab or broad-interest user, ranking within research clusters and max-pooling across them prevents one vocabulary-dominant theme from monopolizing the feed, relative to global ranking. | None. This is the most distinctive idea in the codebase. | Per-theme coverage/recall metrics on lab profiles, cluster-scoped vs. flat, with a diversity or per-aspect-recall measure alongside nDCG. |
| **C4** | An LLM given a researcher's profile and 10 candidates can assign a 0–100 relevance score that orders them better than the fusion score does, **and** the emitted integer is meaningful as a match percentage. | None. | Two separate experiments — a ranking-quality comparison (fusion order vs. LLM order against judgments), and a calibration check (does 80% mean 80%?). The literature already says the first is plausible [B19] and the second is not [B20]. |
| **C5** | Gating fellowships on deterministic eligibility before relevance scoring, then blending 0.65·cosine + 0.35·rule-fit, surfaces fellowships a researcher can actually win better than relevance ranking alone. | None. | Graded judgments in the TREC-CDS style (eligible=2, ineligible-but-relevant=1, irrelevant=0) [B21] on a labeled fellowship sample; ablate the gate and each rule weight. |
| **C6** | Cosine between an item embedding and a lab member's profile embedding (floor 0.35, top 3) identifies the member for whom an item is most relevant, and an LLM constrained to remove-only cannot degrade it. | None. | The RAP gold-standard protocol [B15]: self-reported expertise scores from lab members, misranking rate, plus a TF-IDF baseline (which beat GPT-4o mini 79.5% vs 51.5% at this task [B17]). |
| **C7** | Admitting every item above an absolute cosine threshold, rather than a fixed top-K, yields a more honest and more useful feed. | None. ⚠️ Unusual: no benchmark in this field thresholds on raw cosine, because cosine magnitudes are not calibrated across queries. | Precision/recall at varying thresholds vs. varying K, plus a user-facing measure of whether variable length is preferred. |

**None of the seven has any evidence.** Three (C3, C5, C6) touch genuinely thin literature. Four (C1, C2, C4, C7) are in areas where the answer is either known or the method is standard.

---

## 2. Research Landscape

### 2.1 Decomposition into research areas

| Level | Area | Maturity | Consequence for this project |
|---|---|---|---|
| Core method | Scholarly / scientific paper recommendation | **Mature** (3 surveys, 200+ → 500+ papers) [B12, B22, B23] | Contributing requires beating strong, tuned baselines |
| Core method | Hybrid sparse+dense retrieval and rank fusion | **Mature** (RRF is 2009) [B2] | Nothing to contribute; RRF at k=60 is the most defensible constant in the system |
| Core method | LLM reranking / LLM-as-judge | **Very active, contested** [B5, B19, B20, B24] | Fast-moving; a systems paper here dates in months |
| Core method | Multi-interest / multi-vector user modeling | **Mature** (MIND 2019, ComiRec 2020) [B3, B4] | The architecture has a name; the delta is that interests are *declared*, not learned |
| Core method | Constraint-based recommendation (hard + soft) | **Mature but quiet** [B6] | The cascade is textbook; the *graded ineligibility* refinement is where the room is |
| Core method | Expert finding / reviewer assignment | **Mature, 30 years** [B15, B17, B25] | Closest published analogue to member-fit; has gold standards and metrics |
| Application | Research-lab operations / scholarly infrastructure | **Emerging** | Must justify that the problem matters at all |
| Application | Research funding / fellowship discovery | **Nearly empty** [B12, B39] | ~6 substantive papers in a decade, no benchmark, no shared task |
| **Intersection** | **Eligibility-constrained funding recommendation with graded ineligibility and deadline-aware ranking** | **Open** | Strongest available novelty claim |
| **Intersection** | **Team/lab-level scholarly recommendation with routing to individual members** | **Open** | Second-strongest; no active group found |
| Intersection | Agentic LLM literature monitoring | **Crowded and contested** | Avoid. Three papers say the multi-agent framing is wrong [B9, B10, B11]; one says LLMs underperform keyword retrieval on this exact task [B26] |

### 2.2 Area syntheses

**Scholarly paper recommendation.** *What it is:* recommending research articles to a researcher, either from a query paper (paper-to-paper) or from a user profile (user-to-paper). *Structure:* content-based (embed and match), collaborative (learn from other users' interactions), citation/graph-based, and hybrid. *Frontier:* the field's most current survey covers Nov 2021 – Dec 2024 [B23]; the reference deployed system is Scholar Inbox [B1], which trains a **per-user binary classifier** over GTE embeddings across 3M+ papers, mixes easy random negatives with hard negatives drawn from papers the system itself surfaced, attacks cold start with a science map plus **active learning that prompts users to rate papers**, and released **800,000 user ratings** publicly. *How it evaluates itself:* nDCG@k, MRR, Recall@k, P@k over ranked lists, on SciDocs [B27], SciRepEval [B28], RELISH, CSFCube [B29], DORIS-MAE [B30], LitSearch [B18]. *Open problems, as the field states them:* cold start is named an open challenge in both [B22] and [B23]; both also name evaluation methodology. Beel & Langer [B31] found offline results "sometimes contradict results from online evaluations and user studies," concluding offline evaluation is "probably not suitable" in this domain — which does not excuse having none, but means the plan must be offline sanity checks *plus* a user signal.

**Recommender-system evaluation.** *The frontier is a critique.* Ferrari Dacrema et al. [B32] found only ~7 of 18 neural methods reproducible and most beaten by properly tuned simple baselines — the operative lesson being that *an untuned baseline is not a baseline*. Hidasi & Czapp [B33] catalogue four widespread offline-evaluation flaws, temporal leakage foremost. The 2024 Dagstuhl best-practices document [B34] is a usable rubric. A 2025 TORS editorial [B35] announces the journal will require documented baseline-tuning procedures. And Soboroff [B36] argues that generating ground truth with an LLM sets that LLM as a ceiling on measured performance — which is why Mycelium's match % cannot serve as its own evaluation.

**LLM reranking.** *Frontier:* listwise permutation generation (RankGPT [B5]) is the dominant paradigm; RankZephyr [B37] treats robustness to input ordering as a required property. *Contested point directly relevant here:* the community consensus has been that listwise beats pointwise because LLMs judge relatively better than absolutely [B24]; a 2025 study partially overturns this, showing the gap shrinks to statistical insignificance for many model×dataset pairs **when the pointwise scale is a sufficiently large ordinal space** [B19]. A 0–100 integer is such a space. **But that paper measures nDCG@10 — ordering — and says nothing about magnitude.** The verbalized-confidence literature is consistent that LLM-emitted numbers are poorly calibrated and skewed high [B20].

**Constraint-based recommendation and eligibility.** *Structure:* formalize recommendation as a constraint-satisfaction problem, mediate hard and soft requirements, and — crucially — support *relaxation* when the feasible set empties [B6]. The best-developed instance is clinical-trial matching: TrialGPT [B7] predicts eligibility **per criterion with a natural-language explanation and sentence-level provenance**, then aggregates; SatIR [B8] compiles free-text criteria into SMT/relational constraints and beats TrialGPT by 22–38 recall points, admitting only clauses translatable "without ruling out true matches." *How the area evaluates itself:* TREC Clinical Trials uses **ternary graded judgments** — eligible (2), excluded-but-topically-relevant (1), not relevant (0) — with nDCG@10 [B21]. This separates "wrong field" from "right field, ineligible," which a boolean rule engine collapses.

**Reviewer assignment / expert finding.** *Frontier and a warning.* The RAP gold-standard dataset (477 self-reported expertise scores from 58 researchers) finds **all algorithms misrank at 12–30% in easy cases and 36–43% in hard ones**, that classical TF-IDF matches SPECTER2 given full texts, and that off-the-shelf LLMs lag specialized approaches [B15]. A 2026 study using proposal authorship as proxy ground truth found TF-IDF finds a labelled expert in the top 25 **79.5% of the time vs. 51.5% for GPT-4o mini**, diagnosing that "distinguishing subfield expertise requires fine-grained vocabulary, which is obscured by the semantic smoothing in generative methods" [B17]. MERIT [B25] criticizes exactly the cosine approach: existing methods "rely on coarse proxy signals that conflate general relatedness with true suitability." The area also treats **workload balancing and conflict-of-interest as mandatory constraints** — a top-3-by-cosine rule will systematically overload the same one or two lab members.

**Multi-agent LLM systems.** *The frontier is a rebuttal.* Cemri et al. [B9] (NeurIPS 2025 D&B) open with "Despite enthusiasm for Multi-Agent LLM Systems, their performance gains on popular benchmarks are often minimal," and build MAST, a 14-failure-mode taxonomy from 150 expert-annotated traces (κ=0.88); one of its three clusters is *task verification*, which Mycelium wholly lacks. Tran & Kiela [B10] hold reasoning-token budgets constant across three model families and find single-agent matches or beats multi-agent, concluding that "many reported advantages of multi-agent systems are better explained by unaccounted computation and context effects." Jwalapuram et al. [B11] find auto-generated multi-agent systems consistently underperform single-agent CoT-with-self-consistency at up to 10× the cost, exhibiting "architectural bloat that prioritizes superficial complexity which does not translate into functional utility." Even the pattern's strongest industrial advocate concedes token usage alone explains 80% of the variance in its own results [B38], and defines an agent as "LLMs autonomously using tools in a loop" — a definition under which Mycelium contains **zero agents**.

**Funding-opportunity recommendation.** *What the area is:* recommending grant calls, fellowships, or RFPs to researchers. *Structure:* essentially none — the work is too sparse to have a taxonomy. *Frontier:* GotFunding [B14] casts researcher→grant matching as **learning to rank** on NIH grant–publication records, reporting nDCG@1 = 0.945, with year-gap between publication and grant as its most important feature. A 2026 institution-level framework [B39] builds *multiple* publication sets per researcher (by authorship position and time window) and matches against Horizon Europe topics for 3,013 Granada researchers. A deep-learning study over 12,991 biosketches × 2,234 NIH RFPs reaches **F1 = 71.15%** [B40] — the honest ceiling on how hard this task is. *How the area evaluates itself:* nDCG, F1, on award-linkage data. *Open problems as the field states them:* [B12] states verbatim that grant recommenders "are the least studied scholarly recommendation systems," and that conference recommenders, unlike journal recommenders, are not available online at all; [B39] opens by calling grant recommendation "one of the least explored areas within academic recommender systems."

---

## 3. Closest Prior Work

| Citation | What they do | Overlap | Difference | Threat |
|---|---|---|---|---|
| **[B1]** Flicke et al., *Scholar Inbox: Personalized Paper Recommendations for Scientists*, ACL 2025 System Demonstrations | Open daily digest over arXiv/bioRxiv; per-user binary classifier on GTE embeddings over 3M+ papers; hard negatives from own surfaced papers; science map + active learning for cold start; **800k public user ratings** + user study | The entire paper-recommendation half: daily digest, personalized feed, cold start, deployed at scale | They *learn* from ratings and *evaluate*; Mycelium does neither. Mycelium adds funding/CFPs, lab-level targets, member routing, LLM rationales | **SCOOP** for the paper-feed framing. Any paper claiming "personalized daily research feed" must cite this and state a delta |
| **[B26]** *ResearchArena: Benchmarking LLMs' Ability to Collect and Organize Information as Research Agents* | Three stages — discovery, selection, organization — over 12M papers + 7.9K surveys | Stage 2 (assessing importance to a topic) is exactly Mycelium's LLM match-% step | They benchmark it; Mycelium does not | **SCOOP, and pointing the wrong way.** Headline finding: LLM-based approaches **underperform simpler keyword-based retrieval** |
| **[B14]** Zeng & Acuna, *GotFunding: A grant recommendation system based on scientific articles*, Proc. ASIS&T 2020 | Learning-to-rank over NIH grant–publication records; nDCG@1 = 0.945 | The grant-recommendation task | They *learn* the weights against a ranking objective on real award data; Mycelium hand-picks a 6-feature linear blend | **Partially overlaps.** Existence proof that award data yields ground truth — and a demonstration that the field expects learned weights |
| **[B39]** *Matching Researchers to Funding Calls: A Reproducible Institution-Level Framework*, 2026 | Multiple publication sets per researcher (by authorship position and time window); word-embedding matching against 291 Horizon Europe topics; 3,013 researchers | Researcher→funding-call matching by embeddings | No eligibility layer at all; institution-scale, not lab-scale; no LLM | **Partially overlaps.** Closest published architecture; note their *multiple profiles per researcher* is the same idea as Mycelium's multi-interest vectors, and they evaluate |
| **[B15]** *A Gold Standard Dataset for the Reviewer Assignment Problem*, 2023 | 477 self-reported expertise scores from 58 researchers; benchmarks paper–reviewer matching algorithms | The member-fit task, exactly, under another name | They measure it; Mycelium does not | **Undercuts.** Reports **36–43% misranking in hard cases**, and off-the-shelf LLMs lagging specialized methods. Mycelium's cosine floor of 0.35 sits in that regime |
| **[B17]** *Traditional statistical representations outperform generative AI in identifying expert peer reviewers*, 2026 | Observatory proposal data, authorship as proxy expertise ground truth | Ranking people against an item by textual similarity | Uses TF-IDF, which wins | **Undercuts.** TF-IDF 79.5% vs GPT-4o mini 51.5% at top-25 expert recall; diagnoses "semantic smoothing" in embeddings as the cause |
| **[B7]** Jin et al., *Matching patients to clinical trials with large language models (TrialGPT)*, Nat. Commun. 2024 | Three-stage retrieve → per-criterion eligibility with explanations → rank; >90% recall using <6% of candidates | The hard-eligibility + soft-relevance cascade | Per-criterion prediction with provenance rather than a hardcoded facet table; expert-level criterion accuracy | **Complements** — but sets the bar for what an eligibility layer should look like |
| **[B8]** *SatIR: Scalable High-Recall Constraint-Satisfaction-Based IR for Clinical Trials Matching*, 2026 | Compiles free-text eligibility into SMT/relational constraints executed as SQL; keeps only clauses translatable "without ruling out true matches" | Formalizing hard constraints in a matching system | +22–38 recall points over TrialGPT; a *principled* safety condition | **Complements and outclasses.** The correctness condition Mycelium's rule engine informally gestures at, stated properly |
| **[B4]** Cen et al., *Controllable Multi-Interest Framework for Recommendation* (ComiRec), KDD 2020 | Extract multiple interest vectors → retrieve per interest → aggregate with a **tuned** controllable parameter | The exact architecture: multi-interest retrieval + cross-interest aggregation | Interests are learned from behaviour; the aggregation λ is tuned | **Partially overlaps.** Mycelium's β=0.15 occupies ComiRec's aggregation slot but is a self-declared placeholder |
| **[B41]** Mysore et al., *Editable User Profiles for Controllable Text Recommendation* (LACE), SIGIR 2023 | Represents a user as human-readable concepts retrieved from an inventory, with personalized concept values; user-editable; reports zero/cold-start performance | Declared, human-readable, editable interest profiles driving recommendation | It is evaluated, and has a principled controllability guarantee | **Partially overlaps.** The direct intellectual ancestor of Mycelium's cluster/interest profile |
| **[B2]** Cormack, Clarke & Buettcher, *Reciprocal rank fusion outperforms Condorcet and individual rank learning methods*, SIGIR 2009 | RRF | The fusion method, cited correctly in a code comment | — | **Complements.** ⚠️ Note the irony: the same paper showed RRF beating **CombMNZ**, and Mycelium stacks a softened CombMNZ *on top of* RRF |
| **[B9]** Cemri et al., *Why Do Multi-Agent LLM Systems Fail?*, NeurIPS 2025 D&B | MAST: 14 failure modes from 150 annotated traces; 1600+ traces across 7 frameworks | The multi-agent framing | Empirical; finds gains "often minimal" and failures rooted in system design | **SCOOPS AGAINST.** Any multi-agent claim from Mycelium is pre-refuted |
| **[B10]** Tran & Kiela, *Single-Agent LLMs Outperform Multi-Agent Systems… Under Equal Thinking Token Budgets*, 2026 | Controlled ablation at matched token budgets, three model families | The multi-agent framing | Single-agent matches or beats multi-agent | **SCOOPS AGAINST** |
| **[B42]** PaperWeaver, CHI 2024 | LLM infers interests from collected papers, extracts aspects, compares recommended vs. collected papers on those aspects; user study N=15 | LLM-generated contextual explanations of *why* a paper is relevant | Measured: better understanding of relevance, more confident triage | **Complements.** The best evidence that Mycelium's prose-rationale feature has value — and the template for measuring it |

**Scoop summary.** Three papers scoop or undercut directly: **Scholar Inbox [B1]** on the personalized daily paper feed (and it shipped an 800k-rating dataset Mycelium does not have); **ResearchArena [B26]** on LLM-driven literature discovery and selection, finding *against* the LLM approach; and the multi-agent critique line **[B9, B10, B11]**, which pre-refutes the framing used in this repository's own docstrings. A good-faith search found **no paper that scoops** the two intersection claims — eligibility-constrained fellowship recommendation with graded ineligibility, and lab-level recommendation with member routing. Searched: `grant recommendation system`, `funding opportunity matching`, `fellowship recommender`, `call for proposals recommendation`, `team recommendation scholarly`, `group recommendation research papers`, `paper routing lab member`, plus the reviewer-assignment and expert-finding literature and the clinical-trial-matching analogue.

---

## 4. Gap Inventory

| # | Gap | Evidence it is open | Why it has stayed open | Does Mycelium address it? |
|---|---|---|---|---|
| **G1** | Funding-opportunity recommendation has no shared benchmark, no leaderboard, no shared task, and ~6 substantive papers in a decade | [B12] verbatim: grant recommenders "are the least studied scholarly recommendation systems"; [B39] "one of the least explored areas"; no relevant TREC/CLEF/NTCIR track exists in 2026 | **Data access and incentive.** Funding portals are commercial and paywalled; academic groups have no corpus. Award data exists but requires nontrivial linkage work | **Incidentally.** It ranks fellowships and grants, but proposes no benchmark and reports no metric |
| **G2** | Eligibility is treated as boolean, not graded, in every scholarly matching system found | The graded protocol exists only in clinical trials [B21]; no scholarly analogue found | **Nobody has assembled labeled eligibility data outside medicine.** It requires hand-annotation | **Partially.** It implements a hard gate but collapses "wrong field" and "right field, ineligible" into one exclusion, exactly what TREC-CDS avoids |
| **G3** | No published work recommends scholarly items to a *team* and routes them to individual members | No active academic group found; reviewer assignment does the inverse (people→item, for review not for reading) | **The unit of analysis in recsys is the individual account.** Lab-level deployment data is rare | **Directly.** `member_fit.py` + cluster-scoped lab fusion. Unmeasured |
| **G4** | Removal-only ("monotone veto") LLM filtering over a retrieval-derived candidate set is unstudied | No named technique found under `LLM as filter`, `recall-preserving reranking`, `safe reranking`, `monotone`, `abstention`. Nearest is AFR-Rank's Filter stage, framed as an efficiency mechanism | **It is an engineering convention, not a research question anyone posed.** | **Directly, and possibly wrongly.** ⚠️ It is a bounded-recall architecture by construction: a member at cosine 0.34 can never be recovered. The retrieval literature's response to bounded recall is to *expand* the candidate set adaptively — up to +28% recall [B43] |
| **G5** | Cross-interest fusion aggregation weights are tuned in the published literature and guessed here | ComiRec's λ is tuned [B4]; RRF's k is empirically grounded [B2] | Not open — this is a gap in *this project*, not in the field | **Not at all** |
| **G6** | Whether LLM-generated recommendation rationales are *faithful* to the ranking mechanism | [B44] finds LLM explanations misstate what drove the output and must be measured causally | Faithfulness measurement is expensive and only recently formalized | **Not at all** — and Mycelium's case is worse than empirical: ~92% of items get a template reason with no model involved, and for the remaining ~9% the score and prose are co-samples from one generation, so neither can explain the other |
| **G7** | Conference/CFP recommendation *to a researcher profile* (rather than venue recommendation for a finished paper) has essentially no literature | [B12] notes conference recommenders are not available online at all; the venue-recommendation line [B45] all assumes a finished manuscript | **Different task, no dataset, low perceived value** | **Incidentally.** 2,989 CFP records ranked, nothing claimed |

---

## 5. Novelty Verdict

### 5.1 Novelty assessment

| Dimension | Score | Justification |
|---|---|---|
| **Problem novelty** | **Moderate** | Lab-level scholarly recommendation with member routing (G3) and eligibility-constrained funding recommendation (G1, G2) are genuinely under-served; two surveys name the funding gap explicitly [B12, B39]. But the framing actually present in the repository — "a personalized daily research feed" — is not new and was published with an evaluation last year [B1]. |
| **Methodological novelty** | **None** | Every mechanism is prior art: RRF [B2], multi-interest retrieval and aggregation [B3, B4], LLM top-*k* reranking [B5], constraint-cascade recommendation [B6], hand-blended feature scoring (an unfitted learning-to-rank model [B46]). The two ideas with any originality — gate-on-cosine/rank-on-fusion, and cluster max-pooling — are sound engineering judgments about score calibration, not methods a reviewer would call a contribution. |
| **Domain-transfer novelty** | **Marginal** | Commodity hybrid retrieval applied to fellowships is a transfer, but a shallow one. The genuinely hard part of the transfer — eligibility as a first-class, graded, relaxable constraint — is solved better and earlier in clinical-trial matching [B7, B8], and Mycelium's version (a hardcoded facet table with a 4-entry career-stage map and no relaxation path) is strictly weaker than the published state of the art in the analogue domain. |
| **Empirical novelty** | **None realized; Strong latent** | This is the project's defining asymmetry. Nobody has measured funding-opportunity recommendation on a shared benchmark; nobody has measured item→team-member routing in a lab; nobody has reported whether a hybrid RRF stack beats a dense-only baseline on a *personalized* scholarly feed. Those numbers would be new to the field. **Zero of them exist.** |
| **Systems novelty** | **Marginal** | 113k LOC, 1,379 tests, real systemd deployment, durable Discord outbox, a Playwright scraper that handles a Blazor SignalR circuit. Genuinely competent. But artifact value is gutted by three things: the distinguishing corpus cannot be released, the LLM is an unpinned env var with no default, and the demonstrated scale is 2 users. |
| **Resource novelty** | **None realized; Moderate latent** | 946 fellowships + 2,989 conference CFPs with structured eligibility facets is a corpus nobody in the literature has. ⚠️ It is scraped from a commercial Clarivate product behind institutional SSO and from a single university's site — it cannot be released as-is, and describing the scrape in a paper carries its own risk. Rebuilt from open sources (CORDIS, NIH RePORTER, NSF Awards, public university fellowship listings), it becomes a real contribution. |

### 5.2 Honest overall position

**Not currently publishable as research; valuable as infrastructure and as a demo — and the half of it that most resembles a research contribution is substantially anticipated.**

The paper-recommendation pipeline is a competent 2023-vintage recipe applied to a problem that was published last year with an evaluation and a public 800,000-rating dataset [B1]. Its distinguishing framing — "multi-agent" — is refuted by three independent 2025–2026 studies [B9, B10, B11] and is factually inaccurate about this codebase besides.

**What a submission costs.** Its evaluation is not weak; it is absent, in a subfield whose own literature has spent fifteen years arguing that evaluation is the thing that separates a recommender from an opinion [B31, B32, B33, B34, B35].

What is *not* anticipated is narrower and more interesting than the product: **eligibility-constrained funding and fellowship recommendation with graded ineligibility, deadline-aware ranking, and reciprocal routing of opportunities to lab members under workload constraints.** No paper found does this. Claiming it requires exactly one thing the project has never done — measurement — and requires *less* system than already exists, not more.

The blunt version: nine weeks of extremely productive engineering have produced a product with no research output, and the marginal value of week ten of engineering is negative. The marginal value of week ten spent labelling 200 items is very high.

### 5.3 The hard questions

**"What did you learn that we did not already know?"** — *As of today: nothing.* There is no finding in this repository. There are seven implicit claims (§1.6) and zero results. This is the answer a reviewer would get, and it ends the review.

**Strongest reason to stop working on this.** The product's core loop is genuinely valuable to its users and genuinely unpublishable in its current framing, and those two facts pull in opposite directions. Every hour spent on onboarding UI, billing tiers, and Discord commands — which is where the churn actually went (`docs/changelog.md` is the single most-modified file at 276 commits, followed by `repo-map.md` at 91, then frontend types and hooks) — is an hour not spent on the measurement that would make it a thesis chapter. If the goal is a company, continue. If the goal is a PhD, the current trajectory produces a portfolio piece and no papers. **Nine weeks in, the ratio of product commits to evaluation commits is 426:0.**

**Fastest experiment that would falsify the central claim.** C1 — that the hybrid fusion stack beats dense retrieval alone. Run the existing retrieval code against **LongEval-Sci 2026** (CLEF LongEval Task 1: ad-hoc scientific retrieval over CORE open-access publications, three temporal snapshots, 100 train + 338 test queries, with published BM25 and Qwen3-Embedding-4B baselines). The data is openly downloadable now — no registration, no deadline, `pip install ir-datasets-longeval`. **Estimated cost: one week.** If RRF-over-BGE-small does not beat BM25 on a scholarly collection, the retrieval layer has no defensible claim and the project should pivot immediately to the funding/routing half. If it does, you have your first number and roughly five venues open up. ⚠️ Limitation to state in the paper: LongEval-Sci is ad-hoc query retrieval, not personalized feed ranking, so it tests the retrieval substrate and not the personalization.

**Is the effort-to-contribution ratio defensible?** *Not as spent; yes going forward.* 113k lines and 426 commits have produced an L1 artifact. That is a poor ratio by research standards — a paper-worthy version of C5 or C6 could have been built on perhaps 15% of this code. But the sunk cost is genuinely reusable: the ingestion, the corpus, the deployment, and the two intersection gaps are real assets. The next 14–22 weeks, spent on measurement rather than features, have a good ratio. The question is whether the discipline to stop building is available.

---

## 6. Publication Readiness

### 6.1 Readiness ladder

**Level: L1 — Artifact.**

The system runs end to end on realistic input, daily, in production, and has done so for 30+ logged runs. It clears L1 comfortably.

**Blocking criterion for L2: no falsifiable research claim is stated anywhere, and the system is not built to test one.** The documentation (`purpose.md`, `goals.md`, `architecture.md`, a 218 KB `changelog.md`) is product direction throughout — there is no hypothesis in it. The seven claims in §1.6 had to be reverse-engineered from code by this audit; they are not the project's own. ⚠️ The instrumentation for L2 is half-built: `RelevanceEvent` is documented at `content/models.py:471-475` as "the ground-truth stream a future team-relevance recompute (and the evaluation harness) will read," and it *is* written for project-scoped actions — but no personal-feed endpoint calls `record_event` at all (`content/views.py:933,1095`), so the personal side of the stream is empty, and no evaluation harness reads any of it.

L1, not L2. Do not inflate this. Clearing it means writing down three claims, adding `record_event` calls to the personal save/dismiss/open paths, and building the consumer — call it 2–3 weeks, and it is the single highest-value structural change available.

### 6.2 Readiness scorecard

| Axis | Score | Justification |
|---|---|---|
| **Claim clarity** | **0** | No claim exists in any document or docstring. The repository states a product purpose, not a hypothesis. All seven claims in §1.6 were derived by this audit from code behaviour. |
| **Novelty defensibility** | **1** | Anticipated at the mechanism level across the board ([B2], [B4], [B5], [B6]); the paper-feed framing is anticipated as a whole system [B1]. Above 0 only because the funding-eligibility and lab-routing intersections are genuinely thin [B12, B39] and the delta *could* be stated — it just isn't. |
| **Evaluation rigor** | **0** | No metric, no judgment set, no measurement of output quality. Verified by exhaustive grep: `ndcg\|mrr@\|precision@\|recall@\|ground.?truth\|qrel\|ablation` returns one hit, an aspirational docstring. The 1,379 tests are correctness tests. |
| **Baseline coverage** | **0** | No baseline of any kind. ⚠️ A deterministic non-LLM arm exists in code (`_force_fallback`, `pipeline.py:149-155`) and is used exclusively as a billing gate; no run compares it. |
| **Data legitimacy** | **1** | Split. The paper corpus (OpenAlex/PubMed/Semantic Scholar) is legitimate and releasable — call it a 3. The *distinguishing* corpus is not: 2,989 conference records and 946 fellowships scraped from a commercial Clarivate product behind institutional SSO, plus one university's Blazor site. It cannot be redistributed, and its provenance is a liability in a paper, not an asset. Weighted to 1 because the un-releasable half is the half the novelty claim rests on. |
| **Reproducibility / artifact** | **2** | ⚠️ **This axis scores artifact hygiene, not end-to-end runnability** — §1.5 correctly says a third party cannot reproduce the full system, and a stricter reading would score this 1. Scored 2 because the packaging is genuinely good: `uv.lock` pinned, Docker Compose for the whole stack, documented README, 1,379 offline-runnable tests with injectable seams. Blocking for a 3: `LLM_MODEL` defaults to `""` (`settings.py:314`) so the scoring component is unspecified; `LLM_TEMPERATURE=0.2` so it is nondeterministic even once pinned; Pivot-RP needs SSO credentials; Playwright is host-only; no seeds in the pipeline. |
| **Positioning** | **0** | Related work is absent. The repository contains exactly one literature *reference* — the same "Cormack et al." RRF note repeated in two comments (`fusion.py:42-43`, `search.py:49`) — plus a provenance note for the vendored fellowship rules. A full-repo sweep for `et al.`, DOI, arXiv ID, and author-year across `.py/.ts/.tsx/.md/.toml` finds nothing else. Scored 0 rather than 1 because the anchor for 1 is an explicit comparison to at least one named external system, and none exists; the code's design-rationale comments (`fusion.py:19-22` rejecting raw CombMNZ, `fanout.py:7-8` on calibration) engage *alternatives* thoughtfully but never *prior work*. Scholar Inbox, LACE, ComiRec, GotFunding, and the reviewer-assignment literature are all unreferenced, and all are directly relevant. |
| **Narrative** | **2** | `purpose.md` and `goals.md` are well-written and internally coherent — a genuinely clear product story. But the story is entirely system description; there is no "what we did not know before, and now do" anywhere. Scores exactly the anchor for 2. |

**Mean: 0.75. Minimum axis: 0**, shared by **claim clarity, evaluation rigor, baseline coverage, and positioning.** The minimum is what matters; four axes at floor is not a weak link but a missing chain.

### 6.3 Tier thresholds

| Axis | Current | Workshop/demo min | Applied conf. min | Top-tier min |
|---|---|---|---|---|
| Claim clarity | 0 | 2 ❌ | 3 ❌ | 4 ❌ |
| Novelty defensibility | 1 | 1 ✅ | 3 ❌ | 4 ❌ |
| Evaluation rigor | 0 | 1 ❌ | 3 ❌ | 4 ❌ |
| Baseline coverage | 0 | 1 ❌ | 3 ❌ | 4 ❌ |
| Data legitimacy | 1 | 2 ❌ | 3 ❌ | 3 ❌ |
| Reproducibility | 2 | 1 ✅ | 2 ✅ | 3 ❌ |
| Positioning | 0 | 2 ❌ | 3 ❌ | 4 ❌ |
| Narrative | 2 | 2 ✅ | 3 ❌ | 4 ❌ |

- **Workshop / demo: NEAR.** Falls short on claim clarity, evaluation rigor, baseline coverage, data legitimacy, and positioning. ⚠️ **Important caveat where the scorecard over-predicts difficulty:** dedicated *demo tracks* at ECIR, JCDL, and CHIIR do not require evaluation, and a deployed system with a video demos well. Verified against their current CFPs, none of the three imposes an evaluation requirement. But the trend runs the other way — ACL 2026 and EMNLP 2026 demo tracks now state that "submissions that fail to provide any form of evaluation may be desk rejected," and CIKM 2026 Applied Research desk-rejects submissions without post-launch metrics. Treat demo tracks as a two-year window that is closing.
- **Applied or domain conference: FAR.** Falls short on seven of eight axes.
- **Top-tier archival: FAR.** Falls short on all eight.

### 6.4 Hard disqualifiers — all eight checked

| # | Disqualifier | Result |
|---|---|---|
| 1 | Central claim not falsifiable as constructed | **N/A — no claim exists.** Not a disqualifier in the strict sense; it is a precondition failure that blocks L2. The seven derived claims in §1.6 *are* falsifiable, which is good news: the project is not structurally unfalsifiable, it is merely silent. |
| 2 | No baseline, or only a strawman | **PRESENT.** Zero baselines. The strongest form of this disqualifier. |
| 3 | Closest prior work already demonstrates the claimed result | **PRESENT for the paper half.** Scholar Inbox [B1] demonstrates a deployed personalized daily research feed *with* an evaluation and a public 800k-rating dataset. ResearchArena [B26] already ran the LLM-driven discovery-and-selection experiment and found LLM approaches underperform keyword retrieval. **ABSENT for the funding and member-routing halves** — a good-faith search found no equivalent. |
| 4 | Evaluation data cannot be shared or described, with no path to a releasable proxy | **PRESENT for the opportunity corpus, with a route out.** Pivot-RP is Clarivate proprietary behind institutional SSO; the Illinois Fellowship Finder is one university's site. Neither can be redistributed. **The proxy exists and is proven:** NIH RePORTER, NSF Awards, and CORDIS bulk open data support award-linkage ground truth, and [B14] already built exactly this for NIH. The paper corpus (OpenAlex, CC0) is fine. |
| 5 | **Test-data contamination** | **LATENT, UNMEASURED, AND CURRENTLY UNCHECKABLE — the most important finding in this table.** Three separate exposures. (a) **The model is not pinned.** `LLM_MODEL = env("LLM_MODEL", default="")` (`settings.py:314`); `complete()` raises if unset. The system's scoring component has no recorded identity, so its training cutoff is unknown and *no contamination check can be run against the repository as committed.* Fix this first — it is a one-line change with outsized consequences. (b) **Papers are partly protected by construction, and that protection is accidental.** The feed is scoped to `latest_gather_date` (`pipeline.py:369`), so items are typically days old and post-cutoff for any fixed model. But any retrospective evaluation on historical papers would be severely contaminated, and the current design gives no way to detect it. (c) **Fellowships and CFPs are almost certainly contaminated.** These are long-lived public web pages (the Apple PhD Fellowship description, Illinois fellowship listings) with a high prior of appearing in any web-scale pretraining corpus. An LLM's "match %" for a well-known fellowship may reflect memorized prestige rather than profile fit — which would be indistinguishable from good performance under the current setup. **Two cheap, proven mitigations:** build a post-cutoff holdout in the style of RankGPT's NovelEval [B5], and compare match-% distributions on pre- vs. post-cutoff items, as [B19] did with post-cutoff proprietary labels. Neither has been attempted. See also [B47] on leakage inflating LLM-based recommendation results. |
| 6 | Improvement not attributable to the mechanism (no ablation) | **PRESENT.** No ablation separates RRF from vector-only, LLM from template, cluster-scoped from flat, or β from zero. ⚠️ Compounded by a confound the code creates itself: the LLM sees only the top 10 and its verdicts are frozen permanently by carry-forward (`opportunity_llm.py:88-118`), so any observed quality difference between the top 10 and the rest is confounded with LLM exposure, recency, and the `new_first` slot policy simultaneously. |
| 7 | Human-judgment evaluation with a single unblinded rater and no agreement statistics | **NOT APPLICABLE — because there are zero raters, not one.** No human evaluation exists in any form. Reported for completeness: if a study were run today on the current base of 2 real users (one of whom is the developer), it would trigger this disqualifier immediately and severely. Any user study must recruit outside the lab and report inter-rater agreement. |
| 8 | Required licensing, IRB, or data-use approval absent with no route | **PARTIALLY PRESENT, route available.** No IRB exists, and any user study needs one (routine, ~4–8 weeks). More seriously: describing SSO-authenticated scraping of a commercial Clarivate product in a published paper is a real institutional and legal exposure, independent of whether the data is released. **Route:** obtain IRB before any user study, and replace or supplement the Pivot corpus with open sources for anything published. |

**Four of eight disqualifiers present (2, 3-partial, 4, 6), one latent-and-uncheckable (5), one N/A-for-the-wrong-reason (1), one N/A (7), one partial (8). This is decisive: the project is FAR from publishable at archival venues, and no scorecard improvement overrides it until #2 and #6 are cleared.**

### 6.5 Distance estimate

| Work item | Closes gap | Raises axis | Prerequisite | Weeks | Risk |
|---|---|---|---|---|---|
| **W0.** Strike the knowledge-graph, Cytoscape, multi-agent, and ReAct claims from `README.md`, `docs/architecture.md`, and `briefing_agents.py:1`, or move them under an explicit Roadmap heading | The six ⚠️ overstatements in §1.5 | Narrative | none | **0.2** | None — and it **must precede any demo submission.** A reviewer who greps the repo against the README finds the gap in five minutes, and a README that self-describes as "planned" undercuts a demo paper claiming a deployed system. |
| **W1.** Pin `LLM_MODEL` and set `LLM_TEMPERATURE=0` in code; record model identity, cutoff, **and token usage** on every `RelevanceScore` | Contamination checkability (#5); cost accounting | Reproducibility 2→3 | none | **0.2** | None. Do this today. Token usage matters because W6's ablations and the matched-compute argument [B10, B11] are unanswerable without per-item cost. |
| **W2.** Run existing retrieval on LongEval-Sci 2026 vs. published BM25 + Qwen3-Embedding-4B baselines | C1 | Eval 0→2, Baseline 0→2 | none | **1** | Low. Data is open. Risk is the *result* — it may falsify C1. That is the point. |
| **W3.** Write down 3 claims formally; **instrument the personal feed to emit `RelevanceEvent`s** — no personal endpoint currently calls `record_event` (`content/views.py:933,1095`) — and build a consumer that reads them | L1→L2 | Claim clarity 0→3 | none | **2.5** | Low, but larger than it looks: this is new instrumentation, not a filter change |
| **W4.** Related-work section engaging the 15 works in §3 | Positioning | Positioning 0→3 | none | **1.5** | Low |
| **W5.** Hand-label 250–300 (item, researcher) pairs with graded judgments in the TREC-CDS style [B21] — eligible=2, relevant-but-ineligible=1, irrelevant=0 | G2, C5 | Eval 2→3, Data 1→2 | W3 | **2.5** | Medium — needs 3+ annotators outside the lab and κ reporting |
| **W6.** Ablation suite: vector-only / BM25-only / RRF / ±cluster-scoping / β sweep / ±LLM rerank | C1, C2, C3, #6 | Baseline 2→3, Eval 3→4 | W2, W5 | **2** | Low |
| **W7.** Build award-linkage ground truth from NIH RePORTER + NSF + CORDIS: profile each PI from publications strictly *before* the award date; positives = programs won; negatives = contemporaneous unwon calls | G1, C5 | Eval, Baseline, Data 2→3 | none (parallel) | **4** | Medium-high. ⚠️ Temporal leakage is the killer — [B14] found publication-to-grant year gap to be its single most important feature. Also: won ≠ applied, so positives are contaminated by selection |
| **W8.** Member-fit evaluation on the RAP gold-standard protocol [B15]: self-reported expertise scores from lab members, misranking rate, TF-IDF baseline [B17], workload-balance measure | G3, C6 | Eval, Baseline | W3, recruit ≥15 members across ≥3 labs | **4** | High — recruitment is the bottleneck, not the code |
| **W9.** IRB submission for a user study | #8 | Data legitimacy | none (parallel, start now) | **4–8 elapsed, ~0.5 effort** | Low but slow |
| **W10.** Rebuild the opportunity corpus from open sources (CORDIS, RePORTER, NSF, public university listings) to make it releasable | #4, Resource novelty | Data 1→3 | none | **3** | Medium — loses the Pivot conference CFPs, which have no open equivalent |
| **W11.** Structured-output enforcement + retries + order-robustness test for the LLM scorer | #6 partially | Eval | none | **1** | Low. Commodity since [B48] |
| **W12.** Post-cutoff contamination holdout (NovelEval-style [B5]) + pre/post match-% distribution comparison | #5 | Eval | W1 | **1** | Low |

**Critical path.** W0 → W1 → W3 → W5 → W6 is the spine: the doc cleanup and model pinning gate everything downstream; formal claims are needed before labelling is meaningful; labelled judgments are needed before ablations mean anything; ablations are what clear disqualifier #6. **0.2 + 0.2 + 2.5 + 2.5 + 2 = 7.4 weeks of focused work.** W2 (1 wk) is off the path and should run first anyway. W4 (1.5 wk) is fully parallel. W9 must start immediately because its elapsed time, not its effort, is the constraint. W7 and W8 are alternative *second* papers and should not both be attempted.

**Cheapest decisive next action:** **W2 — run the existing retrieval stack on LongEval-Sci 2026 against its published BM25 and Qwen3-Embedding-4B baselines. One week. No labelling, no recruitment, no IRB, no permission.** It is decisive because it is a genuine falsification test of C1: if the hybrid does not beat BM25 on a scholarly collection, the retrieval layer has no claim and the project should reallocate to the funding and routing halves immediately. Runner-up on value-per-week is W5 (the 250-item labelling), which unlocks more but costs 2.5× as much and needs annotators.

**Confidence in these estimates: moderate.** They assume one person working full-time and unchanged scope. What would change them, in order of impact: (i) whether W2 falsifies or confirms C1 — a falsification saves months by redirecting early; (ii) annotator availability for W5 and recruitment for W8, which are the two items whose duration is set by other people; (iii) whether the Pivot corpus must be abandoned for legal reasons, which would add W10 to the critical path and push the workshop estimate to 14–20 weeks.

### 6.6 Readiness verdict line

> **Readiness: L1 — near from demo track, far from applied conference and far from top-tier archival; blocked by claim clarity, evaluation rigor, baseline coverage, and positioning (all scored 0/4); critical path 10–16 weeks to a credible applied/workshop submission; cheapest next action: run the existing retrieval stack on the openly-downloadable LongEval-Sci 2026 collection against its published BM25 and Qwen3-Embedding-4B baselines (~1 week).**

---

## 7–8. Reshaping Paths and Venue Strategy

Not kept in this repository. The audit's candidate paper framings and its venue
strategy are research planning, and they live with the project's other
publication and grant plans outside the public tree.

---

## 9. Bibliography

Every entry below was retrieved during this session. Entries marked **[unverified metadata]** had their existence and identifiers confirmed via a search index but the abstract or author list was not independently fetched — treat the exact wording of titles or author lists as provisional and re-check before citing in a manuscript.

### Scholarly recommendation — surveys and systems

- **[B1]** Flicke, M., Angrabeit, G., Iyengar, M., Protsenko, V., Shakun, I., Cicvaric, J., Kargi, B., He, H., Schuler, L., Scholz, L., Agnihotri, K., Cao, Y., Geiger, A. *Scholar Inbox: Personalized Paper Recommendations for Scientists.* ACL 2025 System Demonstrations. arXiv:2504.08385. https://aclanthology.org/2025.acl-demo.30/
- **[B12]** *Scholarly recommendation systems: a literature survey.* Knowledge and Information Systems, 2023. DOI 10.1007/s10115-023-01901-x. https://link.springer.com/article/10.1007/s10115-023-01901-x — verified author Hulin Wu (UTHealth Houston); full author list not captured. Source of "grant recommendation systems… are the least studied."
- **[B22]** Beel, J., Gipp, B., Langer, S., Breitinger, C. *Research-paper recommender systems: a literature survey.* Int. J. Digital Libraries 17(4):305–338, 2016. DOI 10.1007/s00799-015-0156-0. ⚠️ Frequently mis-cited as 2015 (online-first); the journal issue is 2016.
- **[B23]** Pinedo, I., Larrañaga, M., Arruarte, A. *Recent Advances and Trends in Research Paper Recommender Systems: A Comprehensive Survey.* arXiv:2508.08828 (Aug 2025, rev. Jan 2026). Covers Nov 2021 – Dec 2024.
- **[B42]** Lee, Y., Kang, H.B., Latzke, M., Kim, J., Bragg, J., Chang, J.C., Siangliulue, P. *PaperWeaver: Enriching Topical Paper Alerts by Contextualizing Recommended Papers with User-collected Papers.* CHI 2024. DOI 10.1145/3613904.3642196. arXiv:2403.02939.
- **[B49]** *SciNUP: Scientific Paper Recommendation with Natural-Language User Profiles.* arXiv:2510.21352. https://arxiv.org/abs/2510.21352
- Kreutz, C.K., Schenkel, R. *Scientific Paper Recommendation Systems: a Literature Review of recent Publications.* IJDL 23(4):335–369, 2022. arXiv:2201.00682.
- Wang, C., Blei, D.M. *Collaborative topic modeling for recommending scientific articles.* KDD 2011. DOI 10.1145/2020408.2020480. — canonical cold-start-motivated hybrid.

### Evaluation methodology and critique

- **[B31]** Beel, J., Langer, S. *A Comparison of Offline Evaluations, Online Evaluations, and User Studies in the Context of Research-Paper Recommender Systems.* TPDL 2015, LNCS 9316:153–168. DOI 10.1007/978-3-319-24592-8_12.
- **[B32]** Ferrari Dacrema, M., Cremonesi, P., Jannach, D. *Are We Really Making Much Progress? A Worrying Analysis of Recent Neural Recommendation Approaches.* RecSys 2019 (Best Long Paper). arXiv:1907.06902.
- **[B33]** Hidasi, B., Czapp, Á.T. *Widespread Flaws in Offline Evaluation of Recommender Systems.* RecSys 2023. arXiv:2307.14951. DOI 10.1145/3604915.3608839.
- **[B34]** Beel, J., Jannach, D., Said, A., Shani, G., Vente, T., Wegmeth, L. *Best-Practices for Offline Evaluations of Recommender Systems.* In Dagstuhl Seminar 24211 report, 2024. https://drops.dagstuhl.de/storage/04dagstuhl-reports/volume14/issue05/24211/DagRep.14.5.58/DagRep.14.5.58.pdf
- **[B35]** *Improving Methodological Standards in Recommender Systems Offline Evaluation.* ACM TORS 4(3), Art. 34e (editorial). DOI 10.1145/3800587. **[unverified metadata — author list not captured; cite by title]**
- **[B36]** Soboroff, I. *Don't Use LLMs to Make Relevance Judgments.* Information Retrieval Research 1(1):29–46, 2025. arXiv:2409.15133. DOI 10.54195/irrj.19625.
- Beel, J. et al. *Towards reproducibility in recommender-systems research.* UMUAI 26:69–101, 2016. DOI 10.1007/s11257-016-9174-x.
- Sun, A. *On Challenges of Evaluating Recommender Systems in an Offline Setting.* RecSys 2023. DOI 10.1145/3604915.3609495.

### Retrieval, fusion, and scientific embeddings

- **[B2]** Cormack, G.V., Clarke, C.L.A., Buettcher, S. *Reciprocal rank fusion outperforms Condorcet and individual rank learning methods.* SIGIR 2009:758–759. DOI 10.1145/1571941.1572114.
- **[B16]** *UniFAR: A Unified Facet-Aware Retrieval Framework for Scientific Documents.* arXiv:2602.23766 (2026).
- **[B18]** Ajith, A., Xia, M., Chevalier, A., Goyal, T., Chen, D., Gao, T. *LitSearch: A Retrieval Benchmark for Scientific Literature Search.* EMNLP 2024:15068–15083. arXiv:2407.18940.
- **[B27]** Cohan, A., Feldman, S., Beltagy, I., Downey, D., Weld, D. *SPECTER: Document-level Representation Learning using Citation-informed Transformers.* ACL 2020:2270–2282. arXiv:2004.07180. (Introduces SciDocs.)
- **[B28]** Singh, A., D'Arcy, M., Cohan, A., Downey, D., Feldman, S. *SciRepEval: A Multi-Format Benchmark for Scientific Document Representations.* EMNLP 2023. arXiv:2211.13308. (Introduces SPECTER2.)
- **[B29]** Mysore, S., O'Gorman, T., McCallum, A., Zamani, H. *CSFCube: A Test Collection of Computer Science Research Articles for Faceted Query by Example.* NeurIPS 2021 Datasets & Benchmarks.
- **[B30]** *DORIS-MAE: Scientific Document Retrieval using Multi-level Aspect-based Queries.* NeurIPS 2023 Datasets & Benchmarks. arXiv:2310.04678. **[unverified metadata — full author list not confirmed]**
- **[B43]** *Guiding Retrieval using LLM-based Listwise Rankers (SLIDEGAR).* arXiv:2501.09186. **[unverified metadata]** — identifies the bounded-recall problem; adaptive expansion improves recall by up to 28.02%.
- Ostendorff, M., Rethmeier, N., Augenstein, I., Gipp, B., Rehm, G. *Neighborhood Contrastive Learning for Scientific Document Representations with Citation Embeddings* (SciNCL). EMNLP 2022. arXiv:2202.06671.
- Mysore, S., Cohan, A., Hope, T. *Multi-Vector Models with Textual Guidance for Fine-Grained Scientific Document Similarity* (Aspire). NAACL 2022. arXiv:2111.08366.
- *Chain of Retrieval: Multi-Aspect Iterative Search Expansion…* arXiv:2507.10057. — Table 1 shows general-purpose encoders matching SPECTER2/SciNCL on abstract-to-abstract retrieval.
- *ChEmbed: Enhancing Chemical Literature Search Through Domain-Specific Text Embeddings.* arXiv:2508.01643. — +9 pp nDCG@10 from domain adaptation; tokenizer fragmentation as a failure mode.
- *CASPER: Concept-integrated Sparse Representation for Scientific Retrieval.* arXiv:2508.13394. **[unverified metadata]**

### Multi-interest and controllable user modeling

- **[B3]** Li, C., Liu, Z., Wu, M., et al. *Multi-Interest Network with Dynamic Routing for Recommendation at Tmall* (MIND). CIKM 2019. arXiv:1904.08030.
- **[B4]** Cen, Y., Zhang, J., Zou, X., Zhou, C., Yang, H., Tang, J. *Controllable Multi-Interest Framework for Recommendation* (ComiRec). KDD 2020. Code: https://github.com/THUDM/ComiRec
- **[B41]** Mysore, S., Jasim, M., McCallum, A., Zamani, H. *Editable User Profiles for Controllable Text Recommendation* (LACE). SIGIR 2023. DOI 10.1145/3539618.3591677. arXiv:2304.04250.

### LLM ranking, judging, and calibration

- **[B5]** Sun, W., Yan, L., Ma, X., Wang, S., Ren, P., Chen, Z., Yin, D., Ren, Z. *Is ChatGPT Good at Search? Investigating Large Language Models as Re-Ranking Agents* (RankGPT). EMNLP 2023 (Outstanding Paper). arXiv:2304.09542. — introduces **NovelEval**, a post-cutoff test set built expressly to control contamination in ranking evaluation.
- **[B19]** Godfrey, C., Nie, P., Ostapuk, N., Ken, D., Gao, S., Inati, S. *Likert or Not: LLM Absolute Relevance Judgments on Fine-Grained Ordinal Scales.* arXiv:2505.19334, 2025. — pointwise/listwise gap becomes statistically insignificant for many model×dataset pairs given a sufficiently large ordinal space; evaluated partly on post-training-cutoff labels.
- **[B20]** Yang, D. et al. *On Verbalized Confidence Scores for LLMs.* arXiv:2412.14737. **[unverified metadata]** — with *Overconfidence in LLM-as-a-Judge* (arXiv:2508.06225) and *Large Language Models Are Overconfident in Their Own Responses* (arXiv:2606.03437): LLM-emitted numeric degrees are poorly calibrated and skewed high.
- **[B24]** Qin, Z., Jagerman, R., Hui, K., Zhuang, H., Wu, J., Shen, J., Liu, T., Liu, J., Metzler, D., Wang, X., Bendersky, M. *Large Language Models are Effective Text Rankers with Pairwise Ranking Prompting.* arXiv:2306.17563, 2023.
- **[B37]** *RankZephyr: Effective and Robust Zero-Shot Listwise Reranking is a Breeze!* arXiv:2312.02724. **[unverified metadata]**
- **[B44]** Matton, K., Ness, R.O., Guttag, J., Kıcıman, E. *Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations.* ICLR 2025. arXiv:2504.14150. **[unverified metadata]**
- **[B47]** *Benchmark Leakage Trap: Can We Trust LLM-based Recommendation?* arXiv:2602.13626, 2026. **[unverified metadata]** — in-domain leakage produces substantial but spurious performance inflation in LLM-based recommendation.
- **[B48]** Geng, S., Cooper, H., Moskal, M., Jenkins, S., Berman, J., Ranchin, N., West, R., Horvitz, E., Nori, H. *JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models.* arXiv:2501.10868, 2025. **[unverified metadata]**
- Zheng, L. et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* arXiv:2306.05685. **[unverified metadata]**
- Shi, L., Ma, C., Liang, W., Diao, X., Ma, W., Vosoughi, S. *Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge.* AACL-IJCNLP 2025. arXiv:2406.07791. — >150,000 evaluation instances; position bias is worst when candidates are close in quality.
- Zhuang, H. et al. *Beyond Yes and No: Improving Zero-Shot LLM Rankers via Scoring Fine-Grained Relevance Labels.* arXiv:2310.14122. **[unverified metadata]**
- Tam, Z.R., Wu, C.-K., Tsai, Y.-L., Lin, C.-Y., Lee, H., Chen, Y.-N. *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models.* arXiv:2408.02442, 2024. ⚠️ **Contested** — see the `.txt` rebuttal at https://blog.dottxt.co/say-what-you-mean.html. Cite as disputed, not settled.

### Agents for science, and the multi-agent critique

- **[B9]** Cemri, M., Pan, M.Z., Yang, S., Agrawal, L.A., Chopra, B., Tiwari, R., Keutzer, K., Parameswaran, A., Klein, D., Ramchandran, K., Zaharia, M., Gonzalez, J.E., Stoica, I. *Why Do Multi-Agent LLM Systems Fail?* NeurIPS 2025 Datasets & Benchmarks. arXiv:2503.13657.
- **[B10]** Tran, D., Kiela, D. *Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets.* arXiv:2604.02460, 2026.
- **[B11]** Jwalapuram, P., Lin, H., Li, C., Jiao, F., Wang, S., Ming, Y., Ke, Z., Qin, C., Carenini, G., Joty, S. *The Illusion of Multi-Agent Advantage.* arXiv:2606.13003, 2026.
- **[B26]** *ResearchArena: Benchmarking LLMs' Ability to Collect and Organize Information as Research Agents.* arXiv:2406.10291. **[unverified metadata]** — LLM-based approaches underperform simpler keyword-based retrieval.
- **[B38]** Hadfield, J., Zhang, B., Lien, K., Scholz, F., Fox, J., Ford, D. *How we built our multi-agent research system.* Anthropic engineering blog, 13 Jun 2025. https://www.anthropic.com/engineering/multi-agent-research-system — **practice evidence, not peer-reviewed.** Concedes token usage alone explains ~80% of variance.
- Ren, S., Xie, C., Jian, P., Ren, Z., Leng, C., Zhang, J. *Towards Scientific Intelligence: A Survey of LLM-based Scientific Agents.* arXiv:2503.24047.
- Lu, C., Lu, C., Lange, R.T., Foerster, J., Clune, J., Ha, D. *The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery.* arXiv:2408.06292, 2024.
- *Towards an AI co-scientist.* arXiv:2502.18864, 2025. ⚠️ One index entry suggests a later retitle — verify before citing.
- Yan, W. *Don't Build Multi-Agents.* Cognition blog, 12 Jun 2025. https://cognition.ai/blog/dont-build-multi-agents — **practice evidence, not peer-reviewed.**
- Siegel, Z.S., Kapoor, S., Nagdir, N., Stroebl, B., Narayanan, A. *CORE-Bench: Fostering the Credibility of Published Research Through a Computational Reproducibility Agent Benchmark.* TMLR 2024. arXiv:2409.11363.
- Starace, G., Jaffe, O., et al., Patwardhan, T. *PaperBench: Evaluating AI's Ability to Replicate AI Research.* arXiv:2504.01848, OpenAI.
- *ScienceAgentBench: Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery.* ICLR 2025. arXiv:2410.05080. **[unverified metadata]**
- *AstaBench: Rigorous Benchmarking of AI Agents with a Scientific Research Suite.* Allen Institute for AI. arXiv:2510.21652. **[unverified metadata]**

### Funding, eligibility, and expert matching

- **[B6]** Felfernig, A., Friedrich, G., Jannach, D., Zanker, M. *Constraint-Based Recommender Systems.* In *Recommender Systems Handbook.* DOI 10.1007/978-1-4899-7637-6_5. **[unverified metadata]**
- **[B7]** Jin, Q. et al. *Matching patients to clinical trials with large language models* (TrialGPT). Nature Communications, 2024. arXiv:2307.15051. https://www.nature.com/articles/s41467-024-53081-z **[unverified metadata — author list not fully confirmed]**
- **[B8]** *SatIR: Scalable High-Recall Constraint-Satisfaction-Based Information Retrieval for Clinical Trials Matching.* arXiv:2604.08849, 2026.
- **[B14]** Zeng, T., Acuna, D.E. *GotFunding: A grant recommendation system based on scientific articles.* Proc. Assoc. Inf. Sci. Technol. 57(1):e323, 2020. DOI 10.1002/pra2.323. arXiv:2405.12840. — nDCG@1 = 0.945 on NIH grant–publication data.
- **[B15]** *A Gold Standard Dataset for the Reviewer Assignment Problem.* arXiv:2303.16750. OpenReview: https://openreview.net/forum?id=XofMHO5yVY — misranking 12–30% (easy) / 36–43% (hard).
- **[B17]** *Traditional statistical representations outperform generative AI in identifying expert peer reviewers.* arXiv:2605.18752, 2026. — TF-IDF 79.5% vs GPT-4o mini 51.5% at top-25 expert recall.
- **[B21]** TREC Clinical Trials Track 2023. https://trec-cds.org/2023.html — ternary graded judgments (eligible=2, excluded=1, not relevant=0), nDCG@10 primary.
- **[B25]** Yang, Z., Zhao, Y., Liu, W., Li, X. *MERIT: Matching Expertise via Rubric-Informed Training for Reviewer Assignment.* arXiv:2605.27865, 2026. Code: https://github.com/Luli3220/MERIT
- **[B39]** *Matching Researchers to Funding Calls: A Reproducible Institution-Level Framework.* arXiv:2604.06321, 2026.
- **[B40]** *Automated Matchmaking of Researcher Biosketches and Funder Requests for Proposals Using Deep Neural Networks.* IEEE, 2024. https://ieeexplore.ieee.org/document/10597426/ **[unverified metadata]** — best model F1 = 71.15%.
- **[B45]** *Publication venue recommendation using profiles based on clustering.* arXiv:2401.10611, 2024. See also Yang, Z., Davison, B.D. *Venue Recommendation: Submitting Your Paper with Style.* ICMLA 2012.
- **[B46]** Burges, C.J.C. *From RankNet to LambdaRank to LambdaMART: An Overview.* Microsoft Research MSR-TR-2010-82. **[unverified metadata]** See also *Blending Learning to Rank and Dense Representations for Efficient and Effective Cascades*, arXiv:2510.16393.
- Zhang, Y. et al. *Chain-of-Factors Paper-Reviewer Matching.* WWW 2025. arXiv:2310.14483.
- Balog, K., Fang, Y., de Rijke, M., Serdyukov, P., Si, L. *Expertise Retrieval.* Foundations and Trends in IR 6(2-3):127–256, 2012. **[unverified metadata]**
- Charlin, L., Zemel, R. *The Toronto Paper Matching System: An automated paper-reviewer assignment system.* https://www.cs.toronto.edu/~lcharlin/papers/tpms.pdf **[unverified metadata]**
- Ghosh, S., Schneider, M., Reinicke, C., Eickhoff, C. *A Survey on LLM-Assisted Clinical Trial Recruitment.* IJCNLP-AACL 2025. arXiv:2506.15301.
- Mashayekhi, Y., Li, N., Kang, B., Lijffijt, J., De Bie, T. *A challenge-based survey of e-recruitment recommendation systems.* arXiv:2209.05112.
- *Reviewer assignment problem: A scoping review.* arXiv:2305.07887.

---

## 10. Methodology and Confidence

### What was done

**Repository analysis (Phase 0).** Full directory mapping; all dependency manifests read (`pyproject.toml` ×2, `package.json`, `uv.lock`, `compose.yaml`, `ops/compose.gpu.yaml`, `.env.example`, systemd units); all top-level documentation read (`README.md`, `AGENTS.md`, `docs/purpose.md`, `goals.md`, `architecture.md`, and index-level reads of `repo-map.md` and `changelog.md`); git history analyzed at summary level (426 commits, 31 May – 2 Aug 2026; churn by file; branch inventory). Two deep semantic passes were run by subagents over the ranking/matching machinery and over the agentic/ingestion/evaluation layers respectively, with file:line citation required for every claim. **All load-bearing negative findings were then independently re-verified by the auditor via direct grep**, specifically: absence of Neo4j usage, absence of any ANN index, the fusion constants and CombMNZ formula, the fellowship blend weights, the absence of IR-evaluation terms, and the test count (1,379).

**Adversarial verification pass.** A separate agent was tasked with falsifying this report against the repository: re-checking the fifteen most load-bearing file:line citations, diffing the readiness verdict line between §0 and §6.6, checking every bibliography tag for dangling or uncited entries, and auditing the arithmetic of the scorecard and work plan. It found eleven factual corrections, all of which have been applied. The three most consequential are recorded here for transparency, because each changed a conclusion: (i) the original draft claimed personal engagement events were logged but filtered out — in fact **no personal endpoint calls `record_event` at all**, which makes the L2 remediation new instrumentation rather than a one-line filter change; (ii) the original draft's paper-ingestion figure of ~300/run was drawn from a single low day and understated the median by roughly 3× — corrected upward, *against* the audit's own critical thrust; (iii) LLM coverage was corrected from ~9% to 8.2% and re-derived from all 30 logs rather than one. One claim the verifier challenged was re-checked and upheld: `build_bm25_index(list(pool.values()))` is at `pipeline.py:978` as originally cited.

**Literature search (Phases 2–3).** Three parallel searches covering scholarly recommendation and its evaluation critique; LLM agents, reranking, judging, and contamination; and funding/eligibility/expert matching. A fourth search covered venues and deadlines against live official sources. Search queries were derived from the seven claims in §1.6 and included canonical work, 2024–2026 state of the art, surveys, benchmarks, **negative-result and critique papers**, and adjacent-field terminology (clinical-trial matching, e-recruitment, reviewer assignment) chosen specifically to break terminology silos.

### Confidence, by section

| Section | Confidence | Basis |
|---|---|---|
| §1 Project characterization | **High** | Every architectural statement traces to a specific file and line; negative findings independently re-verified by grep |
| §1.5 Maturity table | **High** | Aspirational items confirmed absent by exhaustive grep, and corroborated by the project's own unchecked `docs/goals.md` items |
| §1.6 Claims | **Medium-high** | Derived by the auditor from code; the project has not endorsed them. A different reader might partition them differently, though the substance would be the same |
| §2–3 Literature | **Medium-high** | All papers retrieved this session. See "not verified" below |
| §4 Gaps | **Medium** | Absence of prior work is harder to establish than presence. G3 and G4 rest on negative search results |
| §5 Novelty | **High** for methodological (None) and empirical-realized (None); **Medium** for problem novelty, which depends on how thin the funding literature really is |
| §6 Readiness | **High** — the scorecard floors are matters of fact, not judgment |
| §6.4 Disqualifier #5 (contamination) | **Medium** — the exposure is established; its magnitude is **not determinable from the repository**, and cannot be, until the model is pinned |
| §7–8 | Not kept in this repository |

### What could not be verified

- **The identity of the LLM.** `LLM_MODEL` defaults to the empty string. Model family, size, and training cutoff are **not determinable from the repository**. This blocks any contamination assessment and is the single most consequential unknown in this audit.
- **Whether the system's recommendations are any good.** Not determinable — there is no measurement, and none can be reconstructed from the artifacts present.
- **Real user counts beyond the logs.** The logs are authoritative for 30 dated runs; whether other deployments exist is not determinable.
- **Full author lists and exact titles** for the entries marked **[unverified metadata]** in §9. Their existence and identifiers were confirmed via a search index; the abstract or author list was not independently fetched. **Re-check each before citing in a manuscript.**
- **The legal status of the Pivot-RP scrape.** Flagged as a risk; assessing it requires reading Clarivate's terms and is a question for the institution's counsel, not for this audit. This document does not constitute legal advice.

### Where the literature is genuinely contested

Presented as disputes, not resolved:

1. **Pointwise vs. listwise LLM reranking.** The consensus has been that listwise wins because LLMs judge relatively better than absolutely [B24]; [B19] shows the gap becoming statistically insignificant for many model×dataset pairs given a large ordinal space. Both sides agree this concerns *ordering*, and neither supports treating the emitted integer as a calibrated percentage.
2. **Whether format restriction degrades LLM reasoning.** [Tam et al., arXiv:2408.02442] reports significant degradation; the `.txt` rebuttal argues the comparison was not like-for-like and reports the opposite. Unresolved.
3. **General-purpose vs. domain-specific scientific embeddings.** arXiv:2507.10057 shows general encoders matching SPECTER2/SciNCL on abstract-to-abstract retrieval; ChEmbed (arXiv:2508.01643) shows +9 pp from domain adaptation where vocabulary is specialized. Applied to Mycelium: **BGE-small is a defensible choice, not a documented error — but it is an unmeasured risk**, and PubMed vocabulary is exactly the specialized-vocabulary case. The system has no instrument that would reveal whether the encoder is the bottleneck.
4. **Whether offline evaluation is meaningful in this subfield at all.** [B31] concludes it is "probably not suitable" for research-paper recommenders; the entire benchmark literature (§2.2) proceeds anyway. The practical resolution most groups adopt — and the one recommended here — is offline sanity checks *plus* a real user signal, never offline alone.

### Self-check

All fourteen items of the audit protocol were satisfied. Specifically: every architectural statement traces to a file or module; the implemented/aspirational table exists and flags six overstatements with ⚠️; seven falsifiable claims were extracted and searched; every cited paper was retrieved this session, with unverified metadata marked; three works that scoop or undercut the project are identified by name ([B1], [B26], and the multi-agent critique line), alongside an explicit statement that a good-faith search found no scoop for the two intersection claims, with the queries listed; the verdict states a position; exactly one readiness level (L1) is assigned with its blocking criterion named; all eight scorecard axes are scored with justification and the minimum identified; all eight hard disqualifiers were checked explicitly and reported, including the contamination check; distance is given in weeks per tier with a critical path and a cheapest decisive action; the readiness verdict line appears verbatim in §0 and §6.6; reshaping paths carried effort estimates and evaluation designs, and venue deadlines were verified against current sources (both now kept outside this repository).
