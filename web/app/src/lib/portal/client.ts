import { ApiError } from "@/lib/api-error";
import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import type {
  AdminLabDetail,
  AdminLabsPage,
  AdminUserDetail,
  AdminUsersPage,
  AdminUsersQuery,
  CollectionBrief,
  CollectionDetail,
  ConferenceOpportunity,
  DailyBriefing,
  DailyBriefingSummary,
  DailyReport,
  DeptLabRow,
  DeptMemberRow,
  DiscordGuildStatus,
  DiscordHealth,
  DiscordStartResponse,
  DiscordStatus,
  Entitlements,
  OrgBilling,
  GrantOpportunity,
  FellowshipsFeed,
  LabMember,
  LabProfileData,
  MemberSuggestionsFeed,
  MyInvitation,
  MyLab,
  NotificationFeed,
  OpportunityFeed,
  Project,
  ProjectRecommendations,
  LabReminderChannels,
  ProfileData,
  ProjectFeed,
  Reminder,
  ReminderAccess,
  SavedDeadline,
  LabSavesResponse,
  SavedItem,
  SearchParams,
  SearchResponse,
  PersonalWindowCounts,
  TargetRecommendations,
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
    // Keep the friendly message the UI surfaces, but carry the status so the
    // query client can skip retrying a 401/403 (deauth) instead of hammering.
    throw new ApiError(whatFailed, response.status);
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

/** The cross-category "Mylo Report" briefing (the Daily page's three zones). */
export async function fetchDailyBriefing(): Promise<DailyBriefing> {
  return getJson<DailyBriefing>(
    buildApiUrl(getPublicApiBase(), "daily-briefing"),
    "Could not load your daily briefing.",
  );
}

/** A lab's "Mylo Report" briefing (the lab overview's written zone). */
export async function fetchLabDailyBriefing(
  slug: string,
): Promise<DailyBriefing> {
  return getJson<DailyBriefing>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "daily-briefing"),
    "Could not load the lab's daily briefing.",
  );
}

/** The caller's retained briefings, newest day first — dates and counts only. */
export async function fetchBriefings(): Promise<DailyBriefingSummary[]> {
  return getJson<DailyBriefingSummary[]>(
    buildApiUrl(getPublicApiBase(), "briefings"),
    "Could not load your report history.",
  );
}

/** One archived day, in the same envelope the Daily page renders. */
export async function fetchBriefingByDate(date: string): Promise<DailyBriefing> {
  return getJson<DailyBriefing>(
    buildApiUrl(getPublicApiBase(), "briefings", date),
    "Could not load that report.",
  );
}

/** A lab's retained briefings, newest day first — dates and counts only. */
export async function fetchLabBriefings(
  slug: string,
): Promise<DailyBriefingSummary[]> {
  return getJson<DailyBriefingSummary[]>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "briefings"),
    "Could not load the lab's report history.",
  );
}

/** One archived day for a lab, in the same envelope as the lab's current one. */
export async function fetchLabBriefingByDate(
  slug: string,
  date: string,
): Promise<DailyBriefing> {
  return getJson<DailyBriefing>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "briefings", date),
    "Could not load that report.",
  );
}

/**
 * The `<img src>` for a lab's logo, served through the API gateway. `version` is
 * the cache-busting token from `MyLab.logo_version`; pass it so a re-upload shows
 * immediately. Returns null when the lab has no logo.
 */
