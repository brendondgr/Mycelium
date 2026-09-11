/** Shapes returned by the workspace read endpoints (see docs/api-contract.md). */

import type { ClusterGroup, ResearchInterests, WatchCadence } from "@/lib/auth-types";

export type LabRole = "owner" | "admin" | "member" | "viewer";

/**
 * Mylo's four-point judgement — what replaced the percent match everywhere.
 *
 * The number implied a measurement nobody made: a language model was asked to
 * guess a similarity, and the result sat next to a real embedding cosine with no
 * way for a reader to tell which was which. A verdict says the useful part
 * honestly, and it exists on both paths — model-judged on a paid plan, derived
 * from the item's rank band within its own theme otherwise — so it means the same
 * thing to every reader.
 *
 * `skip` is never shown as a chip: the item keeps its place in the list and its
 * reference row, but earns no write-up and no badge.
 */
export type Verdict = "read" | "skim" | "file" | "skip";

/** One of the signed-in user's lab memberships — powers the workspace switcher. */
export type MyLab = {
  slug: string;
  name: string;
  role: LabRole;
  is_lead: boolean;
  department: string | null;
  /** Whether the lab has an uploaded logo (shown as the workspace brand mark). */
  has_logo: boolean;
  /** Cache-busting token for the logo URL, or null when there's no logo. */
  logo_version: number | null;
};

/** A lab member row (also used for project members). */
export type LabMember = {
  username: string;
  name: string;
  initials: string;
  email: string;
  role: LabRole;
  is_lead: boolean;
};

export type ProjectMember = {
  username: string;
  name: string;
  initials: string;
};

/** A pending lab invitation addressed to the caller (notifications panel). */
export type MyInvitation = {
  id: string;
  lab_slug: string;
  lab_name: string;
  role: LabRole;
  inviter: string | null;
  created_at: string;
};

/** How an invitee answers an invitation. */
export type InvitationAction = "accept" | "reject" | "ignore";

/** A lab's collective purpose & goals (from `/api/auth/labs/<slug>/profile/`). */
export type LabProfileData = {
  statement: string;
  areas: string[];
  funding_needs: string[];
  strategic_needs: string[];
  interests: Record<string, unknown>;
  embedding_text: string;
  updated_at: string;
};

export type ProjectScope = "user" | "lab" | "department";

/** A project's research focus — the topic its daily recommendations run against. */
export type ProjectFocus = {
  areas: string[];
  keywords: string[];
  statement: string;
  watch_topics: string[];
  /** Interest-cluster grouping (theme label + concrete sub-topic areas) — the
   * same v2 partition shape a profile or lab declares. Empty on a project that
   * hasn't been given a clustered focus. */
  clusters: ClusterGroup[];
};

/**
 * The write shape for a project's `focus` (create body, or PATCH `focus`).
 * `clusters`/`watch_topics` are optional — omitting them leaves that part of
 * the stored focus untouched (PATCH) or simply unset (create).
 */
export type ProjectFocusInput = {
  areas: string[];
  keywords: string[];
  statement: string;
  clusters?: ClusterGroup[];
  watch_topics?: string[];
};

export type Project = {
  id: string;
  name: string;
  scope: ProjectScope;
  scope_name: string;
  /** The owning lab's slug; null for a personal (or department) project. Lets a
   * caller tell a lab project from a personal one without consulting the
   * active workspace. */
  scope_slug: string | null;
  goals: Record<string, unknown>;
  /** Optional display hints read from `goals`; null when the author set none. */
  description: string | null;
  status: string | null;
  progress: number | null;
  /** Normalized research focus (areas/keywords/statement/watch topics/clusters). */
  focus: ProjectFocus;
  /** Which of papers/grants/fellowships/conferences Mylo tracks for this project. */
  watch_categories: BriefingCategory[];
  member_count: number;
  /** Whether the signed-in user belongs to this project. */
  is_member: boolean;
  /** Archived projects keep their stored recommendations but stop new search
   * work and free a slot against the owner's plan cap. Never deleted. */
  is_archived: boolean;
  /** True when a plan downgrade pushed this (active) project past its owner's
   * cap — Mylo pauses new recommendations for it until it's archived or the
   * plan is upgraded. Always false once archived. */
  is_over_cap: boolean;
  /** Whether the signed-in user may edit this project's fundamentals — reported
   * by the API rather than inferred from the active workspace, which was wrong
   * whenever a lab project was opened from the personal scope. */
  can_edit: boolean;
  /** Whether the signed-in user may add, invite, or remove members. */
  can_manage_members: boolean;
  members: ProjectMember[];
  updated_at: string;
};

/** The write shape for a project's fundamentals (`PATCH /api/projects/<id>/`).
 * Every field is optional; an empty string or `null` clears the stored value. */
export type ProjectUpdateInput = {
  name?: string;
  description?: string | null;
  status?: string | null;
  progress?: number | null;
  watch_categories?: BriefingCategory[];
  focus?: ProjectFocusInput;
};

/** An invitation to join a project (from either end of the exchange). */
export type ProjectInvitation = {
  id: string;
  project_id: string;
  project_name: string;
  /** Where the project lives — a lab's name, or "Personal". */
  scope_name: string;
  invitee: ProjectMember;
  inviter: ProjectMember | null;
  message: string;
  status: "pending" | "accepted" | "rejected" | "ignored" | "cancelled";
  created_at: string;
};

/**
 * The 403 body a project-cap violation returns — creating beyond the plan's
 * limit, or restoring an archived project that would exceed it.
 */
export type ProjectCapErrorBody = {
  detail: string;
  code: "project_cap_reached";
  scope: ProjectScope;
  cap: number;
  active: number;
};

/** The caller's own research profile (from `/api/auth/profile/me/`). */
export type ProfileData = {
  academic_title: string;
  institution: string;
  orcid: string;
  openalex_id: string;
  scholar_id: string;
  interests: ResearchInterests;
  is_verified: boolean;
  embedding_text: string;
  updated_at: string;
};

/** What Mylo watches for the caller (from `/api/auth/watch/me/`). */
export type WatchData = {
  topics: string[];
  categories: string[];
  cadence: WatchCadence;
  timezone: string;
  send_hour_local: number;
  urgent_alerts: boolean;
  deadline_buffer_days: number;
  min_paper_window_days: number;
};

/**
 * The default, non-lab scope: the caller's own personal workspace. The account
 * is always a personal one that can additionally view labs, so this — not an
 * "all labs" aggregate — is the primary switcher option.
 */
export const PERSONAL_SLUG = "__personal__";

