# Mycelium: 5-Month Development Roadmap

**June 14 – November 14, 2026**  ·  *First Draft Target*

This roadmap translates the Mycelium product brief, purpose, goals checklist, and API contract into a sequential 20-week plan. The structure follows the principle defined in the goals document: foundation and trust first, then profile and data boundaries, then research intelligence, evidence graphs, opportunity matching, and reports. Each month builds directly on the one before it.

---

## Monthly Overview

| Period | Theme | Primary Focus |
| :--- | :--- | :--- |
| **Month 1**<br>Jun 14 – Jul 14 | Foundation & Infrastructure | Project setup, Django architecture, auth system, data models, scraper framework for papers/grants/fellowships |
| **Month 2**<br>Jul 14 – Aug 14 | Lab Profile & Relevance Engine | Lab/researcher profiles, onboarding flows, embedding-based relevance scoring, filtering pipeline, permissions |
| **Month 3**<br>Aug 14 – Sep 14 | Knowledge Graph & Evidence Layer | Graph data model, entity relationships, claim/evidence modeling, cross-entity queries, graph-backed retrieval |
| **Month 4**<br>Sep 14 – Oct 14 | Digest, Reports & Opportunity Matching | Weekly digest pipeline, grant/fellowship scoring and explanation, proposal readiness, deadline planning, report generation |
| **Month 5**<br>Oct 14 – Nov 14 | Integration, Polish & First Draft Review | End-to-end testing, audit logging, basic dashboard/UI, documentation, first draft review, future planning |

---

## Week-by-Week Breakdown

### 📂 Month 1: Foundation & Infrastructure
*June 14 – July 14, 2026*

Establish project architecture, authentication, core data models, and the first working scrapers. Nothing user-facing yet — this is laying the reliable ground everything else will stand on.

**Month Goal:** Raw data flowing reliably into storage from at least 5 external sources. Auth system working end-to-end.

| Week | Dates | Tasks | Milestone / Deliverable | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Week 1** | Jun 14–20 | Finalize repo structure and tech stack decisions. Set up Django project with apps: auth, labs, scraper, graph, reports. Configure Postgres. Define environment and secrets management. | Django project running locally with Postgres connected | [ ] |
| **Week 2** | Jun 21–27 | Build auth system: session cookies, CSRF, login/logout/me endpoints per API contract. Set up user model. Write basic role scaffolding (PI, student, staff, admin). | Auth endpoints passing integration tests | [ ] |
| **Week 3** | Jun 28–Jul 4 | Define core data models: Paper, Grant, Fellowship, Lab, Person, Project, ResearchArea. Write migrations. Begin scraper framework: base scraper class, rate limiting, retry logic, source registry. | All core models migrated; base scraper framework in place | [ ] |
| **Week 4** | Jul 5–14 | Build and test scrapers for arXiv, Semantic Scholar, NIH Reporter, grants.gov, and one fellowship source (NSF GRFP or similar). Implement deduplication and raw ingestion to DB. Set up Celery for background jobs. | Month 1 complete — 5+ sources ingesting reliably | [ ] |

---

### 🧬 Month 2: Lab Profile & Relevance Engine
*July 14 – August 14, 2026*

Teach the system what a lab looks like and what matters to it. Build the profile layer and the relevance engine that turns raw data into filtered, ranked recommendations.

**Month Goal:** Given a lab profile, the system returns a filtered, ranked list of relevant papers, grants, and fellowships with scores and reasons.

| Week | Dates | Tasks | Milestone / Deliverable | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Week 5** | Jul 14–20 | Design Lab Profile schema: research areas, goals, active projects, methods, datasets, funding priorities, deadlines. Design individual ResearcherProfile: interests, skills, career goals, eligibility, academic stage. | Profile schemas defined and migrated | [ ] |
| **Week 6** | Jul 21–27 | Build profile onboarding flow (API endpoints + minimal input form or JSON config). Add object-level permissions: all lab-scoped objects enforce membership and role. Write permission tests. | Lab and researcher onboarding working with enforced permissions | [ ] |
| **Week 7** | Jul 28–Aug 3 | Implement relevance scoring: keyword overlap + embedding similarity (OpenAI or sentence-transformers). Score incoming papers, grants, fellowships against active lab profiles. Store scores and signal metadata. | Relevance scores generating for all incoming items | [ ] |
| **Week 8** | Aug 4–14 | Build filtering pipeline: threshold logic, noise reduction, deduplication across sources. Add tagging and category labeling. Log pass/fail decisions for tuning. Add profile review reminder flow (flag stale profiles). | Month 2 complete — filtered, scored item lists per lab profile | [ ] |

---

### 🕸️ Month 3: Knowledge Graph & Evidence Layer
*August 14 – September 14, 2026*

Connect entities into a living relationship layer. Model claims and evidence so the system can reason across relationships — not just retrieve isolated items.

