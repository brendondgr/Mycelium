# Mycelium Goals

Mycelium should grow from a clear product foundation into a secure, useful,
open-source academic research assistant that any lab can run on its own
computers: helping research labs understand their goals, people,
projects, literature, evidence, funding opportunities, and next actions as one
connected system.

**First draft target:** June 14 – **November 14, 2026** — an end-to-end system
that can onboard a lab, ingest external sources, filter and score items, connect
entities in a graph, and produce a personalized digest with opportunity matching
and exportable reports.

**Status of this document:** current as of **August 4, 2026**. It records what is
built and what is next. It is not a task tracker — see
[`changelog.md`](changelog.md) for what happened.

## Build sequence rules

These ordering rules apply throughout the first draft and should not be reversed:

- Auth and object-level permissions before any lab-scoped data is exposed.
- Scrapers and raw ingestion before relevance scoring — you cannot filter what
  you have not collected.
- Lab and researcher profiles before the knowledge graph — the graph needs
  entities to connect.
- Digest generation and report output before a full dashboard — prove the
  intelligence works before building UI around it.
- Audit logging alongside sensitive workflows, not as an afterthought.

## Product foundation

These hold throughout and should stay true of every change:

- Mycelium is an open-source academic research assistant that any lab can run on
  its own computers, not a generic paper search tool or chatbot. It is the
  grounding layer (corpus, profiles, graph, feeds, evaluation harness) that
  research tools are built on.
- Primary users: principal investigators, students, postdocs, research staff,
  grant writers, collaborators, and lab administrators.
- The core promise: connect lab context with literature, evidence, funding,
  fellowships, reports, and strategy.
- The trust model: recommendations must be explainable, source-aware,
  permission-aware, and honest about uncertainty.
- The brand is calm organic intelligence — scholarly, warm, botanical,
  professional. Mylo is the mushroom scout who searches, connects, alerts, and
  guides. See [`styles.md`](styles.md).
- Security, privacy, accessibility, and responsive usability are first-class
  requirements, not a later pass.
- Keep validating against the core question: does this help a real lab decide
  what to read, fund, write, submit, or work on next?

## Built

**Modular tools.** Research capabilities are tools under `tools/`, one
self-contained folder each, declared by one class and loaded by discovery. An
import script probes every tool before anything runs it, so a tool that cannot
load is set aside (or, if the platform needs it, stops startup with the reason)
and nothing depending on it runs. Each tool has its own `[tools.<name>]` section
in `mycelium.toml` and declares its own nightly stages. The first three are the
layers Mycelium already had: retrieval (the corpus), recommendation (ranking
against profiles) and delivery (feeds, reports, reminders, announcements).

**Foundation & identity.** Monorepo, service boundaries, Compose stack, and
secrets management. Session auth with CSRF, a configurable sign-up gate (its
shared-code mode has a shadow-ban lockout), users, labs, departments, memberships, permission roles,
academic titles, audit events, and lab invitations. Object-level permissions on
the profile, lab, department, project, and reminder surfaces.

**Ingestion.** OpenAlex / PubMed / Semantic Scholar paper scrapers behind a
registry with rate limiting, retry/backoff, a publication-date scan window, and
cross-source plus against-store deduplication. Grants and conferences come from
an open collector of public HTTP sources needing no login or licence — five live
grant adapters and six conference adapters — carrying per-record source links and
licence, CCF / CORE / THCPL rankings where a series has them, and every
deadline round rather than one. Expiry is
driven by the written deadline, never the posted date: a multi-round grant
survives to its last round while the reader is shown the next one, and a
conference is surfaced on its next submission deadline, never its event date.
Fellowships come from the Illinois Fellowship Finder. Every grant and conference
description is a model-written extraction under a fixed schema, verified by
deterministic checks before it is shown or embedded; a record that fails them is
refused, falls back to raw text, and shows no summary. An external DOI / arXiv /
URL resolver handles pasted links.

**Profiles.** Author import from four sources plus optional résumé parsing (read
and discarded, never stored), LLM synthesis of the full interest profile with a
deterministic fallback, and the v2 interests contract — themed **clusters** of
concrete sub-topics. The same reasoning drives onboarding's "tell Mylo what you
want to research" box and the initial profile build. Editing is one tabbed modal
for people and one for labs; projects carry their own focus.

**Relevance engine.** Per-interest retrieval fusing BM25 lexical and pgvector
semantic channels via RRF, cluster-scoped scoring with argmax attribution and
bridge clusters, LLM percent-match scoring and written reasons for the top items,
and a deterministic tail. Scored for three target kinds — user, lab, and project
— over four areas: papers, grants, fellowships, conferences. Fellowships add a
deterministic eligibility rule engine for people; labs and projects rank them on
research fit alone.

**Evaluation.** A reusable retrieval harness (`eval/`) that scores the production
ranking stack against LongEval-Sci with `ir_measures`, emits TREC run files and
`ir_metadata`, and accumulates a committed score history keyed by git SHA. Five
arms, each a thin call into production code, so re-measuring after a ranking
change is one command. See `docs/evaluation.md` for the claims boundary.

**Delivery.** Four in-app feeds with search, cluster chips, filter rails, and
infinite reveal. A sectioned written daily briefing per user and per lab. A
rendered PDF report DM'd to linked users and attached to a lab's Discord channel
beneath a counts-by-theme summary. Saves, addressable deadlines, and
Discord-delivered reminders with lead times, snoozing, and a manage page.
Unified query-first search over the whole corpus. A "who is this for?" member-fit
layer on every lab feed.