/** One research-article suggestion (from `/api/daily-report/`). */
export type Suggestion = {
  content_id: string;
  title: string;
  /** The paper's abstract; shown on the card and searched over. */
  abstract: string;
  source: string;
  url: string;
  venue: string;
  year: number | null;
  authors: string[];
  score: number;
  /** read / skim / file / skip — Mylo's judgement, or the rank band's when the
   * reader is on a plan without model reasoning. Null on an unscored row. */
  verdict: Verdict | null;
  /** Position within this item's **own theme's** slate. A global position would
   * compare scores that are not comparable across themes. */
  position: number | null;
  /** How long that theme's slate ran, so the card can say "3rd of 7". Null on
   * rows written before slates recorded their own length. */
  position_of: number | null;
  /** The strongest reason this might not be worth the reader's time. Mandatory on
   * a model-written judgement — it is what makes the feed read as judgement
   * rather than promotion. */
  caveat: string;
  /** The reason's three beats: why it matters to this theme, how to use it, what
   * to take from it. The printed report carries only the first. */
  beats: string[];
  /** One clause on what two themes share, when the item reaches both. */
  bridge_note: string;
  /** The transformer (embedding) cosine match, 0–100, this paper cleared to be
   * surfaced — shown on the cross-embedding tail in place of the model's percent.
   * null on legacy rows written before the threshold. */
  embedding_match: number | null;
  /** Interest label -> [0,1] fusion score; drives the derived per-category %. */
  per_interest: Record<string, number>;
  /** Interest labels this paper matched — the source of the page's filter chips. */
  matched_interests: string[];
  /** The attributed research-interest cluster this paper best fits, or null on a
   * single/no-cluster profile. */
  cluster: { id: string; label: string } | null;
  /** cluster_id -> [0,1] fit score, across every cluster this paper cleared. */
  per_cluster: Record<string, number>;
  /** Secondary clusters this paper is also relevant to (empty when none). */
  bridge_clusters: { id: string; label: string }[];
  rank: number | null;
  headline: string;
  reason: string;
  /** "llm" when Mylo wrote the reason, "fallback" when it was templated. */
  origin: "llm" | "fallback";
  /** Freshly gathered within the last week — flagged New and pinned to the top. */
  is_new: boolean;
  /** Still inside its one-week pin window (leads the list; sinks to match order after). */
  pinned: boolean;
  /** Whether the user has bookmarked this paper (the Saves page). */
  saved: boolean;
  /** Slugs of the caller's *managed* labs that have already saved this paper. */
  saved_labs: string[];
};

/**
 * A plain roll-up of the day's suggested papers (from `/api/daily-report/`).
 * Powers the Daily Report page; the papers themselves live on Research Papers.
 */
export type DailyReportSummary = {
  paper_count: number;
  /** How many of the matched papers are new this week (pinned to the top). */
  new_count: number;
  /** How many of the feed's papers Mylo judged worth reading in full. */
  strong_matches: number;
  /** How many of each verdict the feed currently holds. */
  verdict_counts: Record<Verdict, number>;
  /** The embedding-match floor (percent) each surfaced paper had to clear. Not a
   * claim about any one item — it is what got them into the feed at all. */
  match_threshold: number;
  themes: string[];
  sources: string[];
  headline: string;
};

/** The signed-in user's current daily digest (from `/api/daily-report/`). */
export type DailyReport = {
  /** ISO timestamp of the run that produced these, or null when none has run. */
  generated_at: string | null;
  /** The day's summary, or null when no run has produced suggestions yet. */
  summary: DailyReportSummary | null;
  /**
   * True while a sign-up background scan is filling this user's paper feed, so the
   * page can show a "scanning new articles for you" state until it lands.
   */
  scanning: boolean;
  suggestions: Suggestion[];
};

/**
 * Who wrote a day's report body.
 *
 * `"carried"` means nothing entered the reader's top 25 that day, so the previous
 * day's report stands unchanged — a real answer, and a different one from the
 * deterministic `"fallback"` the model's absence produces.
 */
export type BriefingOrigin = "llm" | "fallback" | "carried";

/** A watched category key, as stored in `WatchPreference.categories`. */
export type BriefingCategory =
  | "papers"
  | "grants"
  | "conferences"
  | "fellowships";

/** One top item the briefing references (the showcase grounding). */
export type BriefingShowcaseItem = {
  content_id: string;
  type: string;
  title: string;
  url: string;
  verdict: Verdict | null;
  headline: string;
  deadline_date: string;
  is_new: boolean;
};

/**
 * One row of the report's summary table: the reader's own part, or one project
 * they are on. `counts` is what is **new today and above the relevance floor** —
 * the same set the report's sections list, so the table maps the document rather
 * than restating the feeds. A project with an all-zero row still appears: "nothing
 * for this project today" is an answer, and a row that vanished on a quiet day
 * would read as the project having been dropped from the report.
 */
export type BriefingProjectRow = {
  /** `"personal"`, or the project's id. */
  key: string;
  /** `"Personal"`, or the project's name. */
  label: string;
  kind: "personal" | "project";
  /** A project's owner: `"user"` / `"lab"` / `"department"`. Empty for Personal. */
  scope: string;
  counts: Partial<Record<BriefingCategory, number>>;
};

/** The "Mylo Report" (from `/api/daily-briefing/`) — the Daily page's three zones. */
export type DailyBriefing = {
  /** ISO timestamp of the last briefing generation, or null before the first run. */
  generated_at: string | null;
  /** The `YYYY-MM-DD` day this briefing covers — the history key. Null before the
   * first run. */
  generated_on: string | null;
  /** The categories this briefing covered (what the user watches). */
  categories: BriefingCategory[];
  /** Per-category item counts ("Today's Summaries"). */
  counts: Partial<Record<BriefingCategory, number>>;
  /** Items first seen this week, per category. Optional — absent on older,
   * already-persisted briefings that predate this field. */
  new_counts?: Partial<Record<BriefingCategory, number>>;
  /** Top items per category the prose is grounded in (the showcase). */
  showcase: Partial<Record<BriefingCategory, BriefingShowcaseItem[]>>;
  /** The report's summary table — Personal first, then a row per project. Empty
   * on briefings written before the table existed, which the card reads as "no
   * table" rather than "no projects". */
  project_summary?: BriefingProjectRow[];
  /** This run's numbers, as the Discord post carries them. Read from the stored
   * row rather than derived here, so the header and the post can never quote
   * different figures for the same morning. Empty on briefings written before
   * statistics existed. */
  stats?: BriefingStats;
  /** Which report this is. `"daily"` unless the caller asked for the weekly. */
  kind?: BriefingKind;
  /** The written briefing, or null when no run has produced one yet. */
  briefing: { body: string; origin: BriefingOrigin } | null;
};

export type BriefingKind = "daily" | "weekly";

/**
 * One run's statistics (`DailyBriefing.stats`). Every field is optional: a row
 * written before this existed carries `{}`, and a header must render as "no
 * numbers" rather than as zeros, which would read as "Mylo found nothing".
 *
 * `discovered_*` are corpus-wide and `null` when the collector could not answer
 * — again distinct from zero.
 */
export type BriefingStats = {
  discovered_papers?: number | null;
  discovered_opportunities?: number | null;
  /** Distinct items that first matched this reader or their projects this run. */
  matched?: number;
  /** Items that entered a top list. Equals the summary table's grand total. */
  entered?: number;
  /** `{category: [entered today, in the feed]}`. */
  by_category?: Partial<Record<BriefingCategory, [number, number]>>;
  /** `[label, entered, alerts]`, the reader's own part first. */
  by_project?: [string, number, number][];
  /** `[label, entered]`, busiest first. */
  by_theme?: [string, number][];
  /** What the first `by_project` row is called, so a caller can drop it. */
  aggregate_label?: string;
  alerts?: number;
  deadline_window_days?: number;
  deadlines_in_window?: number;
  nearest_deadline?: {
    title: string;
    url: string;
    due_date: string;
    days: number;
    label: string;
  } | null;
  /** Lab surfaces only: projects this report is not naming. */
  private_projects_hidden?: number;
};

/**
 * One row of the briefing index (`/api/briefings/`) — the Reports page's date
 * list. Deliberately body-free: the index can span the whole retention window, so
 * the prose is fetched only for the day the reader opens.
 */