**Month Goal:** The system answers at least 4 cross-entity relationship queries using the graph (e.g. papers connected to a project, grants matching a student's profile).

| Week | Dates | Tasks | Milestone / Deliverable | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Week 9** | Aug 14–20 | Choose graph approach (Neo4j, relational edge tables, or lightweight graph lib). Define node types: Lab, Person, Project, Paper, Grant, Fellowship, Topic, Claim. Define edge types: belongs_to, interested_in, authored_by, funds, matches, contradicts, supports. | Graph schema finalized and data store selected | [ ] |
| **Week 10** | Aug 21–27 | Build ingestion pipeline: load existing scraped data into graph nodes. Create edges from metadata (co-authors, research areas, funding agency to grant, etc.). Write basic traversal queries. | Existing scraped data loaded into graph with core edges | [ ] |
| **Week 11** | Aug 28–Sep 3 | Model claims and evidence: Claim node linked to Paper, Evidence, Method, Dataset, Limitation. Add confidence signals and source traceability. Add contradiction detection (same topic, conflicting claims). | Claim/evidence model working with traceable sources | [ ] |
| **Week 12** | Sep 4–14 | Build cross-entity queries powering future features: "What grants fit this lab's projects?" / "What papers support a student's research area?" / "What research gaps exist in our graph?". Write query tests. Document graph API. | Month 3 complete — 4+ cross-entity graph queries passing | [ ] |

---

### 📊 Month 4: Digest, Reports & Opportunity Matching
*September 14 – October 14, 2026*

Turn backend intelligence into readable, actionable output. Build the digest pipeline, opportunity scoring and explanation system, and structured reports a real lab could act on.

**Month Goal:** The system produces a readable, personalized weekly digest with papers, grants, and fellowships — each with clear relevance explanations and deadline flags.

| Week | Dates | Tasks | Milestone / Deliverable | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Week 13** | Sep 14–20 | Build weekly digest pipeline: collect filtered items since last digest, rank by relevance score + recency + deadline urgency. Add paper summaries with "why this matters" context tied to lab goals or projects. | Weekly digest generating for a test lab profile | [ ] |
| **Week 14** | Sep 21–27 | Build grant matching output: fit explanation, eligibility check, deadline flag, missing materials list. Build fellowship matching: student eligibility, career stage fit, mentor/topic fit, deadline. Score each opportunity across 7 dimensions (topic, eligibility, timing, evidence, team, budget, strategic fit). | Grant and fellowship outputs generating with scored explanations | [ ] |
| **Week 15** | Sep 28–Oct 4 | Add proposal readiness view: what is complete, partial, missing, risky, and urgent per opportunity. Add 30/60/90-day deadline planning. Generate action items by person, project, and deadline. | Proposal readiness and deadline planning working | [ ] |
| **Week 16** | Oct 5–14 | Build structured report output (Markdown + HTML or PDF export). Add scheduling layer for recurring digests (Celery beat). Add audit logging for document access, report exports, profile changes, and generated recommendations. | Month 4 complete — scheduled, exportable digest and reports | [ ] |

---

### 🏁 Month 5: Integration, Polish & First Draft Review
*October 14 – November 14, 2026*

Close the loop end-to-end. Test the system against real lab use cases, document what works and what is stubbed, and conduct the first draft review against the original product brief.

**Month Goal:** End-to-end system working: onboard a lab → scrape → filter → graph → digest. First draft review complete with written gap analysis.

| Week | Dates | Tasks | Milestone / Deliverable | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Week 17** | Oct 14–20 | Full end-to-end test pass: onboard lab profile → scrape sources → filter and score → load graph → generate digest → export report. Fix brittle scrapers, broken flows, and permission gaps surfaced during testing. | End-to-end flow passing with a real or realistic lab profile | [ ] |
| **Week 18** | Oct 21–27 | Build minimal UI entry point: basic web dashboard or CLI for lab onboarding, profile editing, digest viewing, and opportunity browsing. Add monitoring, structured logs, error tracking, and job status visibility. | Minimal working UI / entry point accessible to a test user | [ ] |
| **Week 19** | Oct 28–Nov 3 | Harden background jobs: source freshness tracking, last-checked dates, retry logic, dead-letter handling. Verify audit logs are complete. Add basic operational runbook. Security review: permission boundaries, session handling, CSRF. | Background jobs stable; audit logs verified; security review complete | [ ] |
| **Week 20** | Nov 4–14 | Write architecture overview, setup guide, and data flow documentation. Draft future-planning section for Discord/Slack integration approach. Conduct first draft review: does the system fulfill the core brief? Write gap analysis and next-phase priorities. | Month 5 complete — First Draft Done. Gap analysis written. | [ ] |

---

## Key Principles for This Roadmap

*   **Sequence matters:**
    *   Auth and permissions before any lab data is exposed — object-level enforcement is non-negotiable from Week 2 onward.
    *   Scrapers before relevance scoring — you cannot filter what you have not collected.
    *   Profiles before the knowledge graph — the graph needs entities to connect.
    *   Digest generation before dashboards — prove the intelligence works before building the UI around it.
*   **What is deferred intentionally:**
    *   Discord / Slack integration — design the approach in Month 5, build in a later phase.
    *   Full dashboard UI — a minimal entry point is sufficient for the first draft.
    *   Publication pipeline tracking, skill matrix, strategic planning agent — long-term features per goals checklist.
    *   Real-time collaboration — background jobs and digests cover the first-draft scope.

---

## Checkpoints

*   **End of Month 1:** Raw data flowing from 5+ sources. Auth working.
*   **End of Month 2:** Filtered, scored item lists generating per lab profile.
*   **End of Month 3:** 4+ cross-entity graph queries passing.
*   **End of Month 4:** Exportable weekly digest with opportunity scoring live.
*   **End of Month 5:** End-to-end flow verified. Gap analysis and first draft review complete.

---
*Mycelium Roadmap  ·  Generated June 2026  ·  First draft target: November 14, 2026*
