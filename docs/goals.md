# Mycelium Goals

Mycelium should grow from a clear product foundation into a secure, useful lab intelligence platform. The work should begin with the core promise: helping research labs understand their goals, people, projects, literature, evidence, funding opportunities, and next actions as one connected system.

The product should be built in a deliberate order. First, establish the identity and trusted public explanation. Next, create the private workspace and data boundaries that make lab-specific intelligence possible. Then layer in research monitoring, evidence graphs, grants, fellowships, reports, and strategic recommendations. Later, expand toward collaboration, publication planning, student development, and deeper lab operations.

The checklist below is chronological by week. It is meant to guide what should generally be made next, not prescribe implementation files. Task-level detail and status tracking live in `docs/chats/mycelium_roadmap.md`.

## First Draft Target

**June 14 – November 14, 2026** · **November 14, 2026** — end-to-end system that can onboard a lab, ingest external sources, filter and score items, connect entities in a graph, and produce a personalized weekly digest with opportunity matching and exportable reports.

## Progress (as of June 21, 2026)

Ahead of the weekly sequence, the full relational data model is implemented across the `accounts`, `research`, `content`, and `billing` apps and verified on SQLite and Postgres:

- **Organization & identity** — departments, labs, lab and department memberships, permission roles, academic titles, and PI lead flags.
- **Research context** — one profile per user (interests, skills, eligibility, funding needs, and an interest embedding) and projects scoped to a user, lab, or department.
- **Matching layer** — deduplicated content items (papers, grants, fellowships) and per-target relevance scores, with `pgvector` embedding columns staged for scoring.
- **Billing & entitlements** — subscriptions and per-seat billing, tier-based feature resolution, and derived department membership.

The database is seeded with several hundred demo users across varied lab and department arrangements for exploration. Relevance scoring, scrapers, the knowledge graph, and onboarding UI remain to be built per the weekly plan below.

## Build Sequence

These ordering rules apply throughout the first draft and should not be reversed:

- Auth and object-level permissions before any lab-scoped data is exposed.
- Scrapers and raw ingestion before relevance scoring — you cannot filter what you have not collected.
- Lab and researcher profiles before the knowledge graph — the graph needs entities to connect.
- Digest generation and report output before a full dashboard — prove the intelligence works before building UI around it.
- Audit logging alongside sensitive workflows, not as an afterthought.

## Product Foundation

These goals run in parallel with the weekly plan and should stay aligned throughout the first draft.

- [ ] Define the product as a lab intelligence platform for research teams, not a generic paper search tool or chatbot.
- [ ] Clarify the primary users: principal investigators, students, postdocs, research staff, grant writers, collaborators, and lab administrators.
- [ ] Establish the core promise: connect lab context with literature, evidence, funding, fellowships, reports, and strategy.
- [ ] Define the trust model: recommendations must be explainable, source-aware, permission-aware, and honest about uncertainty.
- [ ] Establish the brand identity as calm organic intelligence: scholarly, warm, botanical, professional, and memorable.
- [ ] Lock the light and dark visual palettes so future interface work stays consistent.
- [ ] Treat Mylo as the mushroom scout and product agent who searches, connects, alerts, and guides.
- [ ] Build public-facing pages that explain the product clearly, show credible use cases, and demonstrate real outputs.
- [ ] Show product value with realistic dashboard previews, sample research briefs, grant matches, fellowship matches, and evidence trails.
- [ ] Keep security, privacy, accessibility, and responsive usability as first-class product requirements throughout the work.
- [ ] Continue validating the product against its core question: does this help a real lab decide what to read, fund, write, submit, or work on next?

## Week-by-Week Checklist

### Month 1: Foundation & Infrastructure
*June 14 – July 14, 2026*

Establish project architecture, authentication, core data models, and the first working scrapers. Nothing user-facing yet — this is laying the reliable ground everything else will stand on.

**Month goal:** Raw data flowing reliably into storage from at least 5 external sources. Auth system working end-to-end.

#### Week 1 · Jun 14–20

- [x] Finalize repo structure and tech stack: Django backend, Postgres, Celery, and clear app boundaries. *(As built: identity and labs consolidated into `accounts`; `core`, `research`, `content`, and `billing` apps added; `scraper`, `graph`, and `reports` remain planned. Documented in [architecture.md](architecture.md).)*
- [x] Separate public content, authenticated app behavior, backend orchestration, background work, and data storage responsibilities.
- [x] Configure Postgres and define environment and secrets management. *(`django-environ` with a git-ignored `.env`; variables documented in `.env.example`.)*

**Milestone:** Django project running locally with Postgres connected. *(Verified — Postgres with pgvector enabled.)*

#### Week 2 · Jun 21–27

- [x] Build account, lab, membership, and role foundations before exposing private lab information.
- [x] Implement auth per the API contract: session cookies, CSRF, login/logout/me endpoints, and role scaffolding (PI, student, staff, admin).

**Milestone:** Auth endpoints passing integration tests. *(Done — session auth plus the organization model land with permission roles and academic titles.)*

#### Week 3 · Jun 28–Jul 4