export function labLogoUrl(slug: string, version: number | null): string | null {
  if (version === null || version === undefined) {
    return null;
  }
  return `${buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "logo")}?v=${version}`;
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
export async function fetchFellowships(): Promise<FellowshipsFeed> {
  return getJson<FellowshipsFeed>(
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

/** The signed-in user's own "what Mylo found" recency matrix (personal Overview). */
export async function fetchWindowCounts(): Promise<PersonalWindowCounts> {
  return getJson<PersonalWindowCounts>(
    buildApiUrl(getPublicApiBase(), "recommendations", "window-counts"),
    "Could not load what Mylo found.",
  );
}

/** Every bookmark with feed-parity card payloads (Saves page). */
export async function fetchSaves(): Promise<{ items: SavedItem[] }> {
  return getJson<{ items: SavedItem[] }>(
    buildApiUrl(getPublicApiBase(), "saves"),
    "Could not load your saves.",
  );
}

/** A lab's shared saves with feed-parity cards (lab Saves area). */
export async function fetchLabSaves(slug: string): Promise<LabSavesResponse> {
  return getJson<LabSavesResponse>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "saves"),
    "Could not load this lab's saves.",
  );
}

/** The header bell: reminder / moved-deadline / high-signal notifications. */
export async function fetchNotifications(): Promise<NotificationFeed> {
  return getJson<NotificationFeed>(
    buildApiUrl(getPublicApiBase(), "notifications"),
    "Could not load your notifications.",
  );
}

/** The caller's deadline reminders (personal + accessible lab reminders). */
export async function fetchReminders(): Promise<{ items: Reminder[] }> {
  return getJson<{ items: Reminder[] }>(
    buildApiUrl(getPublicApiBase(), "reminders"),
    "Could not load your reminders.",
  );
}

/** Whether the caller may set a reminder — personally, or for `labSlug`.
 *
 * The server computes this with the same module the create path enforces with, so
 * the button state cannot drift from the rule that would reject the POST. */
export async function fetchReminderAccess(
  labSlug?: string,
): Promise<ReminderAccess> {
  const base = buildApiUrl(getPublicApiBase(), "reminders", "access");
  const url = labSlug ? `${base}?lab=${encodeURIComponent(labSlug)}` : base;
  return getJson<ReminderAccess>(
    url,
    "Could not check whether reminders are available.",
  );
}

/** A lab's postable Discord channels + its `/setup` default, for the reminder
 * channel picker (manager-only). Degrades to an empty roster server-side. */
export async function fetchLabReminderChannels(
  slug: string,
): Promise<LabReminderChannels> {
  const base = buildApiUrl(getPublicApiBase(), "reminders", "lab-channels");
  return getJson<LabReminderChannels>(
    `${base}?lab=${encodeURIComponent(slug)}`,
    "Could not load the lab's channels.",
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

/** What Mylo watches for a lab (same shape as a user's watch settings). */
export async function fetchLabWatch(slug: string): Promise<WatchData> {
  return getJson<WatchData>(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "watch"),
    "Could not load the lab's watch settings.",
  );
}

/** A lab's matched papers, grants, and conferences (its aggregate interests). */
export async function fetchLabRecommendations(
  slug: string,
): Promise<TargetRecommendations> {
  return getJson<TargetRecommendations>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "recommendations"),
    "Could not load the lab's recommendations.",
  );
}

/** One project's matched papers, grants, fellowships, and conferences (its
 * declared focus) — the full, uncapped lists. */
export async function fetchProjectRecommendations(
  id: string,
): Promise<ProjectRecommendations> {
  return getJson<ProjectRecommendations>(
    buildApiUrl(getPublicApiBase(), "projects", id, "recommendations"),
    "Could not load the project's recommendations.",
  );
}

/**
 * "Mylo's picks" for a project — the same recommendations, capped to the
 * digest slice (top 10 papers / 5 grants / 5 fellowships / 5 conferences,
 * passed-deadline conferences dropped). `counts` still reflects the full
 * totals, so the UI can show "top 5 of N".
 */
export async function fetchProjectDigest(
  id: string,
): Promise<ProjectRecommendations> {
  const base = buildApiUrl(getPublicApiBase(), "projects", id, "recommendations");
  return getJson<ProjectRecommendations>(
    `${base}?digest=1`,
    "Could not load Mylo's picks for this project.",
  );
}

/** A project's team-shared feed — papers members pasted in or pushed from Mylo's picks. */
export async function fetchProjectFeed(id: string): Promise<ProjectFeed> {
  return getJson<ProjectFeed>(
    buildApiUrl(getPublicApiBase(), "projects", id, "feed"),
    "Could not load the project's shared feed.",
  );
}

/** A project's shared reading lists (non-archived by default). */
export async function fetchProjectCollections(
  id: string,
  options?: { archived?: boolean },
): Promise<{ count: number; items: CollectionBrief[] }> {
  const base = buildApiUrl(getPublicApiBase(), "projects", id, "collections");
  const url = options?.archived ? `${base}?archived=1` : base;
  return getJson<{ count: number; items: CollectionBrief[] }>(
    url,
    "Could not load the project's collections.",
  );
}

/** One collection's full detail, including its items. */
export async function fetchProjectCollection(
  id: string,
  collectionId: string,
): Promise<CollectionDetail> {
  return getJson<CollectionDetail>(
    buildApiUrl(
      getPublicApiBase(),
      "projects",
      id,
      "collections",
      collectionId,
    ),
    "Could not load this collection.",
  );
}

/** Papers teammates shared that closely match the caller's own profile. */
export async function fetchMemberSuggestions(): Promise<MemberSuggestionsFeed> {
  return getJson<MemberSuggestionsFeed>(
    buildApiUrl(getPublicApiBase(), "suggestions"),
    "Could not load your suggestions.",
  );
}