export type DailyBriefingSummary = {
  /** The `YYYY-MM-DD` day this briefing covers. */
  generated_on: string;
  /** When it was written (a same-day rerun moves this, not `generated_on`). */
  generated_at: string;
  origin: BriefingOrigin;
  kind?: BriefingKind;
  categories: BriefingCategory[];
  counts: Partial<Record<BriefingCategory, number>>;
  new_counts?: Partial<Record<BriefingCategory, number>>;
};

/* -- Opportunities: grants, conferences, deadlines -------------------------- */

/**
 * One quality-ranking system's verdict for a conference series (plan D2:
 * rankings are visual only, never relevance). `edition` is always "" in the
 * live corpus — no vendored adapter records a per-year rank, only a
 * point-in-time one — so a client must never read a year into it; kept only
 * because the API contract carries the field verbatim off the collector.
 */
export type ConferenceRanking = { system: string; rank: string; edition: string };

/** Per-source attribution: who produced this record, and where to read it there. */
export type SourceLink = { source: string; url: string };

/**
 * One dated entry in a conference's ordered deadline list, verbatim off the
 * collector's own `Deadline` record (`metadata["deadlines_structured"]`) —
 * the full multi-round detail behind a card's single actionable
 * `deadline_date` (plan D1). `instant` is an ISO 8601 UTC datetime, or null
 * for an entry the source stated in words the collector could not parse
 * (`raw` is then the only display text available).
 */
export type StructuredDeadline = {
  kind: string;
  /** Verbatim as the source wrote it — the fallback display when `instant` is null. */
  raw: string;
  instant: string | null;
  /** How `instant` was resolved from `raw` ("AoE", "UTC-8"), or an
   * "inferred:…" marker where the source published no zone at all. */
  basis: string;
  /** Free-text round label from the source ("round 2"), or "" when the
   * source gave none — there is no typed round vocabulary anywhere upstream. */
  round_label: string;
  source: string;
  /** True only for a date this system projected rather than read verbatim —
   * never let a projection be indistinguishable from a confirmed date. */
  is_estimated: boolean;
  /** Incremented when an upsert moves this same entry later — repeated
   * extensions are one of the collector's predatory red flags. */
  extension_count: number;
};

/** Fields shared by a matched grant and a matched conference. */
type OpportunityBase = {
  content_id: string;
  title: string;
  url: string;
  score: number;
  /** read / skim / file / skip (null on an unscored row). */
  verdict: Verdict | null;
  /** Position within this item's own theme's slate. */
  position: number | null;
  /** That theme's slate length — the denominator behind `position`. */
  position_of: number | null;
  /** The strongest reason to skip it. Mandatory on a model-written judgement. */
  caveat: string;
  /** The reason's three beats; the printed report carries only the first. */
  beats: string[];
  /** The transformer (embedding) cosine match, 0–100, a threshold-gated grant or
   * conference cleared to be surfaced — shown on the tail in place of the model's
   * percent. null for fixed-slice areas and legacy rows. */
  embedding_match: number | null;
  rank: number | null;
  headline: string;
  reason: string;
  origin: "llm" | "fallback" | "rules";
  /** New + pinned to the top for its first week (a fresh, high-fit item). */
  is_new: boolean;
  /** The listing's *source page* moved something actionable — a deadline added,
   * moved, or reopened — inside the pin window. Never true at the same time as
   * `is_new`: an item that just arrived is new, not updated. */
  is_updated: boolean;
  pinned: boolean;
  /** The actionable date (application/abstract/manuscript/event), ISO or "". */
  deadline_date: string;
  deadline_kind: string;
  /** Every addressable per-kind deadline (the reminder composer picks from these). */
  addressable_deadlines: DeadlineOption[];
  status_summary: string;
  /** Whether the user has saved this to their (personal) deadlines. */
  saved: boolean;
  /** Slugs of the caller's *managed* labs that have already saved this item. */
  saved_labs: string[];
  /** The attributed research-interest cluster — the theme this opportunity was
   * matched under. Null/omitted (a single- or no-cluster profile) renders no
   * badge and leaves the cluster chip row on the feed empty. */
  cluster?: { id: string; label: string } | null;
  /** The other themes this opportunity also cleared. The card's match rail
   * names the attributed cluster first and then these, up to three in all. */
  bridge_clusters?: { id: string; label: string }[];
  /** cluster_id -> [0,1] fit score across every cluster the item cleared. */
  per_cluster?: Record<string, number>;
  /** Which adapter/provider produced this row (e.g. "grants:nsf",
   * "conf:ccf_deadlines"), or "" for a snapshot row that predates the
   * open-collector migration. Provenance every area now carries (plan Phase 9). */
  source: string;
  /** A short reuse label ("CC0-1.0", "US Government Work — …"), or "" when the
   * source publishes none. Never a URL — see `license_url`. */
  license: string;
  /** A machine-readable licence URL, or "" — as of this migration no vendored
   * source publishes one the mapper can read yet (see the backend serializer's
   * documented gap); starts working the day one does, no frontend change needed. */
  license_url: string;
  /** Per-source attribution footer entries — one `{source, url}` per
   * contributor (a merged record can have several). Empty for a fellowship,
   * a single-source area with nothing to attribute. */
  source_links: SourceLink[];
};

/** One addressable deadline on an item (the ContentDeadline projection, R0). */
export type DeadlineOption = {
  kind: string;
  /** Which round of that kind, for an item carrying several — a conference's
   * second paper deadline, a workshop track. Send it back verbatim to set a
   * reminder on *that* round. `""` is the single-round case (every grant and
   * fellowship, and a conference's event row). */
  round_key: string;
  /** The source's own wording for the round ("round 2", "workshop track"), or
   * `""`. Free text: 287 distinct values appear in the corpus, so treat it as
   * a label to print, never a value to switch on. */
  round_label: string;
  /** This is the earliest future deadline of its kind — the one a card's
   * headline reads. */
  is_next: boolean;
  /** ISO date, or null for a rolling/unknown deadline (not remindable). */
  due_date: string | null;
  confidence: "confirmed" | "anticipated" | "rolling" | "unknown";
  label: string;
};

/** A matched funding opportunity (from `/api/opportunities/grants/`). */
export type GrantOpportunity = OpportunityBase & {
  sponsor: string;
  amount: string;
  matched_topics: string;
  /** When Mylo first surfaced this grant (ISO or ""). */
  posted: string;
  /** A human-readable blurb (AI summary or abstract), or "". */
  description: string;
  /** The funder's own opportunity identifier (an NOFO/FOA/solicitation
   * number), or "" when the source publishes none. */
  opportunity_number: string;
  /** Every known application round (`close_date` + `additional_due_dates`),
   * as ISO dates — the full detail behind the single next-due `deadline_date`
   * (plan D1). Non-empty whenever `deadline_date` is (mapping.py derives one
   * from the other). Drives the deadline hover. */
  due_dates: string[];
  /** The funder's own free-text deadline line, kept verbatim alongside the
   * parsed `deadline_date` for a reader who wants the source wording. */
  deadline_text: string;
  /** True when the collector estimated this record's dates rather than
   * reading them verbatim off the source — the grant-side twin of a
   * conference's `confidence: "anticipated"` (see deadlines_projection.py). */
  dates_inferred: boolean;
  /** The first-ever recorded close date, kept even after a funder moves it —
   * lets a reader see a deadline shifted, not just what it is now. */
  original_deadline: string;
  /** Letter-of-intent date, when the funder requires one ahead of the full
   * application — "" for the large majority of grants. */
  loi_date: string;
  /** The funder's own publication date (repointed off `posted`, plan Phase 9
   * — `posted` now prefers this and falls back to Mylo's ingest date only for
   * a pre-migration row that carries no such key). */
  published_on: string;
};

