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

/** What Milo watches for the caller (from `/api/auth/watch/me/`). */
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
  /** Interest label -> [0,1] fusion score; drives the derived per-category %. */
  per_interest: Record<string, number>;
  /** Interest labels this paper matched — the source of the page's filter chips. */
  matched_interests: string[];
  rank: number | null;
  headline: string;
  reason: string;
  /** "llm" when Mylo wrote the reason, "fallback" when it was templated. */
  origin: "llm" | "fallback";
};

/**
 * A plain roll-up of the day's suggested papers (from `/api/daily-report/`).
 * Powers the Daily Report page; the papers themselves live on Research Papers.
 */
export type DailyReportSummary = {
  paper_count: number;
  strong_matches: number;
  top_match: number | null;
  average_match: number | null;
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

/* -- Opportunities: grants, conferences, deadlines -------------------------- */

/** Fields shared by a matched grant and a matched conference. */
type OpportunityBase = {
  content_id: string;
  title: string;
  url: string;
  score: number;
  /** The model's 0–100 fit judgement (null on the fallback tail). */
  match_percent: number | null;
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
  /** When Milo first surfaced this grant (ISO or ""). */
  posted: string;
  /** A human-readable blurb (AI summary or abstract), or "". */
  description: string;
};

/** A matched conference (from `/api/opportunities/conferences/`). */
export type ConferenceOpportunity = OpportunityBase & {
  location: string;
  country: string;
  event_dates: string;
  deadlines: string;
  keywords: string;
  /** Semicolon-delimited subject categories — clean tags (unlike keywords). */
  matched_subjects: string;
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

/** One saved deadline (from `/api/deadlines/`). */
export type SavedDeadline = {
  id: string;
  content_id: string | null;
  area: "grant" | "conference" | "fellowship";
  title: string;
  url: string;
  subtitle: string;
  deadline_date: string | null;
  deadline_kind: string;
  note: string;
  days_remaining: number | null;
  within_week: boolean;
};

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
};
