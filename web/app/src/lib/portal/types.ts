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

export type Project = {
  id: string;
  name: string;
  scope: ProjectScope;
  scope_name: string;
  goals: Record<string, unknown>;
  /** Optional display hints read from `goals`; null when the author set none. */
  status: string | null;
  progress: number | null;
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
  source: string;
  url: string;
  venue: string;
  year: number | null;
  authors: string[];
  score: number;
  /** The model's 0–100 percent match for this researcher (null if unscored). */
  match_percent: number | null;
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
  origin: "llm" | "fallback";
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
};

/** A ranked opportunity feed for one area. */
export type OpportunityFeed<T> = {
  generated_at: string | null;
  items: T[];
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