/** Query-first search across the content corpus (GET /api/search/). */
export async function fetchSearch(
  params: SearchParams,
): Promise<SearchResponse> {
  const search = new URLSearchParams();
  search.set("q", params.q);
  for (const type of params.types ?? []) {
    search.append("type", type);
  }
  // Per-type facet filters — each key scopes to its own content type server-side.
  const facetParams: [string, string[] | undefined][] = [
    ["year", params.years],
    ["sponsor", params.sponsors],
    ["award_class", params.awardClasses],
    ["country", params.countries],
  ];
  for (const [key, values] of facetParams) {
    for (const value of values ?? []) {
      search.append(key, value);
    }
  }
  if (params.sort) {
    search.set("sort", params.sort);
  }
  if (params.cursor) {
    search.set("cursor", params.cursor);
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  const url = `${buildApiUrl(getPublicApiBase(), "search")}?${search.toString()}`;
  return getJson<SearchResponse>(url, "Search failed. Please try again.");
}

/** The caller's Discord link status (profile card). */
export async function fetchDiscordStatus(): Promise<DiscordStatus> {
  return getJson<DiscordStatus>(
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "status"),
    "Could not load your Discord connection.",
  );
}

export async function fetchEntitlements(): Promise<Entitlements> {
  return getJson<Entitlements>(
    buildApiUrl(getPublicApiBase(), "billing", "me"),
    "Could not load your plan details.",
  );
}

/** A lab's seat-priced plan state (any member reads; managers can activate). */
export async function fetchLabBilling(slug: string): Promise<OrgBilling> {
  return getJson<OrgBilling>(
    buildApiUrl(getPublicApiBase(), "labs", slug, "billing"),
    "Could not load the lab plan.",
  );
}

/** A department's seat-priced plan state. */
export async function fetchDeptBilling(id: string): Promise<OrgBilling> {
  return getJson<OrgBilling>(
    buildApiUrl(getPublicApiBase(), "departments", id, "billing"),
    "Could not load the department plan.",
  );
}

/** A department's effective-membership roster (direct members + lab members). */
export async function fetchDeptMembers(id: string): Promise<DeptMemberRow[]> {
  return getJson<DeptMemberRow[]>(
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "members"),
    "Could not load the department members.",
  );
}

/** The labs under a department. */
export async function fetchDeptLabs(id: string): Promise<DeptLabRow[]> {
  return getJson<DeptLabRow[]>(
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "labs"),
    "Could not load the department's labs.",
  );
}

/** Begin the user OAuth link — returns the Discord authorize URL to redirect to. */
export async function fetchDiscordStart(): Promise<DiscordStartResponse> {
  return getJson<DiscordStartResponse>(
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "start"),
    "Could not start the Discord connection.",
  );
}

/** Whether a lab's Discord server is synced (Manage & Invite page; managers). */
export async function fetchLabDiscordStatus(
  slug: string,
): Promise<DiscordGuildStatus> {
  const url = buildApiUrl(getPublicApiBase(), "integrations", "discord", "guild", "status");
  return getJson<DiscordGuildStatus>(
    `${url}?lab=${encodeURIComponent(slug)}`,
    "Could not load this lab's Discord connection.",
  );
}

/** A lab's Discord health: guild, channels, add-on, and per-member reachability. */
export async function fetchLabDiscordHealth(slug: string): Promise<DiscordHealth> {
  const url = buildApiUrl(getPublicApiBase(), "integrations", "discord", "health");
  return getJson<DiscordHealth>(
    `${url}?lab=${encodeURIComponent(slug)}`,
    "Could not load this lab's Discord health.",
  );
}

/** Begin the guild install for a lab — returns the Discord authorize URL. */
export async function fetchLabDiscordStart(
  slug: string,
): Promise<DiscordStartResponse> {
  const url = buildApiUrl(getPublicApiBase(), "integrations", "discord", "guild", "start");
  return getJson<DiscordStartResponse>(
    `${url}?lab=${encodeURIComponent(slug)}`,
    "Could not start adding Mylo to your server.",
  );
}

/** One page of the admin user roster (staff/superuser only; the API 403s else). */
export async function fetchAdminUsers(
  params: AdminUsersQuery,
): Promise<AdminUsersPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.page) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  const base = buildApiUrl(getPublicApiBase(), "admin", "users");
  const qs = search.toString();
  return getJson<AdminUsersPage>(
    qs ? `${base}?${qs}` : base,
    "Could not load the user list.",
  );
}

/** One user's full admin detail (staff/superuser only). */
export async function fetchAdminUser(id: number): Promise<AdminUserDetail> {
  return getJson<AdminUserDetail>(
    buildApiUrl(getPublicApiBase(), "admin", "users", String(id)),
    "Could not load this user.",
  );
}

/** One page of the admin lab roster (staff/superuser only; the API 403s else). */
export async function fetchAdminLabs(
  params: AdminUsersQuery,
): Promise<AdminLabsPage> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.page) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  const base = buildApiUrl(getPublicApiBase(), "admin", "labs");
  const qs = search.toString();
  return getJson<AdminLabsPage>(
    qs ? `${base}?${qs}` : base,
    "Could not load the lab list.",
  );
}

/** One lab's full admin detail (staff/superuser only). */
export async function fetchAdminLab(slug: string): Promise<AdminLabDetail> {
  return getJson<AdminLabDetail>(
    buildApiUrl(getPublicApiBase(), "admin", "labs", slug),
    "Could not load this lab.",
  );
}