/** A matched conference (from `/api/opportunities/conferences/`). */
export type ConferenceOpportunity = OpportunityBase & {
  location: string;
  country: string;
  event_dates: string;
  /** The (first) event date as ISO YYYY-MM-DD, or "" — for event-date filters/sort. */
  event_date: string;
  deadlines: string;
  keywords: string;
  /** Semicolon-delimited subject categories — clean tags (unlike keywords). */
  matched_subjects: string;
  /** True while an abstract-submission deadline is still upcoming. */
  abstract_open: boolean;
  /** True while a full-paper (manuscript) submission deadline is still upcoming. */
  manuscript_open: boolean;
  /** Submission status: "open" | "closed" | "unknown". */
  status: string;
  /** Pivot's raw "Scope" section, or "". */
  scope: string;
  /** The venue's own blurb (Pivot files it under "Scope"), collapsed, or "". */
  description: string;
  /** The venue's short acronym (e.g. "NOVAS"), with the edition year already
   * stripped out — see `year_label`. */
  acronym: string;
  /** The edition year, deduplicated from `acronym` at ingest (OpenReview
   * emits "NOVAS 2026", split into acronym "NOVAS" + this field "2026"). */
  year_label: string;
  /** The raw `{system: {rank, edition}}` map, "N" entries included — a real
   * "not ranked by this system" statement, distinct from the key being
   * absent. Prefer `rank_badges` for display; this is the verbatim source. */
  rankings: Record<string, { rank: string; edition: string }>;
  /** Display-ready claimed ranks only ("N" already excluded) — what the
   * card's badge row renders (plan D2). `edition` is always "" — see
   * `ConferenceRanking`. */
  rank_badges: ConferenceRanking[];
  /** Predatory/quality flags on the series (e.g. "fees_prominent"). */
  red_flags: string[];
  /** Per-instance quality caveats (e.g. a date that looks like an abstract
   * registration recorded as a submission deadline). */
  quality_warnings: string[];
  /** The full multi-round deadline array (plan D1) — every kind and round,
   * not just the one `deadline_date` gates openness on. The hover's data. */
  deadlines_structured: StructuredDeadline[];
};

/** A ranked opportunity feed for one area. */
export type OpportunityFeed<T> = {
  generated_at: string | null;
  items: T[];
};

/**
 * Static hover copy for conference rank badges (from
 * `GET /api/opportunities/ranking-reference/`). A conference card carries
 * only which rank it has (`rank_badges`); what that rank *means* is identical
 * prose for every card that shares it, so it is fetched once here rather than
 * duplicated per row of a feed that can carry dozens of conferences.
 * Authenticated but otherwise static — no target, no personalization — safe
 * to cache indefinitely on the client.
 */
export type RankingReference = {
  rank_systems: Record<string, { label: string; about: string }>;
  /** `{system: {rank: explanation}}` — "N" is never a key here: a badge is a
   * claim of rank, and "not ranked" is not one. */
  rank_explanations: Record<string, Record<string, string>>;
};

/** A member who personally matched a shared item (the "who's interested" layer). */
export type InterestedMember = {
  username: string;
  name: string;
  initials: string;
  /** What this member's *own* feed concluded about the item. */
  verdict: Verdict;
};

/**
 * One member an item is recommended to — the "who is this for?" layer that a lab
 * feed has and a personal feed does not.
 *
 * `basis` says *on what grounds*, and the card reads it rather than guessing:
 * - `profile_fit` — Mylo matched the item to this member's own research; `reason`
 *   is his sentence saying why (or the deterministic overlap line when the model
 *   was unavailable, which `source` distinguishes).
 * - `own_match`   — the item independently cleared this member's personal feed,
 *   so `own_feed_percent` is their own score for it.
 * - `eligible`    — fellowships only: this member personally qualifies (`tier`),
 *   disclosed only for members who opted into lab-visible eligibility.
 *
 * Eligibility also subtracts: a member a fellowship hard-excludes never appears
 * here at all, whichever basis named them. That removal needs no consent — it
 * publishes nothing.
 */
export type RecommendedMember = {
  username: string;
  name: string;
  initials: string;
  /**
   * The cosine between the item and this member's profile vector, ×100. A
   * geometric measurement — raw cosines between two short texts sit naturally in
   * the 0.4–0.7 band, so 66 here is strong. Null when no profile vector matched.
   */
  profile_cosine: number | null;
  /**
   * This member's own score for the item on their personal feed — the model's
   * 0–100 judgement, the number they see when they open their own page. Null
   * when the item never cleared their personal feed.
   *
   * Not comparable with `profile_cosine`: different estimators on different
   * scales, and a ~30-point gap between them is expected, not an anomaly. Label
   * whichever one is shown with its scope; never present both as one list.
   */
  own_feed_verdict: Verdict | null;
  reason: string;
  source: "llm" | "similarity" | "own_match" | "eligibility";
  basis: Array<"profile_fit" | "own_match" | "eligible">;
  tier?: "qualified" | "conditional";
};

/** Cumulative "found in the last …" totals for one area (today ≤ week ≤ month ≤ year). */
export type WindowCounts = {
  today: number;
  week: number;
  month: number;
  year: number;
};

/** Per-area recency map, keyed the same way for a user, lab, or project target. */
export type WindowCountsMap = Record<
  "papers" | "grants" | "conferences" | "fellowships",
  WindowCounts
>;

/** The signed-in user's own "what Mylo found" recency matrix (`/api/recommendations/window-counts/`). */
export type PersonalWindowCounts = {
  window_counts: WindowCountsMap;
};

/**
 * A lab's or a project's combined recommendations (from
 * `/api/labs/<slug>/recommendations/` and `/api/projects/<id>/recommendations/`).
 *
 * All four areas are the target's own matches in the *same* card shapes the
 * personal pages render — a lab feed is structurally identical to its personal
 * counterpart, fellowships included. What a lab adds is the layer on top:
 * `recommended_for` maps a content id to the members Mylo judges it most
 * applicable to, and `interested` to the members who matched it strongly on their
 * own account.
 */
export type TargetRecommendations = {
  generated_at: string | null;
  counts: {
    papers: number;
    grants: number;
    conferences: number;
    fellowships: number;
  };
  /** Per-area today/week/month/year totals (the lab overview stats block). */
  window_counts: WindowCountsMap;
  papers: Suggestion[];
  grants: GrantOpportunity[];
  conferences: ConferenceOpportunity[];
  fellowships: FellowshipOpportunity[];
  interested: Record<string, InterestedMember[]>;
  recommended_for: Record<string, RecommendedMember[]>;
};

/**
 * A project's combined recommendations (from
 * `/api/projects/<id>/recommendations/`, optionally `?digest=1` for the
 * capped picks — top 10 papers / 5 grants / 5 fellowships / 5 conferences,
 * passed-deadline conferences dropped). Identical in shape to a lab's.
 */
export type ProjectRecommendations = TargetRecommendations;

/**
 * One paper shared into a project's team feed (from
 * `/api/projects/<id>/feed/`). `shared_by`/`co_sharers` reuse the project
 * member brief shape (`username`/`name`/`initials`) already defined above.
 */