**Collaboration.** A team-fit line on every grant (which of a call's
requirements the reader or their lab covers). An opt-in, expiring "open to
collaboration" setting scoped by verified institution, with a weekly exposure
cap and a preview. An institution is proved by a verified email, never typed,
and people are suggested only to someone verified at one — from the same
institution or, at widest, the same country. A collaborator search from a call, a project or one's own
words — four lanes, a hard consent gate, coarse pointers only — with
introductions through consenting co-authors, "outside my network", and team
proposals. Six harm checks run daily. Built and validated on synthetic worlds;
outward search ships switched off (`COLLAB_SEARCH_ENABLED`).

**Operations & commerce.** One instance configuration (`mycelium.toml`, see
[`configuration.md`](configuration.md)) with four deployment profiles, five
sign-up modes, optional email verification, every limit off unless set, a
nightly model-call budget, and a CLI and agent skill to change it. Billing is a
module that file switches on: tiered subscriptions with per-seat billing for
labs and departments, add-ons, and entitlements enforced in the API, both daily
pipelines, and the frontend. A staff-only admin API for rosters, plan
assignment, and watch quotas. Discord identity linking by three paths, guild
activation, slash commands, a durable outbox with drift detection, and a host
daily run with error reporting and run state. A load-test harness for onboarding
(see [`loadtest.md`](loadtest.md)).

## Not built

- **Knowledge graph & evidence layer.** *Partly built (2026-09-18).* The graph
  itself exists in Postgres (`apps/knowledge`): concepts, typed edges with an
  evidence tier (declared, demonstrated, conversational), declared profiles and
  projects loaded, people's own papers read into demonstrated edges, and the
  four cross-entity queries (Q1–Q4) proven — validated on synthetic worlds of
  up to 600 people and 150 calls (`EXP-2026-09-005` to `-010`). Who published
  with whom is a Postgres table too; Neo4j was benchmarked and not needed
  (`EXP-2026-09-011`, decision D-007). Claim and evidence modeling and
  contradiction detection are outstanding.
- **Object storage.** MinIO runs; nothing writes to it. Uploads, exports, and
  generated artifacts live on the filesystem or in Postgres.
- **Proposal readiness & deadline planning.** 30/60/90-day planning, "what is
  complete / partial / missing / risky", and generated action items by person and
  project.
- **Living reports.** Literature reviews, funding briefs, proposal support, and
  annual summaries as durable, exportable documents — distinct from the daily
  briefing that exists.
- **Human review gates** before a report, alert, or graph update becomes
  authoritative.
- **Operational hardening.** Dead-letter handling, runbooks, structured job-status
  visibility, and a security review of permission boundaries end to end.
- **Slack integration**, the
  skill matrix, publication-pipeline tracking, student development support, and
  the strategic planning agent.

## Next

In rough order, against the November 14 target:

1. Close the graph gap: choose the approach, define node and edge types, load
   existing content, and prove four cross-entity queries. *Approach, types,
   declared content, and Q1–Q4 done (collaboration-network CN-01 to CN-05).*
2. Model claims and evidence so every generated statement is traceable to a
   source, a finding, and a confidence signal.
3. Turn the daily briefing into durable, exportable reports with human review
   before they become authoritative.
4. Add proposal readiness and deadline planning on top of the deadline data that
   already exists.
5. Harden operations — job status, dead-letter handling, runbooks, and a full
   permission/session/CSRF security review.
6. Run the first-draft review against the product brief and write the gap
   analysis.

## Tools on the grounding layer

Planned, not built. Each is built as a tool under `tools/` (start with
`make new-tool`; rules in [`skills/tools.md`](skills/tools.md)). Each one reads the lab's context from Mycelium and is held
to a public benchmark before it is called working. Results go in
`docs/research/` like any other experiment.

| Tool | What it reads from Mycelium | Proven against |
|---|---|---|
| Claim and citation-stance engine: does a later paper support, dispute, or only mention a claim? Built together with the hypothesis engine, since contested or unresolved claims are the best seeds for a hypothesis. Also closes the claims-and-evidence gap above | Corpus, retrieval, the graph | SciCite and MultiCite, plus a hand-labelled sample |
| Systematic-review screening: rank thousands of abstracts so reviewers read the likely includes first | The ranking stack and `eval/` | CLEF TAR and SYNERGY, scored as work saved at 95% recall |
| Expertise finder: who works on X, which teams could go after this call | Author import, co-authorship, collaborator search, grant matching | Recovering held-out collaborations or funded teams |
| Literature-mined domain databases: structured facts pulled from papers at scale | The schema-based extraction with deterministic checks already used for grants | Precision against an existing curated database |
| Internal funding and limited-submission matching | The grant feed and the eligibility rule engine | Low compute; a quick win |

The hypothesis engine is evaluated with a time split: freeze the corpus at a
date, ask for hypotheses, then score them against what was published after that
date. The corpus and graph carry dates, so the split is possible.

Deliberately left out: protein structure and docking (strong open tools exist),
generic "chat with your PDFs" (commoditized and blind to lab context), and AI
peer review (funder and journal policies restrict it).
