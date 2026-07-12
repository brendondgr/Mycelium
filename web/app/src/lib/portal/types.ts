/** Shapes returned by the workspace read endpoints (see docs/api-contract.md). */

import type { ResearchInterests, WatchCadence } from "@/lib/auth-types";

export type LabRole = "owner" | "admin" | "member" | "viewer";

/** One of the signed-in user's lab memberships — powers the workspace switcher. */
export type MyLab = {
  slug: string;
  name: string;
  role: LabRole;
  is_lead: boolean;
  department: string | null;
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
};

export type Project = {
  id: string;
  name: string;
  scope: ProjectScope;
  scope_name: string;
  goals: Record<string, unknown>;
  /** Optional display hints read from `goals`; null when the author set none. */
  status: string | null;
  progress: number | null;
  /** Normalized research focus (areas/keywords/statement/watch topics). */
  focus: ProjectFocus;
  member_count: number;
  /** Whether the signed-in user belongs to this project. */
  is_member: boolean;
  members: ProjectMember[];
  updated_at: string;
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
  /** The model's 0–100 percent match for this researcher (null if unscored). */
  match_percent: number | null;
  /** The transformer (embedding) cosine match, 0–100, this paper cleared to be
   * surfaced — shown on the cross-embedding tail in place of the model's percent.
   * null on legacy rows written before the threshold. */
  embedding_match: number | null;
  /** Interest label -> [0,1] fusion score; drives the derived per-category %. */
  per_interest: Record<string, number>;
  /** Interest labels this paper matched — the source of the page's filter chips. */
  matched_interests: string[];
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
};

/**
 * A plain roll-up of the day's suggested papers (from `/api/daily-report/`).
 * Powers the Daily Report page; the papers themselves live on Research Papers.
 */
export type DailyReportSummary = {
  paper_count: number;
  /** How many of the matched papers are new this week (pinned to the top). */
  new_count: number;
  strong_matches: number;
  top_match: number | null;
  average_match: number | null;
  /** The embedding-match floor (percent) each surfaced paper had to clear. */
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
  suggestions: Suggestion[];
};

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
  match_percent: number | null;
  headline: string;
  deadline_date: string;
  is_new: boolean;
};

/** The "Mylo Report" (from `/api/daily-briefing/`) — the Daily page's three zones. */
export type DailyBriefing = {
  /** ISO timestamp of the last briefing generation, or null before the first run. */
  generated_at: string | null;
  /** The categories this briefing covered (what the user watches). */
  categories: BriefingCategory[];
  /** Per-category item counts ("Today's Summaries"). */
  counts: Partial<Record<BriefingCategory, number>>;
  /** Items first seen this week, per category. Optional — absent on older,
   * already-persisted briefings that predate this field. */
  new_counts?: Partial<Record<BriefingCategory, number>>;
  /** Top items per category the prose is grounded in (the showcase). */
  showcase: Partial<Record<BriefingCategory, BriefingShowcaseItem[]>>;
  /** The written briefing, or null when no run has produced one yet. */
  briefing: { body: string; origin: "llm" | "fallback" } | null;
};

/* -- Opportunities: grants, conferences, deadlines -------------------------- */

/** Fields shared by a matched grant and a matched conference. */
type OpportunityBase = {
  content_id: string;
  title: string;
  url: string;
  score: number;
  /** The model's 0–100 fit judgement (null on the fallback tail). */
  match_percent: number | null;
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
  pinned: boolean;
  /** The actionable date (application/abstract/manuscript/event), ISO or "". */
  deadline_date: string;
  deadline_kind: string;
  status_summary: string;
  /** Whether the user has saved this to their deadlines. */
  saved: boolean;
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
  /** Pivot scope label (e.g. "International", "National"), or "". */
  scope: string;
};

/** A ranked opportunity feed for one area. */
export type OpportunityFeed<T> = {
  generated_at: string | null;
  items: T[];
};

/** A member who personally matched a shared item (the "who's interested" layer). */
export type InterestedMember = {
  username: string;
  name: string;
  initials: string;
  match_percent: number;
};

/**
 * A lab's or a project's combined recommendations (from
 * `/api/labs/<slug>/recommendations/` and `/api/projects/<id>/recommendations/`).
 * Papers + grants + conferences the target matched, plus per-area counts for the
 * overview stat cards. Fellowships are excluded — they are individual-only.
 * `interested` maps a content id to the members who personally matched it strongly,
 * so the UI can suggest who to connect over a shared item.
 */
export type TargetRecommendations = {
  generated_at: string | null;
  counts: { papers: number; grants: number; conferences: number };
  papers: Suggestion[];
  grants: GrantOpportunity[];
  conferences: ConferenceOpportunity[];
  interested: Record<string, InterestedMember[]>;
};

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

/** One deadline alert for the header bell (from `/api/notifications/`). */
export type DeadlineAlert = {
  id: string;
  content_id: string | null;
  area: "grant" | "conference" | "fellowship";
  title: string;
  url: string;
  deadline_date: string;
  days_remaining: number;
  message: string;
};

export type NotificationFeed = {
  count: number;
  items: DeadlineAlert[];
};

/**
 * A paper suggestion surfaced from a teammate's shared item (from
 * `/api/suggestions/`) — the "Suggested for you" surface. `match_percent` is
 * the caller's own personal fit for the shared paper.
 */
export type MemberSuggestion = {
  id: string;
  content_id: string;
  title: string;
  url: string;
  score: number;
  match_percent: number | null;
  project: { id: string; name: string };
  shared_by: ProjectMember | null;
  created_at: string;
};

export type MemberSuggestionsFeed = {
  count: number;
  items: MemberSuggestion[];
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