export type ProjectFeedItem = {
  content_id: string;
  type: string;
  source: string;
  title: string;
  abstract: string;
  url: string;
  venue: string;
  year: number | null;
  authors: string[];
  share_id: string;
  note: string;
  share_source: string;
  shared_by: ProjectMember;
  shared_at: string;
  /** Other members who separately shared the same content item. */
  co_sharers: ProjectMember[];
  /** Total number of times this item has been shared into the project. */
  share_count: number;
  seen: {
    first_seen_at: string;
    first_seen_via: string;
    seen_by_count: number;
  } | null;
};

/** A project's team-shared feed (from `/api/projects/<id>/feed/`). */
export type ProjectFeed = {
  count: number;
  items: ProjectFeedItem[];
};

/**
 * One item inside a shared collection (from
 * `/api/projects/<id>/collections/<cid>/`). Reuses the same content shape as
 * a feed item, plus who added it and their note.
 */
export type CollectionItem = {
  content_id: string;
  type: string;
  source: string;
  title: string;
  abstract: string;
  url: string;
  venue: string;
  year: number | null;
  authors: string[];
  item_id: string;
  note: string;
  added_by: ProjectMember | null;
  added_at: string;
};

/**
 * A project's shared reading list, without its items (from
 * `/api/projects/<id>/collections/`).
 */
export type CollectionBrief = {
  id: string;
  name: string;
  description: string;
  is_archived: boolean;
  item_count: number;
  created_by: ProjectMember | null;
  created_at: string;
};

/** A single collection's full detail, including its items. */
export type CollectionDetail = CollectionBrief & {
  items: CollectionItem[];
};

/** Result of resolving a pasted DOI/article link into a project share. */
export type IngestLinkResult = {
  share_id: string;
  content_id: string;
  created: boolean;
  /** "no_abstract" means the paper was added but can't be matched on yet. */
  embed_status: "ok" | "no_abstract";
  title: string;
};

/** A bookmarkable area — every saveable content kind. */
export type SavedArea = "grant" | "conference" | "fellowship" | "paper";

/** One saved deadline (from `/api/deadlines/`). */
export type SavedDeadline = {
  id: string;
  content_id: string | null;
  area: SavedArea;
  title: string;
  url: string;
  subtitle: string;
  deadline_date: string | null;
  deadline_kind: string;
  note: string;
  days_remaining: number | null;
  within_week: boolean;
};

/**
 * One bookmark on the Saves page (from `/api/saves/`): the save snapshot plus
 * `card`, the exact payload the item's own feed page renders — so a saved grant
 * shows like the Grants page, a saved paper like Research Papers, and so on.
 * `card` is null once the source listing was pruned; the snapshot fields on the
 * envelope are the fallback display.
 */
export type SavedItem = SavedDeadline & {
  /** ISO timestamp the user saved this item. */
  saved_at: string;
} & (
    | { area: "grant"; card: GrantOpportunity | null }
    | { area: "conference"; card: ConferenceOpportunity | null }
    | { area: "fellowship"; card: FellowshipOpportunity | null }
    | { area: "paper"; card: Suggestion | null }
  );

/**
 * One entry this reader has ignored (from `/api/opportunities/ignored/`). The
 * mirror of `SavedItem`, minus the snapshot: an ignore row is deleted with its
 * source listing, so `card` is always the real card the item's own feed renders.
 */
export type IgnoredItem = {
  id: string;
  content_id: string;
  /** ISO timestamp the reader ignored this item. */
  ignored_at: string;
} & (
  | { area: "grant"; card: GrantOpportunity }
  | { area: "conference"; card: ConferenceOpportunity }
  | { area: "fellowship"; card: FellowshipOpportunity }
  | { area: "paper"; card: Suggestion }
);

/**
 * A lab's shared saved items (from `/api/labs/<slug>/saves/`). `can_manage` gates
 * the save/remind/remove affordances to lab managers; every member may read.
 */
export type LabSavesResponse = {
  can_manage: boolean;
  items: SavedItem[];
};

/**
 * One header-bell notification (from `/api/notifications/`). Backed by the
 * Notification model (reminders rework): a fired reminder, a moved deadline, or a
 * high-signal recommendation — not the old saves-due-within-a-week scan.
 */
export type NotificationItem = {
  id: string;
  kind: "reminder" | "deadline_moved" | "high_signal";
  content_id: string | null;
  title: string;
  body: string;
  url: string;
  created_at: string;
  read_at: string | null;
};

export type NotificationFeed = {
  count: number;
  items: NotificationItem[];
};

/** A reminder offset: "N units before the deadline". */
export type ReminderUnit = "day" | "week" | "month" | "year";
export type ReminderOffset = { amount: number; unit: ReminderUnit };

/** An offset as the API reports it back: the lead time plus the date it lands on
 * (computed server-side with the same maths the tick fires by). */
export type ReminderOffsetRead = ReminderOffset & { fire_date: string | null };

export type ReminderState = "active" | "fired_out" | "cancelled" | "stale";

/** One deadline reminder (from `/api/reminders/`). */
export type Reminder = {
  id: string;
  scope: "user" | "lab";
  lab_slug: string | null;
  lab_name: string | null;
  content_id: string | null;
  deadline_kind: string;
  /** Which round of that kind this reminder is for; `""` when single-round. */
  deadline_round_key: string;
  /** The round's own wording, snapshotted so the row can name it. */
  round_label: string;
  area: string;
  title: string;
  url: string;
  due_date: string | null;
  confidence: string;
  state: ReminderState;
  snoozed_until: string | null;
  channel_id_override: string;
  has_unlinked_targets: boolean;
  offsets: ReminderOffsetRead[];
  /** The soonest lead time still ahead (null once they've all fired//it's off). */
  next_fire_date: string | null;
  /** The lab's target local hour; null for a personal reminder, which rides the
   * daily run rather than a configured hour. */
  send_hour_local: number | null;
  timezone: string;
  /** Whether the caller may edit this one — owner, or a lab PI/admin. */
  can_manage: boolean;
  mentions: { kind: string; id: string; username: string; name: string }[];
  created_at: string;
  updated_at: string;
};

/** A partial edit of an existing reminder (`PATCH /api/reminders/<id>/`). Every
 * field is optional; an absent key means "leave alone", and an explicit
 * `snoozed_until: null` clears a snooze. */
export type ReminderUpdateInput = {
  offsets?: ReminderOffset[];
  mentions?: string[];
  channel_id_override?: string;
  snoozed_until?: string | null;
  state?: "active" | "cancelled";
};

/** A postable Discord channel option for the lab reminder channel picker. */
export type ReminderChannel = { id: string; name: string; type?: number };

/** The lab's postable channels + its `/setup` default (GET
 * `/api/reminders/lab-channels/`). An empty `channels` list means the guild is
 * unlinked or Discord was unreachable — the composer then offers only the default. */
export type LabReminderChannels = {
  channels: ReminderChannel[];
  default_channel_id: string;
  default_channel_name: string;
};

/**
 * Whether the caller may set a reminder here (GET `/api/reminders/access/`).
 *
 * Reminders are Discord-delivered and paid, so two independent conditions gate
 * them; both are reported so the UI can name the one thing to fix rather than
 * showing a generic "unavailable". `reason` is `"permission"` only for a lab the
 * caller does not manage.
 */
export type ReminderAccess = {
  allowed: boolean;
  plan_ok: boolean;
  discord_ok: boolean;
  reason: "" | "plan" | "discord" | "plan_and_discord" | "permission";
  detail: string;
};