- [x] Define core data models: Paper, Grant, Fellowship, Lab, Person, Project, and ResearchArea. *(As built: a unified ContentItem covers papers, grants, and fellowships; Lab and Project are implemented; research areas are captured as profile and project interests; Person is deferred to the graph phase.)*
- [x] Add project visibility over the org hierarchy: members see their projects, lab heads see their lab's projects, and a department head always sees every project of every lab under them (`Project.objects.visible_to`).
- [x] Give content items a per-source dedup key (`source` + `external_id`, plus `source_url`) so re-scraping upserts instead of duplicating. *(The Week 4 deduplication item builds on this.)*
- [ ] Build the scraper framework: base scraper class, rate limiting, retry logic, and source registry.

**Milestone:** All core models migrated; base scraper framework in place.

#### Week 4 · Jul 5–14

- [ ] Ingest from at least five external sources: arXiv, Semantic Scholar, NIH Reporter, grants.gov, and one fellowship source (NSF GRFP or similar).
- [ ] Implement deduplication and reliable raw ingestion into durable storage.
- [ ] Set up Celery for background jobs.

**Milestone:** Month 1 complete — 5+ sources ingesting reliably.

---

### Month 2: Lab Profile & Relevance Engine
*July 14 – August 14, 2026*

Teach the system what a lab looks like and what matters to it. Build the profile layer and the relevance engine that turns raw data into filtered, ranked recommendations.

**Month goal:** Given a lab profile, the system returns a filtered, ranked list of relevant papers, grants, and fellowships with scores and reasons.

#### Week 5 · Jul 14–20

- [ ] Create lab profiles that capture research areas, goals, projects, methods, datasets, tools, funding priorities, collaborators, deadlines, and strategic needs. *(Partial: lab-scoped Projects carry goals, methods, datasets, deadlines, and strategic needs; a consolidated lab-profile surface and shared-profile content are still to come.)*
- [x] Create individual researcher profiles that capture interests, skills, career goals, projects, eligibility constraints, funding needs, and development plans.

**Milestone:** Profile schemas defined and migrated. *(Researcher Profile schema done and migrated.)*

#### Week 6 · Jul 21–27

- [ ] Build profile onboarding flow (API endpoints and minimal input surface).
- [ ] Enforce object-level permissions for every lab-scoped object and action.

**Milestone:** Lab and researcher onboarding working with enforced permissions.

#### Week 7 · Jul 28–Aug 3

- [ ] Implement relevance scoring using keyword overlap and embedding similarity against active lab profiles.
- [ ] Score incoming papers, grants, and fellowships and store scores with signal metadata.

**Milestone:** Relevance scores generating for all incoming items.

#### Week 8 · Aug 4–14

- [ ] Build the filtering pipeline: threshold logic, noise reduction, deduplication across sources, tagging, and category labeling.
- [ ] Log pass/fail scoring decisions so relevance tuning is auditable.
- [ ] Add regular profile review flows so lab goals, student interests, project status, and opportunity needs do not drift out of date.

**Milestone:** Month 2 complete — filtered, scored item lists per lab profile.

---

### Month 3: Knowledge Graph & Evidence Layer
*August 14 – September 14, 2026*

Connect entities into a living relationship layer. Model claims and evidence so the system can reason across relationships — not just retrieve isolated items.

**Month goal:** The system answers at least 4 cross-entity relationship queries using the graph.

#### Week 9 · Aug 14–20

- [ ] Choose and implement a graph approach (Neo4j, relational edge tables, or a lightweight graph library).
- [ ] Define node types: Lab, Person, Project, Paper, Grant, Fellowship, Topic, and Claim.
- [ ] Define edge types: belongs_to, interested_in, authored_by, funds, matches, contradicts, and supports.

**Milestone:** Graph schema finalized and data store selected.

#### Week 10 · Aug 21–27

- [ ] Load existing scraped data into graph nodes and create edges from metadata (co-authors, research areas, funding agency links, and similar).
- [ ] Track papers as part of a research map rather than a flat reading list.

**Milestone:** Existing scraped data loaded into graph with core edges.

#### Week 11 · Aug 28–Sep 3

- [ ] Model claims, evidence, findings, methods, datasets, metrics, limitations, contradictions, and relevance to lab projects.
- [ ] Make every generated research claim traceable to supporting sources, specific findings, limitations, and confidence signals.
- [ ] Add contradiction detection for conflicting claims on the same topic.

**Milestone:** Claim/evidence model working with traceable sources.

#### Week 12 · Sep 4–14

