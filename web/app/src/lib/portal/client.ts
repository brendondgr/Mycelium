import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import type {
  ConferenceOpportunity,
  DailyReport,
  FellowshipOpportunity,
  GrantOpportunity,
  LabMember,
  LabProfileData,
  MyInvitation,
  MyLab,
  NotificationFeed,
  OpportunityFeed,
  Project,
  ProfileData,
  SavedDeadline,
  WatchData,
} from "@/lib/portal/types";

/* Re-exported shape: a lab's watch settings share the user's WatchData shape. */

/**
 * Browser-side reads for the workspace dashboard. GET-only, so no CSRF token is
 * needed; `credentials: "include"` carries the session cookie through the Next
 * proxy. Each throws a friendly message the UI can surface as an error state.
 */

async function getJson<T>(url: string, whatFailed: string): Promise<T> {
  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(whatFailed);
  }
  return (await response.json()) as T;
}

export async function fetchMyLabs(): Promise<MyLab[]> {
  return getJson<MyLab[]>(
    buildApiUrl(getPublicApiBase(), "auth", "labs"),
    "Could not load your labs.",
  );
}

export async function fetchLabMembers(slug: string): Promise<LabMember[]> {
  return getJson<LabMember[]>(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "members"),
    "Could not load the lab members.",
  );
}

export async function fetchProjects(labSlug?: string): Promise<Project[]> {
  const base = buildApiUrl(getPublicApiBase(), "projects");
  const url = labSlug ? `${base}?lab=${encodeURIComponent(labSlug)}` : base;
  return getJson<Project[]>(url, "Could not load your projects.");
}

/** Every project of a lab (any lab member may browse them to join). */
export async function fetchLabProjects(slug: string): Promise<Project[]> {
  return getJson<Project[]>(
    buildApiUrl(getPublicApiBase(), "projects", "lab", slug),
    "Could not load the lab's projects.",
  );
}

export async function fetchProfile(): Promise<ProfileData> {
  return getJson<ProfileData>(
    buildApiUrl(getPublicApiBase(), "auth", "profile", "me"),
    "Could not load your profile.",
  );
}

export async function fetchWatch(): Promise<WatchData> {
  return getJson<WatchData>(
    buildApiUrl(getPublicApiBase(), "auth", "watch", "me"),
    "Could not load your watch settings.",
  );
}

export async function fetchDailyReport(): Promise<DailyReport> {
  return getJson<DailyReport>(
    buildApiUrl(getPublicApiBase(), "daily-report"),
    "Could not load your daily report.",
  );
}

/** The user's ranked funding opportunities (Opportunities page, grants column). */
export async function fetchGrants(): Promise<OpportunityFeed<GrantOpportunity>> {
  return getJson<OpportunityFeed<GrantOpportunity>>(
    buildApiUrl(getPublicApiBase(), "opportunities", "grants"),
    "Could not load your grants.",
  );
}

/** The user's ranked conferences (Conferences page). */
export async function fetchConferences(): Promise<
  OpportunityFeed<ConferenceOpportunity>
> {
  return getJson<OpportunityFeed<ConferenceOpportunity>>(
    buildApiUrl(getPublicApiBase(), "opportunities", "conferences"),
    "Could not load your conferences.",
  );
}

/** The user's matched fellowships (Fellowships page). */
export async function fetchFellowships(): Promise<
  OpportunityFeed<FellowshipOpportunity>
> {
  return getJson<OpportunityFeed<FellowshipOpportunity>>(
    buildApiUrl(getPublicApiBase(), "opportunities", "fellowships"),
    "Could not load your fellowships.",
  );
}

/** The user's saved deadlines (Deadlines page). */
export async function fetchDeadlines(): Promise<{ items: SavedDeadline[] }> {
  return getJson<{ items: SavedDeadline[] }>(
    buildApiUrl(getPublicApiBase(), "deadlines"),
    "Could not load your deadlines.",
  );
}

/** Deadline alerts due within a week (the header bell). */
export async function fetchNotifications(): Promise<NotificationFeed> {
  return getJson<NotificationFeed>(
    buildApiUrl(getPublicApiBase(), "notifications"),
    "Could not load your notifications.",
  );
}

/** The caller's pending lab invitations — powers the notifications panel. */
export async function fetchMyInvitations(): Promise<MyInvitation[]> {
  return getJson<MyInvitation[]>(
    buildApiUrl(getPublicApiBase(), "auth", "invitations"),
    "Could not load your invitations.",
  );
}

/** A lab's collective purpose & goals. */
export async function fetchLabProfile(slug: string): Promise<LabProfileData> {
  return getJson<LabProfileData>(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "profile"),
    "Could not load the lab's purpose and goals.",
  );
}

/** What Milo watches for a lab (same shape as a user's watch settings). */
export async function fetchLabWatch(slug: string): Promise<WatchData> {
  return getJson<WatchData>(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "watch"),
    "Could not load the lab's watch settings.",
  );
}