/** One thing a lab alert can @-mention in the lab's Discord server. */
export type MentionTarget =
  | { kind: "everyone" }
  | { kind: "role"; id: string; name: string }
  /** A guild member with no Mycelium account — identified by snowflake. */
  | { kind: "user"; id: string; name: string }
  /** A Mycelium user who is a member of this lab. */
  | { kind: "user"; username: string; name: string };

/** Who a lab alert may tag (`GET /api/reminders/lab-mention-targets/`).
 *
 * `detail` explains an empty roster — an unlinked server, or the Server Members
 * intent not being enabled — so the picker can say why rather than looking
 * broken. Always HTTP 200: a Discord hiccup must not stop someone setting an
 * alert that tags nobody. */
export type LabMentionTargets = {
  roles: { id: string; name: string }[];
  members: { id: string; name: string }[];
  everyone_allowed: boolean;
  detail: string;
};

/** The body for creating a reminder (POST `/api/reminders/`). */
export type ReminderInput = {
  content_id: string;
  deadline_kind: string;
  /** Which round of that kind (`DeadlineOption.round_key`). Omitted means `""`
   * — the single-round deadline every grant and fellowship carries. */
  deadline_round_key?: string;
  scope?: "personal" | "lab";
  lab_slug?: string;
  offsets?: ReminderOffset[];
  mentions?: MentionTarget[];
  channel_id_override?: string;
};

/**
 * A paper suggestion surfaced from a teammate's shared item (from
 * `/api/suggestions/`) — the "Suggested for you" surface. `score` is the fused
 * ranking score, as itself: scaling it by 100 and calling it a percent match was
 * exactly the false precision this product retired.
 */
export type MemberSuggestion = {
  id: string;
  content_id: string;
  title: string;
  url: string;
  score: number;
  project: { id: string; name: string };
  shared_by: ProjectMember | null;
  created_at: string;
};

export type MemberSuggestionsFeed = {
  count: number;
  items: MemberSuggestion[];
};

/**
 * The personal fellowships feed. `stage_set` reports whether the reader's career
 * stage resolved at all — from the eligibility step, the intake answer, or their
 * academic title. The stage gate is deliberately silent for anyone it cannot
 * place on the ladder, so a feed built without one is genuinely less filtered
 * than the page would otherwise imply, and the section says so.
 */
export type FellowshipsFeed = OpportunityFeed<FellowshipOpportunity> & {
  stage_set: boolean;
};

/**
 * A matched fellowship opportunity (from `/api/opportunities/fellowships/`).
 * The deterministic eligibility rule engine gates + fit-ranks these; Mylo's LLM
 * then writes the tailored `reason` for the top slice (`origin === "llm"`),
 * falling back to the rule engine's own summary (`origin === "rules"`) when the
 * model is unavailable. `tier` carries the eligibility verdict either way.
 */
export type FellowshipOpportunity = OpportunityBase & {
  /** Eligibility verdict: "qualified" (strong) | "conditional" (possible fit). */
  tier: string;
  /**
   * Which band this award belongs in: `matched` when its research fit *spikes*
   * on one or two of the reader's themes, `open` when it is flat across all of
   * them and is therefore topic-agnostic.
   *
   * The split exists because cluster-scoping a fellowship list naively puts a
   * university-wide dissertation grant under every theme the reader has, while
   * *not* scoping it at all turns the page into a directory. Eligibility remains
   * a hard gate underneath both bands — no research fit promotes past it.
   */
  band: "matched" | "open" | "";
  /** Place within the band: in its theme, or in the open list. */
  band_position: number | null;
  /** Structured award class: "fellowship" | "scholarship" | "internship" | "award" | "prize". */
  award_class: string;
  /** Human-readable funding amount string (may include range or note). */
  amount: string;
  /** Short clarifying note about the amount (e.g. "per year" or "stipend"). */
  amount_note: string;
  /**
   * Deadline semantics: "true" | "anticipated" | "rolling" | "continuous" |
   * "varies" | "unknown".
   */
  deadline_type: string;
  /** Broad research fields associated with this fellowship. */
  fields: string[];
  /** Eligible academic stages (e.g. "doctoral_dissertation", "postdoc"). */
  stages: string[];
  /** Citizenship requirements (e.g. "us", "international"). */
  citizenship: string[];
  /** Award type labels (e.g. "Stipend", "Travel grant"). */
  award_types: string[];
  /** Limiting conditions (e.g. "Women only", "Illinois affiliation required"). */
  limits: string[];
  /** Human eligibility bullet lines (why the user qualifies or conditionally fits). */
  eligibility: string[];
  /** Contact email for the fellowship administrator, or "". */
  contact_email: string;
  /** ISO date the fellowship was first posted/seen, or "". */
  posted: string;
  /** The fellowship's own blurb from the source listing, or "". */
  description: string;
};

/* ----------------------------------------------------------------------- */
/* Unified search (GET /api/search/)                                        */
/* ----------------------------------------------------------------------- */

export type SearchContentType = "paper" | "grant" | "fellowship" | "conference";
export type SearchSort = "relevance" | "date" | "deadline";

/** One search hit. Type-specific fields are populated per `type`, else "". */
export type SearchResultItem = {
  content_id: string;
  type: SearchContentType;
  title: string;
  summary: string;
  source: string;
  url: string;
  created_at: string;
  /** Fused relevance score (RRF) — for ordering, not display. */
  score: number;
  /** Which channels matched this item: "lexical" | "semantic" | "fuzzy". */
  matched_on: string[];
  saved: boolean;
  /** Slugs of the caller's *managed* labs that have already saved this item. */
  saved_labs: string[];
  /**
   * Whether the reader has ignored this item. Search still returns ignored hits
   * — you typed the query — so the card shows the state and offers the way back.
   */
  ignored: boolean;
  // (No `source` — the search path deliberately omits it.)
  // Paper
  authors: string[];
  venue: string;
  year: number | null;
  // Grant
  sponsor: string;
  amount: string;
  // Conference
  location: string;
  event_dates: string;
  // Fellowship
  award_class: string;
  // Any type (best-effort)
  deadline: string;
  /** The attributed research-interest cluster this result best fits, or null/
   * absent on a single/no-cluster profile. */
  cluster?: { id: string; label: string } | null;
};

export type SearchFacetBucket = { value: string; count: number };
/**
 * `type` is always present. The per-type facet (only one) is included only when
 * exactly one type is selected: papers → `year`, grants → `sponsor`,
 * fellowships → `award_class`, conferences → `country`.
 */
export type SearchFacets = {
  type: SearchFacetBucket[];
  year?: SearchFacetBucket[];
  sponsor?: SearchFacetBucket[];
  award_class?: SearchFacetBucket[];
  country?: SearchFacetBucket[];
};

/** The `GET /api/search/` envelope. */
export type SearchResponse = {
  query: string;
  normalized: string;
  sort: SearchSort;
  /** "low" flags a weak top match — a display cue, never an empty page. */
  confidence: "ok" | "low";
  count: number;
  /** True when the relevance pool was capped (more may exist beyond it). */
  pool_truncated: boolean;
  facets: SearchFacets;
  limit: number;
  offset: number;
  /** Opaque cursor for the next page, or null at the end. */
  next_cursor: string | null;
  results: SearchResultItem[];
};