- [ ] Use graph relationships to improve retrieval, evidence organization, contradiction detection, and research gap discovery.
- [ ] Keep raw documents, semantic retrieval, structured relationships, and durable application records conceptually separate.
- [ ] Build cross-entity queries (for example: grants fit for lab projects, papers supporting a student's research area, research gaps in the graph).

**Milestone:** Month 3 complete — 4+ cross-entity graph queries passing.

---

### Month 4: Digest, Reports & Opportunity Matching
*September 14 – October 14, 2026*

Turn backend intelligence into readable, actionable output. Build the digest pipeline, opportunity scoring and explanation system, and structured reports a real lab could act on.

**Month goal:** The system produces a readable, personalized weekly digest with papers, grants, and fellowships — each with clear relevance explanations and deadline flags.

#### Week 13 · Sep 14–20

- [ ] Build the first useful research workflow around a weekly lab intelligence digest.
- [ ] Include new papers relevant to lab goals, project needs, research questions, and member interests.
- [ ] Rank digest items by relevance score, recency, and deadline urgency with clear "why this matters" context.

**Milestone:** Weekly digest generating for a test lab profile.

#### Week 14 · Sep 21–27

- [ ] Add grant discovery that matches opportunities to lab goals, projects, evidence, team strengths, budget needs, and timing.
- [ ] Add fellowship discovery that matches opportunities to individual members, academic stage, eligibility rules, deadlines, mentor fit, and career goals.
- [ ] Score opportunities by topic fit, eligibility fit, timing fit, evidence fit, team fit, budget fit, and strategic fit.
- [ ] Explain every opportunity match with clear reasons, missing materials, deadline risk, and human-verification needs.

**Milestone:** Grant and fellowship outputs generating with scored explanations.

#### Week 15 · Sep 28–Oct 4

- [ ] Add proposal readiness views that show what is complete, partial, missing, risky, and urgent.
- [ ] Add deadline planning across the next 30, 60, and 90 days.
- [ ] Generate action items by person, project, opportunity, and deadline.

**Milestone:** Proposal readiness and deadline planning working.

#### Week 16 · Oct 5–14

- [ ] Add reports that can become living literature reviews, funding briefs, proposal support, annual summaries, and project updates.
- [ ] Support human review before important reports, graph updates, alerts, and recommendations become authoritative.
- [ ] Schedule recurring digests and report generation through background jobs.
- [ ] Add audit logging for sensitive actions such as document access, profile changes, report exports, membership updates, and generated recommendations.

**Milestone:** Month 4 complete — scheduled, exportable digest and reports.

---

### Month 5: Integration, Polish & First Draft Review
*October 14 – November 14, 2026*

Close the loop end-to-end. Test the system against real lab use cases, document what works and what is stubbed, and conduct the first draft review against the original product brief.

**Month goal:** End-to-end system working: onboard a lab → scrape → filter → graph → digest. First draft review complete with written gap analysis.

#### Week 17 · Oct 14–20

- [ ] Verify the full end-to-end flow: onboard lab profile → scrape sources → filter and score → load graph → generate digest → export report.
- [ ] Fix brittle scrapers, broken flows, and permission gaps surfaced during testing.

**Milestone:** End-to-end flow passing with a real or realistic lab profile.

#### Week 18 · Oct 21–27

- [ ] Build a minimal UI entry point (basic web dashboard or CLI) for lab onboarding, profile editing, digest viewing, and opportunity browsing.
- [ ] Add monitoring, structured logs, error tracking, and job status visibility.

**Milestone:** Minimal working UI entry point accessible to a test user.

#### Week 19 · Oct 28–Nov 3

- [ ] Harden background jobs for literature scans, opportunity refreshes, graph updates, report generation, and scheduled digests.
- [ ] Track source freshness, last-checked dates, deadlines, confidence, and human verification for opportunities.
- [ ] Add dead-letter handling and basic operational runbooks.
- [ ] Conduct a security review of permission boundaries, session handling, and CSRF protection.

**Milestone:** Background jobs stable; audit logs verified; security review complete.

#### Week 20 · Nov 4–14

- [ ] Write architecture overview, setup guide, and data flow documentation.
- [ ] Draft the future approach for Discord and Slack integration without building it yet.
- [ ] Conduct the first draft review against the product brief and write a gap analysis with next-phase priorities.

**Milestone:** First draft done — gap analysis written.

---

## Later Phase

These features belong after the first draft. Design or note them where helpful, but do not block the November 14 target on them.

- [ ] Add full dashboards that answer what changed, what matters, what needs review, and what the lab should do next.
- [ ] Add Discord and Slack integration for alerts and digests.
- [ ] Add collaboration suggestions based on missing expertise, adjacent researchers, team skills, project needs, and proposal requirements.
- [ ] Add a skill matrix that shows current strengths, gaps, training needs, and possible internal collaborators.
- [ ] Add publication pipeline tracking from idea through outline, evidence gathering, experiments, drafting, submission, revision, and acceptance.
- [ ] Add conference, workshop, journal, travel award, and special-issue alerts for students and researchers.
- [ ] Add student development support that recommends papers, training, writing targets, fellowship angles, collaborators, and milestones.
- [ ] Add a strategic planning agent that combines lab goals, member interests, recent literature, funding opportunities, evidence gaps, and available skills.
- [ ] Add real-time collaboration beyond background jobs and scheduled digests.

## Checkpoints

- **End of Month 1:** Raw data flowing from 5+ sources. Auth working.
- **End of Month 2:** Filtered, scored item lists generating per lab profile.
- **End of Month 3:** 4+ cross-entity graph queries passing.
- **End of Month 4:** Exportable weekly digest with opportunity scoring live.
- **End of Month 5:** End-to-end flow verified. Gap analysis and first draft review complete.
