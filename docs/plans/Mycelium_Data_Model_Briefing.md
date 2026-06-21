# Mycelium — Core Data Model Briefing

**Scope:** Relational data model for organization structure, profiles, projects, relevance scoring, and billing
**Status:** Design agreed — ready to translate into Django models / migrations
**Last updated:** June 21, 2026

---

## Table of contents

1. [Purpose & scope](#1-purpose--scope)
2. [Design principles](#2-design-principles)
3. [Entities](#3-entities)
4. [Relationships](#4-relationships)
5. [Roles & titles](#5-roles--titles)
6. [Projects & relevance scoring](#6-projects--relevance-scoring)
7. [Billing, tiers & entitlements](#7-billing-tiers--entitlements)
8. [Institution (deferred)](#8-institution-deferred)
9. [Implementation notes](#9-implementation-notes)
10. [Decisions log](#10-decisions-log)
11. [Open questions & deferred scope](#11-open-questions--deferred-scope)

---

## 1. Purpose & scope

This document defines the **relational core** that the rest of Mycelium stands on: who the users are, how they organize into labs and departments, how their research interests and projects are captured, how content gets scored for relevance, and how all of that maps to billing.

**In scope:**
- Identity & organization (User, Lab, Department, memberships)
- Research context (Profile, Project)
- Matching layer (RelevanceScore against content)
- Billing & entitlements (Subscription, Seat, tier gating)

**Out of scope (pointers only):**
- Knowledge graph node/edge schema (lives in Neo4j — see graph phase). Note the graph's `Person` node is broader than `User`: it includes external co-authors who never hold accounts.
- Scraper/ingestion schemas and source registry
- Digest generation, scheduling, and delivery internals
- Mylo Bot integration

---

## 2. Design principles

These five commitments shape every table below.

1. **Title and role are separate concerns.** A person's *academic title* (career stage) lives on the `User`; their *permission role* lives on each membership. A PI can lead one lab and be a plain member of a collaborator's.

2. **Control flows down through ownership.** A `Department` has a single controlling owner who manages which labs belong to it and who its direct members are. A `Lab` optionally belongs to a department.

3. **Four relationships are polymorphic** — same pattern, four places:
   - A `Project` is scoped to a User, a Lab, or a Department.
   - A `RelevanceScore` targets a User's interests, a Project, a Lab, or a Department.
   - A `Subscription` is scoped to a User, a Lab, or a Department.
   - A `Seat`'s *payer* is a Department, a Lab, or the member themselves.

4. **Structure is decoupled from intelligence.** Labs and departments can exist regardless of payment. What a `Subscription` unlocks is the *shared intelligence layer* (shared profile/goals, shared evidence graph, cross-member suggestions, bot). Unpaid org structures degrade gracefully to "a set of individuals." Who is *charged* for a given member is a separate concern again, recorded per `Seat` (see §7).

5. **Derive, don't duplicate.** A department's effective membership is computed (direct members + members of its labs, deduplicated), not stored as redundant rows.

---

## 3. Entities

### USER
The account and the person's research identity. One profile per user.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `name` | string | |
| `email` | string | unique |
| `academic_title` | enum | `student` / `postdoc` / `researcher` / `pi` / `staff` — drives fellowship/stage matching |
| `institution` | string (nullable) | denormalized attribute, not a controlled entity (see §8) |
| `created_at` | timestamp | |

### DEPARTMENT
A top-of-hierarchy container, controlled by one user.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `owner_id` | uuid (FK → User) | the controlling user |
| `name` | string | |
| `institution` | string (nullable) | denormalized |
| `created_at` | timestamp | |

### LAB
A research group. May or may not belong to a department.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `department_id` | uuid (FK → Department, nullable) | set/cleared by the department owner |
| `name` | string | |
| `slug` | slug | unique |
| `created_at` | timestamp | |

### LAB_MEMBERSHIP
Join between a user and a lab. (Already exists in the `accounts` app.)

| Field | Type | Notes |
|---|---|---|
| `user_id` | uuid (FK → User) | |
| `lab_id` | uuid (FK → Lab) | |
| `role` | enum | `owner` / `admin` / `member` / `viewer` — permission, not title |
| `is_lead` | bool | marks a PI of *this* lab; counted against per-tier PI caps |
| *constraint* | | unique on (`user_id`, `lab_id`) |

### DEPT_MEMBERSHIP
Direct department membership for people not attached via a lab (department admins, unaffiliated researchers).

| Field | Type | Notes |
|---|---|---|
| `user_id` | uuid (FK → User) | |
| `department_id` | uuid (FK → Department) | |
| `role` | enum | `owner` / `admin` / `member` / `viewer` |
| *constraint* | | unique on (`user_id`, `department_id`) |

### PROFILE
One per user. Research interests, skills, eligibility, career goals. Carries the embedding used in relevance scoring.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `user_id` | uuid (FK → User) | one-to-one |
| `interests` | json | keywords, areas, skills, eligibility constraints, funding needs |
| `embedding` | vector (pgvector) | from interests; the "interest" relevance target |
| `updated_at` | timestamp | review flows keep this from drifting |

### PROJECT
A unit of research the relevance engine scores against. Polymorphic owner.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `scope` | enum | `user` / `lab` / `department` |
| `scope_id` | uuid | points at the owning User, Lab, or Department |
| `name` | string | |
| `goals` | json | goals, methods, datasets, deadlines, strategic needs |
| `embedding` | vector (pgvector) | the "project" relevance target |
| `created_at` | timestamp | |

### PROJECT_MEMBER
Join between users and the projects they participate in.

| Field | Type | Notes |
|---|---|---|
| `project_id` | uuid (FK → Project) | |
| `user_id` | uuid (FK → User) | |

### CONTENT_ITEM
Global, deduplicated content from external sources. (Conceptually one table or three sibling tables — Paper / Grant / Fellowship — sharing this shape.)

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `type` | enum | `paper` / `grant` / `fellowship` |
| `source` | string | OpenAlex, arXiv, NIH Reporter, grants.gov, etc. |
| `embedding` | vector (pgvector) | scored against profile/project/lab/dept targets |
| `metadata` | json | authors, venue, deadline, agency, etc. |

### RELEVANCE_SCORE
The match between a content item and a scoring target. One content item can hold several scores against several targets.

| Field | Type | Notes |
|---|---|---|
| `content_id` | uuid (FK → ContentItem) | |
| `target_type` | enum | `user` / `project` / `lab` / `department` |
| `target_id` | uuid | the matched profile/project/lab/dept |
| `score` | float | |
| `signals` | json | per-signal breakdown incl. the project-vs-interest weighting (the "why this matters") |
| `created_at` | timestamp | auditable for relevance tuning |

### SUBSCRIPTION
The plan and entitlement for one scope. Polymorphic scope.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `tier` | enum | `free` / `spore` / `lab` / `canopy` |
| `scope_type` | enum | `user` / `lab` / `department` — who the plan is for |
| `scope_id` | uuid | the User, Lab, or Department on the plan |
| `status` | enum | `active` / `past_due` / `canceled` |

> The subscription holds the *plan*; it does **not** hold a single payer. Each covered member is a `Seat`, and the payer is recorded per seat — so one Canopy department can mix payers (see §7).

### SEAT
One covered member under a subscription. This is the unit that carries a payer, which is what makes flexible Canopy billing possible.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | |
| `subscription_id` | uuid (FK → Subscription) | |
| `member_id` | uuid (FK → User) | the covered member |
| `payer_type` | enum | `department` / `lab` / `self` — who is charged |
| `payer_id` | uuid | the paying Department, Lab, or the member's own User |
| `status` | enum | `active` / `pending` / `revoked` |
| *constraint* | | unique on (`subscription_id`, `member_id`) |

---

## 4. Relationships

| From | To | Cardinality | Meaning |
|---|---|---|---|
| Department | Lab | 1 : N (optional) | a department contains zero or more labs |
| User | Department | 1 : N | a user owns/controls departments |
| User ↔ Lab | via LabMembership | M : N | lab membership with role + lead flag |
| User ↔ Department | via DeptMembership | M : N | direct department membership |
| User | Profile | 1 : 1 | one profile per person |
| Project | User / Lab / Dept | N : 1 (polymorphic) | a project is scoped to exactly one owner |
| User ↔ Project | via ProjectMember | M : N | participation |
| ContentItem | RelevanceScore | 1 : N | many scores per item, one per target |
| Subscription | User / Lab / Dept | N : 1 (polymorphic) | the plan's scope |
| Subscription | Seat | 1 : N | one seat per covered member |
| Seat | User | N : 1 | the covered member (`member_id`) |
| Seat | Dept / Lab / User | N : 1 (polymorphic) | the payer (`payer_id`) |

**Derived relationship — department effective membership:**
```
effective_members(dept) =
    {direct DeptMemberships of dept}
  ∪ {LabMemberships of every Lab where lab.department_id = dept.id}
  (deduplicated by user_id)
```
`Seat` rows are issued against this set (one per member), and department-wide routing uses it too. A user in two labs of the same department counts once.

---

## 5. Roles & titles

Two orthogonal axes — keep them separate.

**Academic title** (on `User.academic_title`) — career stage, used for matching and eligibility:
`student` · `postdoc` · `researcher` · `pi` · `staff`

**Permission role** (on each membership) — authority within a specific lab/department:
`owner` · `admin` · `member` · `viewer`

**Lead flag** (`LabMembership.is_lead`) — marks a PI *of that lab specifically*. Counted against per-tier PI caps (Spore 1 · Lab up to 5 · Canopy unlimited). A user whose title is `pi` may lead one lab and be a `member` elsewhere.

> Existing code uses the `owner/admin/member/viewer` enum on `LabMembership` — this is retained. The change is adding `academic_title` to the user and `is_lead` to lab memberships.

---

## 6. Projects & relevance scoring

**Project scoping.** A project belongs to exactly one owner — a User (personal project), a Lab, or a Department. Users join projects through `PROJECT_MEMBER`.

**Scoring targets.** Every incoming content item is scored against one or more *targets*:
- the user's **interest profile** (`Profile.embedding`)
- the user's / lab's / department's **projects** (`Project.embedding`)
- the **shared lab profile** (lab tier)
- the **department** (Canopy)

**Project beats interest — in the engine, not the schema.** The "prioritize projects over personal interests in some cases" rule is a *weighting decision* applied at scoring time, with the breakdown stored in `RelevanceScore.signals`. This keeps the priority tunable without migrations (relevance tuning is deferred scope) and lets digests explain *why* an item surfaced.

**Cold start.** A brand-new user has a thin or empty profile and no projects, so personalized scoring has little to work with. This is a known gap to solve in the onboarding/relevance phase — flagged here, not resolved by the schema.

---

## 7. Billing, tiers & entitlements

**Core idea: structure is free, intelligence is gated.** Creating labs, departments, and memberships never requires payment. A `Subscription` unlocks the *shared intelligence layer*. An unpaid lab is just a group of individuals who each see their own personal content; subscribing flips on the collective features.

### Tier matrix

| Tier | Price | Who | Unlocks | Excludes |
|---|---|---|---|---|
| **Free** | $0 | Individual | Account, basic usage, very basic (non-personalized) search | No personalized recommendations, no digests, no shared features, no bot |
| **Spore** | $10 / mo | 1 user | Daily personalized digests, up to 10 topics, semantic search, weekly pulse | Team features, shared evidence graph, bot |
| **Mycelium Lab** | $12.50 / member / mo | 3–15 members, up to 5 PIs | Everything in Spore + team workspace, member profiles, shared evidence graph, grant alerts, bot eligible | — |
| **Canopy** | $20 / member / mo | 15+ members, unlimited PIs | Everything in Lab + department-wide routing, advanced admin, priority support, department bot, flexible per-seat billing | — |

### Entitlement logic

- **Free vs Spore** is the personalization line: free gets an account and basic keyword search but **no profile-driven relevance, no digests** — i.e. the scoring layer simply isn't applied for free users.
- **Spore → Lab/Canopy** is the shared line: personal features become collective (shared profile/goals, shared graph, cross-member suggestions, bot).
- **Seat count** for lab/dept tiers is the number of active `Seat` rows, issued against the derived membership (direct + all lab members, deduplicated).

> Gate features by resolving the effective subscription for the user **and** their org context, then checking entitlements — don't hard-code feature checks against tier names scattered through the codebase.

### Canopy payment options

Canopy doesn't force a single payer. Because the payer lives on each `Seat` (not on the subscription), one department can use any mix of:

| Mode | `Seat.payer_type` | Who pays |
|---|---|---|
| Single payment system | `department` | The department owner covers every seat |
| Self-serve | `self` | Each member pays for their own seat |
| Lab-sponsored | `lab` | One member sets up lab-level billing and covers that lab's seats |

Spore is a single self-paid seat; Mycelium Lab defaults to `lab`-paid seats. The same `Seat` mechanism covers every tier — Canopy is just the one that lets the modes coexist within a single department.

---

## 8. Institution (deferred)

**Recommendation: capture it, don't build it.**

Department is the structural and billing ceiling for now. Building Institution as a first-class org unit — with its own memberships, owners, permission cascade, and billing — is significant weight for zero current revenue.

**Do now (cheap):** store `institution` as a string attribute on `User` and `Department`.
**Skip now (expensive):** institution-level memberships, ownership, and billing cascade.

**Why capture it anyway:** powers "same-institution" edges in the knowledge graph, helps deduplicate people across sources, and gives a painless promotion path to a real entity if an enterprise / multi-department deal ever appears. Promote it only when someone is trying to pay for that scope.

---

## 9. Implementation notes

**Already in place (`accounts` app):**
- `Lab` (id, name, slug, timestamps)
- `LabMembership` (user, lab, role ∈ owner/admin/member/viewer, unique per user+lab)
- `AuditEvent`

**To add / change:**
- `User`: add `academic_title`, optional `institution`
- `LabMembership`: add `is_lead`
- New: `Department`, `DeptMembership`, `Profile`, `Project`, `ProjectMember`, `ContentItem` (or Paper/Grant/Fellowship trio), `RelevanceScore`, `Subscription`, `Seat`
- `Lab`: add nullable `department_id`

**Polymorphism — recommended implementation:**
- **Memberships** stay as two concrete tables (`LabMembership` + `DeptMembership`) rather than one polymorphic table — matches existing code and keeps object-level permissions simple.
- **Project scope, RelevanceScore target, Subscription scope, and Seat payer** use nullable typed FK columns + a check constraint ("exactly one set") rather than Django `GenericForeignKey`. This preserves referential integrity and keeps the columns indexable. Reach for `GenericForeignKey` only if target types start proliferating.

**pgvector columns:** `Profile.embedding`, `Project.embedding`, `ContentItem.embedding`. Enabling the `pgvector` extension is a Phase 0 dependency — lock it before scoring work.

---

## 10. Decisions log

| # | Decision | Rationale |
|---|---|---|
| D1 | Academic title on User; permission role on membership | A person's stage is global; their authority is per-org |
| D2 | `is_lead` flag on LabMembership for PIs | Needed to enforce per-tier PI caps; PI status is relational |
| D3 | Department owned/controlled by one user | Clear control surface for managing labs + direct members |
| D4 | Department membership derived, not duplicated | Avoids redundant rows; single source of truth for Canopy seats |
| D5 | One profile per person | Simplest model; per-context nuance handled by projects |
| D6 | Project owner is polymorphic (user/lab/dept) | Supports personal, lab, and department projects uniformly |
| D7 | Project-over-interest priority lives in the engine, not schema | Keeps weighting tunable without migrations |
| D8 | Structure decoupled from billing | Labs/depts exist unpaid; subscription gates shared intelligence |
| D9 | Free $0 individual tier exists | Basic usage + basic search, no personalization |
| D10 | Institution captured as attribute, not built as entity | 80% of value (graph edges, dedup, future-proofing) for ~5% of cost |
| D11 | Polymorphic FKs via nullable columns + check constraint | Preserves integrity/indexing over GenericForeignKey |
| D12 | Payer lives on `Seat`, not `Subscription` | Lets one Canopy department mix payers — dept-paid, self-paid, lab-paid |
| D13 | `Seat` is the universal billing unit across tiers | One mechanism for Spore/Lab/Canopy; seat count = active seats |

---

## 11. Open questions & deferred scope

- [ ] **Free-tier feature boundary.** Confirmed: account + basic usage + very basic search, no personalization. Exact edges (e.g. is *any* digest shown? topic cap?) still to finalize.
- [ ] **Content tables:** single `ContentItem` with a `type` enum vs three sibling tables (Paper/Grant/Fellowship). Trade-off: shared columns/queries vs type-specific fields.
- [ ] **External `Person` vs `User`.** Graph node `Person` includes external co-authors with no account. Decide where the User↔Person link lives when the graph phase starts.
- [ ] **Seat lifecycle.** When are `Seat` rows created and revoked relative to membership changes — auto-provisioned on join, or explicitly assigned? And what's the default `payer_type` when a member joins a Canopy department (department-paid vs prompt-to-choose)?
- [ ] **pgvector verification.** "Verify scaffold + enable pgvector" — Phase 0 dependency, confirm before scoring work.

---

*This briefing captures the agreed relational core. Knowledge-graph schema, scraper/ingestion models, and digest delivery are tracked separately.*