/** Query params accepted by `fetchSearch`. */
export type SearchParams = {
  q: string;
  types?: string[];
  /** Per-type facet filters (each scopes to its own type). */
  years?: string[];
  sponsors?: string[];
  awardClasses?: string[];
  countries?: string[];
  sort?: SearchSort;
  cursor?: string;
  limit?: number;
};

/** Why Mylo can or cannot reach a lab and its people.
 *
 * `linked`/`dm_ok` are independent of guild membership: a personal DM works through
 * the person's own installation, so someone who left the lab's server still gets
 * their reminders — they just cannot be tagged in a channel post. */
export type DiscordChannelHealth = {
  bound: boolean;
  channel_id: string;
  ok: boolean | null;
  verified_at: string | null;
};

export type DiscordMemberHealth = {
  username: string;
  name: string;
  role: string;
  linked: boolean;
  dm_ok: boolean | null;
  checked_at?: string | null;
};

export type DiscordHealth = {
  guild: {
    state: "pending_setup" | "active" | "kicked" | null;
    guild_name: string | null;
    checked_at: string | null;
  };
  channels: {
    announcements: DiscordChannelHealth;
    updates: DiscordChannelHealth;
  };
  addon: { active: boolean | null };
  members: DiscordMemberHealth[];
};

/** Discord link status for the profile "Connected services" card. */
export type DiscordStatus = {
  connected: boolean;
  state: "pending" | "active" | "revoked" | null;
  link_method: "oauth" | "activation_code" | null;
  username: string | null;
  global_name: string | null;
  dm_ok: boolean | null;
  dm_checked_at: string | null;
  linked_at: string | null;
  /** When true, this user is excluded from the daily "Mylo Report" PDF DM. */
  daily_report_opt_out: boolean;
};

/** Whether a Lab's Discord server is synced (Manage & Invite page badge). */
export type DiscordGuildStatus = {
  synced: boolean;
  state: "pending_setup" | "active" | "kicked" | null;
  guild_id: string | null;
  guild_name: string | null;
  verified: boolean;
  confirmed_at: string | null;
};

/** GET /integrations/discord/start (and guild/start) → the URL to redirect to. */
export type DiscordStartResponse = { authorize_url: string };

/** POST /integrations/discord/code → a one-time activation code (Path B). */
export type DiscordCodeResponse = {
  code: string;
  expires_in: number;
  activation_channel: string | null;
};

/** POST /integrations/discord/lab-code?lab=<slug> → a 10-digit lab code (Path C). */
export type DiscordLabCodeResponse = {
  code: string;
  expires_in: number;
};

/** Feature slugs the UI gates on — mirror of apps.billing.entitlements.Feature. */
export const FEATURE = {
  SCHEDULED_REPORTS: "scheduled_reports",
  LLM_FIT_SCORING: "llm_fit_scoring",
  GRANT_ALERTS: "grant_alerts",
  FELLOWSHIP_MATCHING: "fellowship_matching",
  CONFERENCE_ALERTS: "conference_alerts",
  CUSTOM_TOPIC_FEEDS: "custom_topic_feeds",
  API_ACCESS: "api_access",
  BOT_DM: "bot_dm",
  BOT_SERVER: "bot_server",
  DEADLINE_REMINDERS: "deadline_reminders",
} as const;

/** GET /billing/me → the signed-in user's resolved entitlements (read-time gate). */
/** One plan active on the account — the personal plan or a lab/department seat. */
export type PlanSummary = {
  scope_type: "personal" | "lab" | "department";
  /** Lab slug or department id, for linking to management; null for personal. */
  scope_slug: string | null;
  scope_name: string;
  tier: "free" | "spore" | "lab" | "canopy";
  status: string;
  seat_status: string | null;
  payer_type: string | null;
  current_period_end: string | null;
};

export type Entitlements = {
  tier: "free" | "spore" | "lab" | "canopy";
  features: string[];
  topic_cap: number;
  /** How many interest clusters (distinct searches) the tier allows. */
  cluster_cap: number;
  /** How many search terms one cluster may hold under the tier. */
  cluster_topic_cap: number;
  topics_used: number;
  seat_count: number;
  pi_cap: number | null;
  addons: string[];
  /** Every subscription active on the account (account visibility). */
  plans: PlanSummary[];
};

/** A lab or department plan's seat-priced state (cents; nothing is charged). */
export type OrgBilling = {
  scope_type: "lab" | "department";
  scope_slug: string | null;
  scope_name: string;
  tier: "lab" | "canopy" | null;
  status: string | null;
  is_active: boolean;
  /**
   * A complimentary plan — fully entitled, never billed (a platform admin granted it
   * with no end date). Purely a pricing statement: the plan page strikes
   * `seat_price_cents` through rather than hiding it.
   */
  is_comped: boolean;
  /** Whether Mylo on Discord (the `bot_server` add-on) is part of this plan. */
  mylo_included: boolean;
  /**
   * The roster the plan covers. Distinct from `seat_count`, which counts already-ACTIVE
   * seats — before activation every seat is PENDING, so only this prices the plan a
   * manager is about to switch on. It is why a Lab plan is bought on the lab.
   */
  member_count: number;
  /** What activating now would cost per month: the roster at the per-member rate. */
  activation_monthly_cents: number;
  seat_count: number;
  seat_price_cents: number;
  recurring_monthly_cents: number;
  add_member_proration_cents: number;
  current_period_start: string | null;
  current_period_end: string | null;
  /** When the plan stops granting entitlements; null = it never ends. */
  expires_at: string | null;
  activated_at: string | null;
  can_manage: boolean;
};

/** A row in a department's effective-membership roster. */
export type DeptMemberRow = {
  username: string;
  name: string;
  initials: string;
  email: string;
  role: LabRole;
  source: "direct" | "lab";
  lab: string | null;
  seat_status: string | null;
};

/** A lab under a department (department labs card). */
export type DeptLabRow = {
  slug: string;
  name: string;
  member_count: number;
  has_logo: boolean;
  /** Whether this lab's members are covered (and paid for) by the department plan. */
  included_in_plan: boolean;
};

// -- Admin dashboard (staff/superuser only, GET/PATCH /api/admin/users) --------

/** Subscription tiers, as the admin API reports them. */
export type AdminTier = "free" | "spore" | "lab" | "canopy";

/**
 * The tiers each scope is actually *sold*. A tier names who it covers, so Mycelium Lab
 * and Canopy are granted on a lab or department — where a roster exists to price them —
 * and never on a personal account. The API narrows its choices the same way, so sending
 * an out-of-scope tier is a 400 on the `tier` field.
 */
export type AdminPersonalTier = "free" | "spore";
export type AdminLabTier = "lab" | "canopy";

/** Subscription statuses the admin API reports and accepts. */
export type AdminSubscriptionStatus = "active" | "past_due" | "canceled";

/** The personal subscription an admin manages for a user (null if they have none). */
export type AdminSubscriptionSummary = {
  tier: AdminTier;
  status: AdminSubscriptionStatus;
  expires_at: string | null;
};

/** One user row in the admin table (GET /admin/users/ → results[]). */
export type AdminUserRow = {
  id: number;
  username: string;
  email: string;
  name: string;
  is_staff: boolean;
  is_superuser: boolean;
  is_active: boolean;
  date_joined: string;
  effective_tier: AdminTier;
  subscription: AdminSubscriptionSummary | null;
  watch_topics_used: number;
  watch_topic_cap: number;
  watch_topic_limit: number | null;
};

