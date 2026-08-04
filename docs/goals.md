# Mycelium Goals

Mycelium should grow from a clear product foundation into a secure, useful lab
intelligence platform: helping research labs understand their goals, people,
projects, literature, evidence, funding opportunities, and next actions as one
connected system.

**First draft target:** June 14 – **November 14, 2026** — an end-to-end system
that can onboard a lab, ingest external sources, filter and score items, connect
entities in a graph, and produce a personalized digest with opportunity matching
and exportable reports.

**Status of this document:** current as of **August 4, 2026**. It records what is
built and what is next. It is not a task tracker — see
[`changelog.md`](changelog.md) for what happened and
[`chats/mycelium_roadmap.md`](chats/mycelium_roadmap.md) for the original
week-by-week roadmap this project was sequenced against.

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

- Mycelium is a lab intelligence platform for research teams, not a generic paper
  search tool or chatbot.
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

**Foundation & identity.** Monorepo, service boundaries, Compose stack, and
secrets management. Session auth with CSRF, an invite-only sign-up gate with a
shadow-ban lockout, users, labs, departments, memberships, permission roles,
academic titles, audit events, and lab invitations. Object-level permissions on
the profile, lab, department, project, and reminder surfaces.

**Ingestion.** OpenAlex / PubMed / Semantic Scholar paper scrapers behind a
registry with rate limiting, retry/backoff, a publication-date scan window, and
cross-source plus against-store deduplication. Pivot-RP (ProQuest) ingest for
grants, conferences, and fellowships, plus the Illinois Fellowship Finder source.
An external DOI / arXiv / URL resolver for pasted links.

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

**Delivery.** Four in-app feeds with search, cluster chips, filter rails, and
infinite reveal. A sectioned written daily briefing per user and per lab. A
rendered PDF report DM'd to linked users and attached to a lab's Discord channel
beneath a counts-by-theme summary. Saves, addressable deadlines, and
Discord-delivered reminders with lead times, snoozing, and a manage page.
Unified query-first search over the whole corpus. A "who is this for?" member-fit
layer on every lab feed.

**Operations & commerce.** Tiered subscriptions with per-seat billing for labs
and departments, add-ons, and entitlements enforced in the API, both daily
pipelines, and the frontend. A staff-only admin API for rosters, plan
assignment, and watch quotas. Discord identity linking by three paths, guild
activation, slash commands, a durable outbox with drift detection, and a host
daily run with error reporting and run state. A load-test harness for onboarding
(see [`loadtest.md`](loadtest.md)).

## Not built

- **Knowledge graph & evidence layer.** Neo4j runs in Compose but no code uses
  it. Node/edge types, claim and evidence modeling, contradiction detection, and
  cross-entity queries are all outstanding. This is the largest remaining gap
  against the first-draft target.
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
- **Slack integration**, collaboration suggestions from missing expertise, the
  skill matrix, publication-pipeline tracking, student development support, and
  the strategic planning agent.

## Next

In rough order, against the November 14 target:

1. Close the graph gap: choose the approach, define node and edge types, load
   existing content, and prove four cross-entity queries.
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