/** A single user's full admin view (GET /admin/users/<id>/). */
export type AdminUserDetail = AdminUserRow & {
  academic_title: string;
  watch_topics: string[];
  watch_categories: string[];
  lab_memberships: {
    slug: string;
    name: string;
    role: LabRole;
    is_lead: boolean;
  }[];
};

/** One page of the admin roster (DRF PageNumberPagination envelope). */
export type AdminUsersPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AdminUserRow[];
};

/** Query params for the admin roster. */
export type AdminUsersQuery = {
  q?: string;
  page?: number;
  pageSize?: number;
};

/**
 * A partial admin PATCH over a user's plan + watch quota. Only the keys sent are
 * applied; `duration_days`/`expires_at` are mutually exclusive, and either sent
 * as null clears the expiry (open-ended). `watch_topic_limit: null` clears the
 * override back to the tier cap.
 */
export type AdminUserUpdate = {
  tier?: AdminPersonalTier;
  duration_days?: number | null;
  expires_at?: string | null;
  subscription_status?: AdminSubscriptionStatus;
  watch_topic_limit?: number | null;
};

// -- Admin dashboard, Labs context (GET/PATCH /api/admin/labs) -----------------

/**
 * Org plans additionally use `inactive` — the created-but-not-yet-granting state every
 * lab/department plan starts in.
 */
export type AdminOrgStatus = "inactive" | "active" | "past_due" | "canceled";

/** A lab's plan as the admin dashboard reports it. */
export type AdminLabSubscription = {
  tier: AdminTier;
  status: AdminOrgStatus;
  /** When the plan stops granting entitlements; null = it never ends. */
  expires_at: string | null;
  /** Complimentary — entitled but never billed (a free lab). */
  is_comped: boolean;
  /** Whether Mylo on Discord is part of the plan (the `bot_server` add-on). */
  mylo_included: boolean;
  seat_count: number;
  seat_price_cents: number;
  recurring_monthly_cents: number;
  current_period_start: string | null;
  current_period_end: string | null;
  activated_at: string | null;
  billing_interval: string;
};

/** One lab row in the admin table (GET /admin/labs/ → results[]). */
export type AdminLabRow = {
  slug: string;
  name: string;
  created_at: string;
  department: { id: string; name: string; included_in_plan: boolean } | null;
  member_count: number;
  subscription: AdminLabSubscription | null;
};

/** A single lab's full admin view (GET /admin/labs/<slug>/). */
export type AdminLabDetail = AdminLabRow & {
  timezone: string;
  leads: { username: string; name: string; role: LabRole; is_lead: boolean }[];
  watch_topics: string[];
  watch_categories: string[];
};

/** One page of the admin lab roster (same DRF envelope as the user roster). */
export type AdminLabsPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AdminLabRow[];
};

/**
 * A partial admin PATCH over a lab's plan. Only the keys sent are applied;
 * `duration_days`/`expires_at` are mutually exclusive, and either sent as null means
 * the plan never ends. Setting `status: "active"` runs the shared activation service,
 * which opens the billing period and seats every member.
 */
export type AdminLabUpdate = {
  tier?: AdminLabTier;
  status?: AdminOrgStatus;
  duration_days?: number | null;
  expires_at?: string | null;
  is_comped?: boolean;
  mylo_included?: boolean;
};

/** A department the caller owns or is a direct member of. */
export type MyDepartment = {
  id: string;
  name: string;
  institution: string;
  role: string;
  is_owner: boolean;
  can_manage: boolean;
};

/**
 * One way into a lab or department — the manager's view, so it carries the URL.
 *
 * `kind: "email"` is bound to one address and worth exactly one use. `kind:
 * "link"` is bound to nobody, so `max_uses` and `expires_at` are what hold it.
 */
export type OrgInvite = {
  id: string;
  kind: "email" | "link";
  role: string;
  email: string;
  message: string;
  url: string;
  max_uses: number;
  used_count: number;
  uses_left: number;
  expires_at: string;
  revoked_at: string | null;
  is_live: boolean;
  created_at: string;
  created_by: string;
};

/** What a manager fills in to create an invitation. */
export type OrgInviteInput = {
  kind: "email" | "link";
  email?: string;
  role?: string;
  max_uses?: number;
  expires_in_days?: number;
  message?: string;
};


/* -- Project state ---------------------------------------------------------- */

/**
 * What a project claims, what blocks it, and what is due when
 * (`/api/projects/<id>/state/`).
 *
 * Split in two because the halves change at different speeds. `slow` is the
 * research identity — editing it invalidates Mylo's written reasoning about the
 * project, so it is worth a confirmation step. `fast` is operational and is read
 * by deterministic matchers that cost nothing to re-run, so a milestone can be
 * moved freely.
 *
 * `provenance` is what separates what the team said from what Mylo guessed.
 * Every surface shows the difference, and a `stated` field is never auto-edited.
 */
export type ProjectStateSlow = {
  problem: string;
  claimed_contribution: string;
  method: string[];
  planned_components: string[];
  data: string[];
  blockers: { id: string; text: string }[];
};

export type ProjectMilestone = {
  id: string;
  /** `results_by` for an abstract-only venue, `draft_by` for a full paper. */
  kind: "results_by" | "draft_by" | "submit_by" | "other";
  what: string;
  /** ISO date, or `""` when the team has not set one — never a guess. */
  date: string;
  source: string;
};

export type ProjectConstraint = {
  id: string;
  kind: "earliest_start" | "latest_end" | "embargo" | "other";
  applies_to: string;
  date: string;
  note: string;
};

export type ProjectStateFast = {
  stage: string;
  milestones: ProjectMilestone[];
  venue_targets: { venue: string; slot: string; fallback: string }[];
  constraints: ProjectConstraint[];
  /** `null` on either half means "inherit" — the lab's, then yours, then 14/60. */
  timeline_overrides: {
    deadline_buffer_days: number | null;
    min_paper_window_days: number | null;
  };
  needs: { expertise: string[] };
  known_literature: { collections: string[]; suppress_known: boolean };
  exclusions: string[];
};

/** Where a resolved timeline setting came from, for "buffer 14 (yours)". */
export type TimelineSource = "project" | "lab" | "you" | "default";

export type ProjectStatePayload = {
  project_id: string;
  slow: ProjectStateSlow;
  fast: ProjectStateFast;
  provenance: Record<string, "stated" | "inferred">;
  state_version: number;
  slow_fingerprint: string;
  confirmed_at: string | null;
  /** `null` means never confirmed, which is a prompt; `0` is reassurance. */
  days_since_confirmed: number | null;
  /** True when nobody has answered yet — a prompt, not a blank document. */
  is_empty: boolean;
  effective_timeline: {
    buffer_days: number;
    window_days: number;
    buffer_source: TimelineSource;
    window_source: TimelineSource;
  };
};

/** A partial state edit. Merged server-side, so send only what changed. */
export type ProjectStateInput = {
  slow?: Partial<ProjectStateSlow>;
  fast?: Partial<ProjectStateFast>;
  provenance?: Record<string, "stated" | "inferred">;
};

/**
 * What one document yielded when Mylo read a project out of it. Nothing here is
 * saved: every field comes back marked `inferred` and it is the reader who
 * decides whether to apply it, because an extractor that wrote straight into the
 * state would overwrite what the team said with what a model read.
 */
export type ProjectStateProposal = {
  ok: boolean;
  /** Why it refused, in words a person can act on. Empty on success. */
  reason: string;
  attempts: number;
  failures: string[];
  proposal: ProjectStateInput;
};
