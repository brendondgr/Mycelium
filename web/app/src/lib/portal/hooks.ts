"use client";

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  AgentError,
  deleteThread,
  fetchAgentCatalog,
  fetchAgentPolicy,
  fetchAgentPreferences,
  fetchAgentStatus,
  fetchThread,
  fetchThreads,
  saveAgentPolicy,
  saveAgentPreferences,
  updateThread,
  type ThreadQuery,
} from "@/lib/portal/agent/client";
import {
  availabilityFrom,
  type CatalogOutcome,
} from "@/lib/portal/agent/availability";
import type {
  AgentPolicy,
  AgentPreferences,
  ChatAvailability,
} from "@/lib/portal/agent/types";
import {
  fetchAnnouncements,
  fetchDeptOpportunities,
  fetchAdminLab,
  fetchAdminLabs,
  fetchAdminUser,
  fetchAdminUsers,
  fetchConferences,
  fetchBriefingByDate,
  fetchBriefings,
  fetchDailyBriefing,
  fetchDailyReport,
  fetchDeptDiscordStart,
  fetchDeptDiscordStatus,
  fetchDiscordStart,
  fetchDiscordStatus,
  fetchEntitlements,
  fetchLabBriefingByDate,
  fetchLabBriefings,
  fetchLabDailyBriefing,
  fetchLabDiscordStart,
  fetchLabDiscordHealth,
  fetchLabDiscordStatus,
  fetchLabSaves,
  fetchDeadlines,
  fetchFellowships,
  fetchGrants,
  fetchIgnored,
  fetchLabMembers,
  fetchDeptProfile,
  fetchLabProfile,
  fetchLabProjects,
  fetchDepartmentDailyBriefing,
  fetchDepartmentRecommendations,
  fetchLabRecommendations,
  fetchLabWatch,
  fetchMemberSuggestions,
  fetchLabMentionTargets,
  fetchLabReminderChannels,
  fetchDeptInvites,
  fetchLabInvites,
  fetchMyDepartments,
  fetchMyInvitations,
  fetchMyLabs,
  fetchNotifications,
  fetchReminderAccess,
  fetchReminders,
  fetchSaves,
  fetchProfile,
  fetchMyProjectInvitations,
  fetchProject,
  fetchProjectConversation,
  fetchProjectState,
  fetchReflections,
  fetchProjectCollection,
  fetchProjectCollections,
  fetchProjectDigest,
  fetchProjectFeed,
  fetchProjectInvitations,
  fetchProjectRecommendations,
  fetchProjects,
  fetchRankingReference,
  fetchSearch,
  fetchWatch,
  fetchWindowCounts,
  fetchLabBilling,
  fetchDeptBilling,
  fetchDeptMembers,
  fetchDeptLabs,
} from "@/lib/portal/client";
import {
  actOnNotification,
  activateDeptBilling,
  activateLabBilling,
  addDeptMember,
  addLabMember,
  addProjectMember,
  addToCollection,
  archiveProject,
  cancelProjectInvitation,
  attachLabToDept,
  cancelInvitation,
  createCollection,
  createDepartment,
  createDeptInvite,
  createDeptInvites,
  createLab,
  createLabInDept,
  createLabInvite,
  createLabInvites,
  createProject,
  createReminder,
  deleteLabLogo,
  deleteReminder,
  detachLabFromDept,
  disconnectDiscord,
  dismissSuggestion,
  ingestProjectLink,
  inviteToProject,
  issueActivationCode,
  issueDeptActivationCode,
  issueLabActivationCode,
  removeDeptMember,
  setDeptMemberRole,
  transferDeptOwnership,
  removeLabMember,
  regenerateDeptInvite,
  regenerateLabInvite,
  revokeDeptInvite,
  revokeLabInvite,
  setDiscordDailyReport,
  setLabMemberRole,
  transferLabOwnership,
  setLabPlanInclusion,
  testDiscordDm,
  inviteToLab,
  joinProject,
  leaveProject,
  removeProjectMember,
  respondProjectInvitation,
  removeFromCollection,
  respondToInvitation,
  ignoreItem,
  saveOpportunity,
  shareToProject,
  synthesizeLabProfile,
  unarchiveProject,
  unignoreItem,
  unsaveOpportunity,
  updateAdminLab,
  updateAdminUser,
  updateCollection,
  updateDeptProfile,
  updateLabProfile,
  leaveDepartment,
  leaveLab,
  updateLabWatch,
  updateProject,
  updateProjectCategories,
  updateProjectFocus,
  updateReminder,
  uploadLabLogo,
  createAnnouncementChannels,
  saveAnnouncementSettings,
  sendAnnouncementTest,
} from "@/lib/portal/mutations";
import {
  PERSONAL_SLUG,
  type AdminLabUpdate,
  type AdminUsersQuery,
  type AdminUserUpdate,
  type BriefingCategory,
  type BriefingKind,
  type InvitationAction,
  type OrgInviteInput,
  type OrgInviteBatchInput,
  type ProjectUpdateInput,
  type ReminderUpdateInput,
  type SearchSort,
} from "@/lib/portal/types";
import type { OrgKind } from "@/lib/auth-types";
import type {
  AnnouncementSettings,
  AnnouncementTarget,
  MyDepartment,
  MyLab,
} from "@/lib/portal/types";

export type SearchInput = {
  q: string;
  types: string[];
  /** Per-type facet selections keyed by facet field (year/sponsor/…). */
  facetFilters: Record<string, string[]>;
  sort: SearchSort;
};

/**
 * Query-first search, paginated by cursor. Disabled until the (trimmed) query is
 * non-empty, so an empty box makes no request. The query key includes every
 * filter so changing a facet or sort refetches from the first page; previous
 * pages accumulate for the "load more" control.
 */
export function useSearchResults(input: SearchInput) {
  const q = input.q.trim();
  const f = input.facetFilters;
  return useInfiniteQuery({
    queryKey: ["portal", "search", q, input.types, f, input.sort],
    queryFn: ({ pageParam }) =>
      fetchSearch({
        q,
        types: input.types,
        years: f.year,
        sponsors: f.sponsor,
        awardClasses: f.award_class,
        countries: f.country,
        sort: input.sort,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: q.length > 0,
    staleTime: 30_000,
  });
}

/** The signed-in user's labs (workspace switcher). */
export function useMyLabs() {
  return useQuery({
    queryKey: ["portal", "labs"],
    queryFn: fetchMyLabs,
    staleTime: 60_000,
  });
}

/**
 * Projects visible to the user, optionally scoped to one lab. Passing the
 * personal-workspace slug (or nothing) returns the full visible set.
 */
export function useProjects(labSlug?: string) {
  const scoped = labSlug && labSlug !== PERSONAL_SLUG ? labSlug : undefined;
  return useQuery({
    queryKey: ["portal", "projects", scoped ?? "all"],
    queryFn: () => fetchProjects(scoped),
    staleTime: 30_000,
  });
}

/**
 * One project, read by id. The project page uses this rather than picking its
 * row out of `useProjects` — that list is scoped to the active workspace, so a
 * lab project opened from the personal scope simply is not in it.
 */
export function useProject(id?: string) {
  return useQuery({
    queryKey: ["portal", "project", id ?? "none"],
    queryFn: () => fetchProject(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/**
 * One project's state. Kept in its own query rather than folded into the project
 * row: the project list is read constantly and this is read on one page, and the
 * state is the one payload in the product that should not travel further than the
 * surface asking for it.
 */
export function useProjectState(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-state", id ?? "none"],
    queryFn: () => fetchProjectState(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/**
 * Which lab conversation Mylo filed under a project. Editors only, so pass
 * `enabled = project.can_edit` — a reader who cannot edit would only get a 403.
 */
export function useProjectConversation(id?: string, enabled = true) {
  return useQuery({
    queryKey: ["portal", "project-conversation", id ?? "none"],
    queryFn: () => fetchProjectConversation(id as string),
    enabled: Boolean(id) && enabled,
    staleTime: 30_000,
  });
}

/** Mylo's pending proposals about the caller's project state. */
export function useReflections() {
  return useQuery({
    queryKey: ["portal", "reflections"],
    queryFn: fetchReflections,
    staleTime: 60_000,
  });
}

/** Members of a single lab. Disabled for the personal-workspace scope. */
export function useLabMembers(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "members", slug ?? "none"],
    queryFn: () => fetchLabMembers(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** The caller's own research profile. */
export function useProfile() {
  return useQuery({
    queryKey: ["portal", "profile"],
    queryFn: fetchProfile,
    staleTime: 60_000,
  });
}

/** What Mylo watches for the caller. */
export function useWatch() {
  return useQuery({
    queryKey: ["portal", "watch"],
    queryFn: fetchWatch,
    staleTime: 60_000,
  });
}

/** The caller's current daily research-suggestion digest. */
export function useDailyReport() {
  return useQuery({
    queryKey: ["portal", "daily-report"],
    queryFn: fetchDailyReport,
    staleTime: 60_000,
  });
}

/** The caller's current "Mylo Report" briefing (Daily page, three zones). */
export function useDailyBriefing() {
  return useQuery({
    queryKey: ["portal", "daily-briefing"],
    queryFn: fetchDailyBriefing,
    staleTime: 60_000,
  });
}

/** A lab's "Mylo Report" briefing (the lab overview). Disabled for personal scope. */
export function useLabDailyBriefing(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-daily-briefing", slug ?? "none"],
    queryFn: () => fetchLabDailyBriefing(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** A department's "Mylo Report" briefing (the department overview). */
export function useDepartmentDailyBriefing(id?: string) {
  return useQuery({
    queryKey: ["portal", "department-daily-briefing", id ?? "none"],
    queryFn: () => fetchDepartmentDailyBriefing(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/** The caller's retained report history — the Reports page's date list. */
export function useBriefings(kind: BriefingKind = "daily") {
  return useQuery({
    queryKey: ["portal", "briefings", kind],
    queryFn: () => fetchBriefings(kind),
    staleTime: 60_000,
  });
}

/** One archived day of the caller's history. Idle until a date is picked. */
export function useBriefing(date?: string, kind: BriefingKind = "daily") {
  return useQuery({
    queryKey: ["portal", "briefing", kind, date ?? "none"],
    queryFn: () => fetchBriefingByDate(date as string, kind),
    enabled: Boolean(date),
    // An archived day never changes once written, so there is nothing to refetch.
    staleTime: Infinity,
  });
}

/** A lab's retained report history. Disabled for personal scope. */
export function useLabBriefings(slug?: string, kind: BriefingKind = "daily") {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-briefings", slug ?? "none", kind],
    queryFn: () => fetchLabBriefings(slug as string, kind),
    enabled,
    staleTime: 60_000,
  });
}

/** One archived day of a lab's history. Idle until a lab and a date are picked. */
export function useLabBriefing(
  slug?: string,
  date?: string,
  kind: BriefingKind = "daily",
) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG && date);
  return useQuery({
    queryKey: ["portal", "lab-briefing", slug ?? "none", kind, date ?? "none"],
    queryFn: () => fetchLabBriefingByDate(slug as string, date as string, kind),
    enabled,
    staleTime: Infinity,
  });
}

/** Upload / replace a lab's logo; refreshes the switcher list and the lab profile. */
export function useUploadLabLogo(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadLabLogo(slug, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-profile", slug] });
    },
  });
}

/** Clear a lab's logo; refreshes the switcher list and the lab profile. */
export function useDeleteLabLogo(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteLabLogo(slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-profile", slug] });
    },
  });
}

/** The user's ranked funding opportunities (Opportunities page). */
export function useGrants() {
  return useQuery({
    queryKey: ["portal", "grants"],
    queryFn: fetchGrants,
    staleTime: 60_000,
  });
}

/** The user's ranked conferences (Conferences page). */
export function useConferences() {
  return useQuery({
    queryKey: ["portal", "conferences"],
    queryFn: fetchConferences,
    staleTime: 60_000,
  });
}

/**
 * Static hover copy for conference rank badges and trust tiers (Phase 10).
 * `staleTime: Infinity` because the reference table only changes when the
 * collector's own rank/tier vocabulary changes — never per request, and
 * never per user — so one fetch serves every badge on every card for the
 * whole session (react-query dedupes every card's subscription to it).
 */
export function useRankingReference() {
  return useQuery({
    queryKey: ["portal", "ranking-reference"],
    queryFn: fetchRankingReference,
    staleTime: Infinity,
  });
}

/** The user's matched fellowships (Fellowships page). */
export function useFellowships() {
  return useQuery({
    queryKey: ["portal", "fellowships"],
    queryFn: fetchFellowships,
    staleTime: 60_000,
  });
}

/** The user's saved deadlines (Deadlines page + Overview). */
export function useDeadlines() {
  return useQuery({
    queryKey: ["portal", "deadlines"],
    queryFn: fetchDeadlines,
    staleTime: 30_000,
  });
}

/** The signed-in user's own "what Mylo found" recency matrix (personal Overview). */
export function useWindowCounts() {
  return useQuery({
    queryKey: ["portal", "window-counts"],
    queryFn: fetchWindowCounts,
    staleTime: 60_000,
  });
}

/** Every bookmark with feed-parity card payloads (Saves page). */
export function useSaves() {
  return useQuery({
    queryKey: ["portal", "saves"],
    queryFn: fetchSaves,
    staleTime: 30_000,
  });
}

/** The header bell: reminder / moved-deadline / high-signal notifications. */
export function useNotifications() {
  return useQuery({
    queryKey: ["portal", "notifications"],
    queryFn: fetchNotifications,
    staleTime: 60_000,
  });
}

/** Mark a bell notification read or dismissed; refreshes the bell. */
export function useNotificationAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "read" | "dismiss" }) =>
      actOnNotification(id, action),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "notifications"] }),
  });
}

/** The caller's deadline reminders (personal + accessible lab reminders). */
export function useReminders() {
  return useQuery({
    queryKey: ["portal", "reminders"],
    queryFn: fetchReminders,
    staleTime: 30_000,
  });
}

/**
 * Whether reminders are available to the caller — personally, or for `labSlug`.
 *
 * One account-level query shared by every bell on the page (react-query dedupes by
 * key), so gating a hundred feed cards costs a single request. The answer comes
 * from the server rather than being re-derived from entitlements + Discord status
 * on the client, so the button and the endpoint can never disagree.
 */
export function useReminderAccess(labSlug?: string) {
  return useQuery({
    queryKey: ["portal", "reminder-access", labSlug ?? "personal"],
    queryFn: () => fetchReminderAccess(labSlug),
    staleTime: 60_000,
  });
}

/** A lab's postable Discord channels for the reminder channel picker. Only
 * fetched when a slug is given (lab scope + a lab the caller manages). */
export function useLabReminderChannels(slug?: string) {
  return useQuery({
    queryKey: ["portal", "lab-reminder-channels", slug],
    queryFn: () => fetchLabReminderChannels(slug!),
    enabled: Boolean(slug),
    staleTime: 60_000,
  });
}

/** Who a lab alert may tag. Only fetched in lab scope, for a managed lab. */
export function useLabMentionTargets(slug?: string) {
  return useQuery({
    queryKey: ["portal", "lab-mention-targets", slug],
    queryFn: () => fetchLabMentionTargets(slug!),
    enabled: Boolean(slug),
    staleTime: 60_000,
  });
}

/** Create, edit and stop reminders; all refresh the reminders list and the bell. */
export function useReminderMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal", "reminders"] });
    queryClient.invalidateQueries({ queryKey: ["portal", "notifications"] });
  };
  const create = useMutation({ mutationFn: createReminder, onSuccess: invalidate });
  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: ReminderUpdateInput }) =>
      updateReminder(id, input),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: ({ id, purge }: { id: string; purge?: boolean }) =>
      deleteReminder(id, { purge }),
    onSuccess: invalidate,
  });
  return { create, update, remove };
}

/** Save or unsave a bookmarkable item; refreshes the feeds, saves, and bell. */
export function useSaveOpportunity() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    for (const key of [
      "grants",
      "conferences",
      "fellowships",
      "daily-report",
      "deadlines",
      "saves",
      "lab-saves",
      "search",
      "lab-recommendations",
      "notifications",
    ]) {
      queryClient.invalidateQueries({ queryKey: ["portal", key] });
    }
  };
  const save = useMutation({
    mutationFn: ({
      contentId,
      note,
      labSlug,
    }: {
      contentId: string;
      note?: string;
      labSlug?: string;
    }) => saveOpportunity(contentId, note, labSlug),
    onSuccess: invalidate,
  });
  const unsave = useMutation({
    mutationFn: ({
      contentId,
      labSlug,
    }: {
      contentId: string;
      labSlug?: string;
    }) => unsaveOpportunity(contentId, labSlug),
    onSuccess: invalidate,
  });
  return { save, unsave };
}

/** The queries an item's presence or absence can change. */
const IGNORE_AFFECTED = [
  "grants",
  "conferences",
  "fellowships",
  "daily-report",
  "deadlines",
  "saves",
  "lab-saves",
  "search",
  "lab-recommendations",
  "window-counts",
] as const;

/**
 * Ignore or restore an item.
 *
 * The two directions invalidate **different** sets, on purpose.
 *
 * Ignoring refreshes only the Ignored view and search (which still lists ignored
 * hits and needs the flag). It deliberately leaves the feeds alone: refetching
 * them drops the row from the list, which unmounts the card *and the undo strip
 * that replaced it* — the reader's way back would vanish in the same instant it
 * appeared. The feed is momentarily stale by one row the card has already
 * collapsed in place, and it corrects itself on the next natural fetch.
 *
 * Restoring has no such strip to protect and must put the item back everywhere,
 * so it invalidates the lot.
 */
export function useIgnoreItem() {
  const queryClient = useQueryClient();
  const invalidate = (keys: readonly string[]) => {
    for (const key of keys) {
      queryClient.invalidateQueries({ queryKey: ["portal", key] });
    }
  };
  const ignore = useMutation({
    mutationFn: ({ contentId }: { contentId: string }) => ignoreItem(contentId),
    onSuccess: () => invalidate(["ignored", "search"]),
  });
  const restore = useMutation({
    mutationFn: ({ contentId }: { contentId: string }) =>
      unignoreItem(contentId),
    onSuccess: () => invalidate(["ignored", ...IGNORE_AFFECTED]),
  });
  return { ignore, restore };
}

/** Everything this reader has ignored, with feed-parity cards (Ignored view). */
export function useIgnored() {
  return useQuery({
    queryKey: ["portal", "ignored"],
    queryFn: fetchIgnored,
    staleTime: 30_000,
  });
}

/** A lab's shared saves (lab Saves area). Disabled for the personal scope. */
export function useLabSaves(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-saves", slug ?? "none"],
    queryFn: () => fetchLabSaves(slug as string),
    enabled,
    staleTime: 30_000,
  });
}

/** The caller's pending lab invitations (notifications panel). */
export function useMyInvitations() {
  return useQuery({
    queryKey: ["portal", "invitations"],
    queryFn: fetchMyInvitations,
    staleTime: 30_000,
  });
}

/** A single lab's collective purpose & goals. Disabled for the personal scope. */
export function useLabProfile(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-profile", slug ?? "none"],
    queryFn: () => fetchLabProfile(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** Create a lab, then refresh the switcher's lab list. */
export function useCreateLab() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createLab(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
    },
  });
}

/** Invite someone to a lab. */
export function useInviteToLab(slug: string) {
  return useMutation({
    mutationFn: (input: { identifier: string; role?: string }) =>
      inviteToLab(slug, input.identifier, input.role),
  });
}

/** Answer an invitation, then refresh the feed and the caller's labs. */
export function useRespondInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; action: InvitationAction }) =>
      respondToInvitation(input.id, input.action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "invitations"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
    },
  });
}

/** Create a project, then refresh the visible project lists. */
export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof createProject>[0]) =>
      createProject(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
    },
  });
}

/** Archive a project (owner or lab manager only); refreshes the project lists
 * so it moves into the Archived section and frees a cap slot. */
export function useArchiveProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
    },
  });
}

/** Restore an archived project; may reject with `ProjectCapReachedError` if
 * the owning scope is at its plan's limit. Refreshes the project lists. */
export function useUnarchiveProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unarchiveProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
    },
  });
}

/**
 * Save a project's fundamentals (name, description, status, progress, watch
 * categories, focus). Refreshes the project itself and both lists; when the
 * patch changed what Mylo searches on, its recommendations are re-read too —
 * the backend re-seeds them in the background on exactly those keys.
 */
export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; patch: ProjectUpdateInput }) =>
      updateProject(input.id, input.patch),
    onSuccess: (project, variables) => {
      queryClient.setQueryData(["portal", "project", variables.id], project);
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
      if ("focus" in variables.patch || "watch_categories" in variables.patch) {
        queryClient.invalidateQueries({
          queryKey: ["portal", "project-recommendations", variables.id],
        });
        queryClient.invalidateQueries({
          queryKey: ["portal", "project-digest", variables.id],
        });
      }
    },
  });
}

/** A project's pending invitations (its editors only). */
export function useProjectInvitations(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-invitations", id ?? "none"],
    queryFn: () => fetchProjectInvitations(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** The caller's own pending project invitations (notifications feed). */
export function useMyProjectInvitations() {
  return useQuery({
    queryKey: ["portal", "my-project-invitations"],
    queryFn: fetchMyProjectInvitations,
    staleTime: 60_000,
  });
}

/** Invite someone to a project, then refresh its invitation list. */
export function useInviteToProject(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { identifier: string; message?: string }) =>
      inviteToProject(id, input.identifier, input.message),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-invitations", id],
      });
    },
  });
}

/** Withdraw a pending invitation, then refresh the list. */
export function useCancelProjectInvitation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      cancelProjectInvitation(id, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-invitations", id],
      });
    },
  });
}

/** Answer a project invitation; refreshes the feed and the project lists (an
 * accept adds a project the caller can now see). */
export function useRespondProjectInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; action: InvitationAction }) =>
      respondProjectInvitation(input.id, input.action),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "my-project-invitations"],
      });
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
    },
  });
}

/** One project's matched papers/grants/fellowships/conferences, capped to
 * Mylo's digest slice ("Mylo's picks for this project"). */
export function useProjectDigest(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-digest", id ?? "none"],
    queryFn: () => fetchProjectDigest(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/** Update which categories Mylo tracks for a project; refreshes its
 * recommendations (both the full list and the digest) and the project lists. */
export function useUpdateProjectCategories() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, categories }: { id: string; categories: BriefingCategory[] }) =>
      updateProjectCategories(id, categories),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-recommendations", variables.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-digest", variables.id],
      });
    },
  });
}

/** Update a project's research focus; refreshes its recommendations once
 * Mylo's background re-seed lands. */
export function useUpdateProjectFocus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; focus: Parameters<typeof updateProjectFocus>[1] }) =>
      updateProjectFocus(input.id, input.focus),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-recommendations", variables.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-digest", variables.id],
      });
    },
  });
}

/** Every project of a lab (any lab member may browse them to join). */
export function useLabProjects(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-projects", slug ?? "none"],
    queryFn: () => fetchLabProjects(slug as string),
    enabled,
    staleTime: 30_000,
  });
}

/** Join / leave / add / remove members on a project, refreshing the project
 * itself (its roster is serialized on the row) and both project lists. */
export function useProjectMembership() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal", "project"] });
    queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
    queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
  };
  const join = useMutation({
    mutationFn: (id: string) => joinProject(id),
    onSuccess: invalidate,
  });
  const leave = useMutation({
    mutationFn: (id: string) => leaveProject(id),
    onSuccess: invalidate,
  });
  const addMember = useMutation({
    mutationFn: (input: { id: string; username: string }) =>
      addProjectMember(input.id, input.username),
    onSuccess: invalidate,
  });
  const removeMember = useMutation({
    mutationFn: (input: { id: string; username: string }) =>
      removeProjectMember(input.id, input.username),
    onSuccess: invalidate,
  });
  return { join, leave, addMember, removeMember };
}

/** Save a lab's purpose & goals, updating the cached copy in place. */
export function useUpdateLabProfile(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      payload: Parameters<typeof updateLabProfile>[1],
    ) => updateLabProfile(slug, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["portal", "lab-profile", slug], data);
    },
  });
}

/** A department's profile (its General page in Settings). */
export function useDeptProfile(id?: string) {
  return useQuery({
    queryKey: ["portal", "dept-profile", id ?? "none"],
    queryFn: () => fetchDeptProfile(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/** Save a department's profile, updating the cached copy in place. */
export function useUpdateDeptProfile(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof updateDeptProfile>[1]) =>
      updateDeptProfile(id, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["portal", "dept-profile", id], data);
    },
  });
}

/**
 * Leave a lab or a department yourself. On success the org drops out of the
 * caller's lists, so both are refreshed.
 */
export function useLeaveOrg() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (org: { kind: "lab"; slug: string } | { kind: "department"; id: string }) =>
      org.kind === "lab" ? leaveLab(org.slug) : leaveDepartment(org.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "departments"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
}

/** A lab's matched papers/grants/conferences. Disabled for the personal scope. */
export function useLabRecommendations(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-recommendations", slug ?? "none"],
    queryFn: () => fetchLabRecommendations(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** A department's matched papers, grants, fellowships and conferences. */
export function useDepartmentRecommendations(id?: string) {
  return useQuery({
    queryKey: ["portal", "department-recommendations", id ?? "none"],
    queryFn: () => fetchDepartmentRecommendations(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/**
 * The feed of whichever org the reader is working in: a lab's, or a
 * department's (a department works like a lab, through the lab's feed).
 * `org` is null in the personal scope, and both queries then stay idle.
 */
export function useOrgRecommendations(org: OrgRef | null) {
  const lab = useLabRecommendations(org?.kind === "lab" ? org.key : undefined);
  const dept = useDepartmentRecommendations(
    org?.kind === "department" ? org.key : undefined,
  );
  return org?.kind === "department" ? dept : lab;
}

/** A lab (by slug) or a department (by id), with the name its feed shows. */
export type OrgRef = { kind: "lab" | "department"; key: string; name: string };

/** The org a workspace's feeds read, or null in the personal scope. */
export function orgRefFor(
  lab: Pick<MyLab, "slug" | "name"> | null,
  department: Pick<MyDepartment, "id" | "name"> | null,
): OrgRef | null {
  if (lab) return { kind: "lab", key: lab.slug, name: lab.name };
  if (department) return { kind: "department", key: department.id, name: department.name };
  return null;
}

/** One project's matched papers/grants/conferences (its declared focus). */
export function useProjectRecommendations(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-recommendations", id ?? "none"],
    queryFn: () => fetchProjectRecommendations(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/** A project's team-shared feed (papers members pasted in or pushed from Mylo's picks). */
export function useProjectFeed(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-feed", id ?? "none"],
    queryFn: () => fetchProjectFeed(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** Share a content item into a project's team feed; refreshes the feed and recommendations. */
export function useShareToProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; contentId: string; note?: string }) =>
      shareToProject(input.id, input.contentId, input.note),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-feed", variables.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-recommendations", variables.id],
      });
    },
  });
}

/** Resolve a pasted DOI/article link into a project share; refreshes the feed. */
export function useIngestProjectLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; rawInput: string; note?: string }) =>
      ingestProjectLink(input.id, input.rawInput, input.note),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-feed", variables.id],
      });
    },
  });
}

/** A project's shared reading lists (non-archived by default). */
export function useProjectCollections(id?: string) {
  return useQuery({
    queryKey: ["portal", "project-collections", id ?? "none"],
    queryFn: () => fetchProjectCollections(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** One collection's full item list. Disabled until both ids are known. */
export function useProjectCollection(id?: string, collectionId?: string) {
  return useQuery({
    queryKey: [
      "portal",
      "project-collection",
      id ?? "none",
      collectionId ?? "none",
    ],
    queryFn: () => fetchProjectCollection(id as string, collectionId as string),
    enabled: Boolean(id && collectionId),
    staleTime: 30_000,
  });
}

/** Create a collection; refreshes the project's collection list. */
export function useCreateCollection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; description?: string }) =>
      createCollection(id, input.name, input.description),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collections", id],
      });
    },
  });
}

/** Rename, re-describe, or archive/unarchive a collection. */
export function useUpdateCollection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      collectionId: string;
      patch: Parameters<typeof updateCollection>[2];
    }) => updateCollection(id, input.collectionId, input.patch),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collections", id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collection", id, variables.collectionId],
      });
    },
  });
}

/** Add a content item to a collection; refreshes the list and that collection's detail. */
export function useAddToCollection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      collectionId: string;
      contentId: string;
      note?: string;
    }) => addToCollection(id, input.collectionId, input.contentId, input.note),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collections", id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collection", id, variables.collectionId],
      });
    },
  });
}

/** Remove a content item from a collection; refreshes the list and that collection's detail. */
export function useRemoveFromCollection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { collectionId: string; contentId: string }) =>
      removeFromCollection(id, input.collectionId, input.contentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collections", id],
      });
      queryClient.invalidateQueries({
        queryKey: ["portal", "project-collection", id, variables.collectionId],
      });
    },
  });
}

/** Papers teammates shared that closely match the caller's own profile. */
export function useMemberSuggestions() {
  return useQuery({
    queryKey: ["portal", "member-suggestions"],
    queryFn: fetchMemberSuggestions,
    staleTime: 30_000,
  });
}

/** Dismiss a member suggestion; refreshes the suggestions feed and the notification bell. */
export function useDismissSuggestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dismissSuggestion(id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["portal", "member-suggestions"],
      });
      queryClient.invalidateQueries({ queryKey: ["portal", "notifications"] });
    },
  });
}

/** What Mylo watches for a lab. Disabled for the personal-workspace scope. */
export function useLabWatch(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-watch", slug ?? "none"],
    queryFn: () => fetchLabWatch(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** Save a lab's watch settings, updating the cached copy in place. */
export function useUpdateLabWatch(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof updateLabWatch>[1]) =>
      updateLabWatch(slug, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["portal", "lab-watch", slug], data);
    },
  });
}

/** Draft a lab profile from the PI's free text (LLM-assisted, nothing saved). */
export function useSynthesizeLabProfile(slug: string) {
  return useMutation({
    mutationFn: (input: Parameters<typeof synthesizeLabProfile>[1]) =>
      synthesizeLabProfile(slug, input),
  });
}

/** The caller's Discord link status (profile "Connected services" card).
 *
 * ``watch`` turns on short polling, for the one window where the answer changes
 * without this app doing anything: the reader has a live activation code and is
 * off in Discord typing /activate. Nothing pushes that back here — the link is
 * written by the Mylo gateway — so without polling the card keeps saying "not
 * linked" until the reader navigates away and back. Polling stops the moment it
 * succeeds, and react-query pauses it while the tab is hidden, which is most of
 * the time it is on.
 */
export function useDiscordStatus(watch = false) {
  return useQuery({
    queryKey: ["portal", "discord"],
    queryFn: fetchDiscordStatus,
    staleTime: watch ? 0 : 30_000,
    // Stops itself on success rather than waiting for the caller to notice and
    // flip ``watch`` — a linked account cannot go back to unlinked on its own, so
    // there is nothing left to watch for.
    refetchInterval: watch
      ? (query) => (query.state.data?.connected ? false : 3_000)
      : false,
  });
}

/** The signed-in user's resolved entitlements — drives read-time lock states. */
export function useEntitlements() {
  return useQuery({
    queryKey: ["portal", "entitlements"],
    queryFn: fetchEntitlements,
    staleTime: 60_000,
  });
}

// -- Lab & department billing / member management -----------------------------

/** A lab's seat-priced plan state. */
export function useLabBilling(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-billing", slug ?? "none"],
    queryFn: () => fetchLabBilling(slug as string),
    enabled,
    staleTime: 30_000,
  });
}

/** Activate a lab's plan, then refresh billing, members, and entitlements. */
export function useActivateLabBilling(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateLabBilling(slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-billing", slug] });
      queryClient.invalidateQueries({ queryKey: ["portal", "members", slug] });
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
}

/** Add / remove / re-role a lab member, or cancel an invite; refresh the roster. */
export function useLabMemberMutations(slug: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal", "members", slug] });
    queryClient.invalidateQueries({ queryKey: ["portal", "lab-billing", slug] });
  };
  const add = useMutation({
    mutationFn: (input: { username: string; role?: string }) =>
      addLabMember(slug, input.username, input.role),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (username: string) => removeLabMember(slug, username),
    onSuccess: invalidate,
  });
  const setRole = useMutation({
    mutationFn: (input: { username: string; role: string }) =>
      setLabMemberRole(slug, input.username, input.role),
    onSuccess: invalidate,
  });
  const cancelInvite = useMutation({
    mutationFn: (id: string) => cancelInvitation(slug, id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "invitations"] }),
  });
  // Handing the lab over also moves the caller's own role, so the switcher's
  // copy of this lab is stale the moment it succeeds.
  const transfer = useMutation({
    mutationFn: (username: string) => transferLabOwnership(slug, username),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["portal", "labs"] });
    },
  });
  return { add, remove, setRole, cancelInvite, transfer };
}

/** A department's plan state. */
export function useDeptBilling(id?: string) {
  return useQuery({
    queryKey: ["portal", "dept-billing", id ?? "none"],
    queryFn: () => fetchDeptBilling(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** A department's effective-membership roster. */
export function useDeptMembers(id?: string) {
  return useQuery({
    queryKey: ["portal", "dept-members", id ?? "none"],
    queryFn: () => fetchDeptMembers(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** The labs under a department. */
export function useDeptLabs(id?: string) {
  return useQuery({
    queryKey: ["portal", "dept-labs", id ?? "none"],
    queryFn: () => fetchDeptLabs(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** Activate a department's plan, then refresh its billing, members, entitlements. */
export function useActivateDeptBilling(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateDeptBilling(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "dept-billing", id] });
      queryClient.invalidateQueries({ queryKey: ["portal", "dept-members", id] });
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
}

/** Add / remove department members and attach / create / detach labs. */
export function useDeptManagement(id: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal", "dept-members", id] });
    queryClient.invalidateQueries({ queryKey: ["portal", "dept-labs", id] });
    queryClient.invalidateQueries({ queryKey: ["portal", "dept-billing", id] });
  };
  const addMember = useMutation({
    mutationFn: (input: { username: string; role?: string }) =>
      addDeptMember(id, input.username, input.role),
    onSuccess: invalidate,
  });
  const removeMember = useMutation({
    mutationFn: (username: string) => removeDeptMember(id, username),
    onSuccess: invalidate,
  });
  const setMemberRole = useMutation({
    mutationFn: (input: { username: string; role: string }) =>
      setDeptMemberRole(id, input.username, input.role),
    onSuccess: invalidate,
  });
  // Handing the department over changes the caller's own role, so the
  // department list's copy is stale the moment it succeeds.
  const transfer = useMutation({
    mutationFn: (username: string) => transferDeptOwnership(id, username),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["portal", "departments"] });
    },
  });
  const attachLab = useMutation({
    mutationFn: (slug: string) => attachLabToDept(id, slug),
    onSuccess: invalidate,
  });
  const createLab = useMutation({
    mutationFn: (name: string) => createLabInDept(id, name),
    onSuccess: invalidate,
  });
  const detachLab = useMutation({
    mutationFn: (slug: string) => detachLabFromDept(id, slug),
    onSuccess: invalidate,
  });
  const setLabInclusion = useMutation({
    mutationFn: (input: { slug: string; included: boolean }) =>
      setLabPlanInclusion(id, input.slug, input.included),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
  return {
    addMember,
    removeMember,
    setMemberRole,
    transfer,
    attachLab,
    createLab,
    detachLab,
    setLabInclusion,
  };
}

/** A lab's Discord sync status (Manage & Invite page; managers only). */
export function useLabDiscordStatus(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-discord", slug ?? "none"],
    queryFn: () => fetchLabDiscordStatus(slug as string),
    enabled,
    staleTime: 30_000,
  });
}

/** A lab's Discord health — drives the manager-only reachability panel.
 *
 * Manager-gated server-side (403 for anyone else), so this is only ever mounted
 * inside the lab settings surface. */
export function useLabDiscordHealth(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-discord-health", slug ?? "none"],
    queryFn: () => fetchLabDiscordHealth(slug as string),
    enabled,
    staleTime: 30_000,
  });
}

/** A department's own Discord server status (department settings; managers only). */
export function useDeptDiscordStatus(id?: string) {
  return useQuery({
    queryKey: ["portal", "dept-discord", id ?? "none"],
    queryFn: () => fetchDeptDiscordStatus(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

/** Start the guild install for a department: fetch the authorize URL, then redirect. */
export function useConnectDeptDiscord() {
  return useMutation({
    mutationFn: async (id: string) => {
      const { authorize_url } = await fetchDeptDiscordStart(id);
      window.location.href = authorize_url;
    },
  });
}

export function useIssueDeptActivationCode() {
  return useMutation({ mutationFn: (id: string) => issueDeptActivationCode(id) });
}

/** Start the Discord OAuth link: fetch the authorize URL, then redirect. */
export function useConnectDiscord() {
  return useMutation({
    mutationFn: async () => {
      const { authorize_url } = await fetchDiscordStart();
      window.location.href = authorize_url;
    },
  });
}

/** Start the guild install for a lab: fetch the authorize URL, then redirect. */
export function useConnectLabDiscord() {
  return useMutation({
    mutationFn: async (slug: string) => {
      const { authorize_url } = await fetchLabDiscordStart(slug);
      window.location.href = authorize_url;
    },
  });
}

/** Re-run the DM reachability probe; write the fresh status into the card. */
export function useTestDiscordDm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => testDiscordDm(),
    onSuccess: (status) => {
      queryClient.setQueryData(["portal", "discord"], status);
    },
  });
}

/** Toggle the daily "Mylo Report" DM; write the fresh status into the card. */
export function useSetDiscordDailyReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (optOut: boolean) => setDiscordDailyReport(optOut),
    onSuccess: (status) => {
      queryClient.setQueryData(["portal", "discord"], status);
    },
  });
}

/** Disconnect Discord, then refresh the status card. */
export function useDisconnectDiscord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => disconnectDiscord(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "discord"] });
    },
  });
}

/** Issue a one-time Path B activation code. */
export function useIssueActivationCode() {
  return useMutation({ mutationFn: () => issueActivationCode() });
}

/** Issue a one-time 10-digit lab activation code (Path C) for `/activate-lab`. */
export function useIssueLabActivationCode() {
  return useMutation({ mutationFn: (slug: string) => issueLabActivationCode(slug) });
}

/**
 * The admin roster — paginated + searchable. `keepPreviousData` holds the current
 * page visible while the next one loads, so paging/searching doesn't flash empty.
 * Staff/superuser only (the API 403s otherwise); the section also hides for
 * non-admins, so this never fires for them.
 */
export function useAdminUsers(query: AdminUsersQuery) {
  return useQuery({
    queryKey: [
      "portal",
      "admin-users",
      query.q ?? "",
      query.page ?? 1,
      query.pageSize ?? 0,
    ],
    queryFn: () => fetchAdminUsers(query),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

/** One user's full admin detail (drives the editor). */
export function useAdminUser(id?: number) {
  return useQuery({
    queryKey: ["portal", "admin-user", id ?? 0],
    queryFn: () => fetchAdminUser(id as number),
    enabled: Boolean(id),
    staleTime: 15_000,
  });
}

/** Apply an admin update; refresh that user's detail + the roster. */
export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: number; patch: AdminUserUpdate }) =>
      updateAdminUser(input.id, input.patch),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["portal", "admin-user", variables.id], data);
      queryClient.invalidateQueries({ queryKey: ["portal", "admin-users"] });
    },
  });
}

/** The admin lab roster — same paging/search contract as {@link useAdminUsers}. */
export function useAdminLabs(query: AdminUsersQuery) {
  return useQuery({
    queryKey: [
      "portal",
      "admin-labs",
      query.q ?? "",
      query.page ?? 1,
      query.pageSize ?? 0,
    ],
    queryFn: () => fetchAdminLabs(query),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

/** One lab's full admin detail (drives the plan editor). */
export function useAdminLab(slug?: string) {
  return useQuery({
    queryKey: ["portal", "admin-lab", slug ?? ""],
    queryFn: () => fetchAdminLab(slug as string),
    enabled: Boolean(slug),
    staleTime: 15_000,
  });
}

/**
 * Apply an admin plan update to a lab; refresh that lab's detail + the roster, plus
 * the lab-billing read the lab's own plan card and Discord gate render from — an
 * admin granting Mylo should unlock the lab's setup flow without a reload.
 */
export function useUpdateAdminLab() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { slug: string; patch: AdminLabUpdate }) =>
      updateAdminLab(input.slug, input.patch),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["portal", "admin-lab", variables.slug], data);
      queryClient.invalidateQueries({ queryKey: ["portal", "admin-labs"] });
      queryClient.invalidateQueries({
        queryKey: ["portal", "lab-billing", variables.slug],
      });
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
}

/** The caller's departments, for the workspace-structure page. */
export function useMyDepartments() {
  return useQuery({
    queryKey: ["portal", "departments"],
    queryFn: fetchMyDepartments,
    staleTime: 60_000,
  });
}

/** Create a department, then refresh the list it appears in. */
export function useCreateDepartment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string }) => createDepartment(input.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "departments"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "entitlements"] });
    },
  });
}

/**
 * One org's join invitations: the list, plus creating and withdrawing them.
 *
 * A lab and a department differ only in which endpoints they talk to, so the
 * shared invite card takes this shape and never has to know which it is looking
 * at. Pass `kind` and the lab slug or department id.
 */
export function useOrgInvites(kind: OrgKind, id: string) {
  const queryClient = useQueryClient();
  const key = ["portal", "org-invites", kind, id];
  const list = useQuery({
    queryKey: key,
    queryFn: () =>
      kind === "lab" ? fetchLabInvites(id) : fetchDeptInvites(id),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: (input: OrgInviteInput) =>
      kind === "lab" ? createLabInvite(id, input) : createDeptInvite(id, input),
    onSuccess: invalidate,
  });
  const createMany = useMutation({
    mutationFn: (input: OrgInviteBatchInput) =>
      kind === "lab" ? createLabInvites(id, input) : createDeptInvites(id, input),
    onSuccess: invalidate,
  });
  const revoke = useMutation({
    mutationFn: (inviteId: string) =>
      kind === "lab"
        ? revokeLabInvite(id, inviteId)
        : revokeDeptInvite(id, inviteId),
    onSuccess: invalidate,
  });
  const regenerate = useMutation({
    mutationFn: (inviteId: string) =>
      kind === "lab"
        ? regenerateLabInvite(id, inviteId)
        : regenerateDeptInvite(id, inviteId),
    onSuccess: invalidate,
  });
  return { list, create, createMany, revoke, regenerate };
}


/** A lab's or department's announcements; disabled without a target. */
export function useAnnouncements(target: AnnouncementTarget | null) {
  const key = target ? ("lab" in target ? `lab:${target.lab}` : `dept:${target.department}`) : "none";
  return useQuery({
    queryKey: ["portal", "announcements", key],
    queryFn: () => fetchAnnouncements(target as AnnouncementTarget),
    enabled: Boolean(target),
    staleTime: 60_000,
  });
}


/** A department's Opportunities page; disabled without a department. */
export function useDeptOpportunities(departmentId: string | null) {
  return useQuery({
    queryKey: ["portal", "dept-opportunities", departmentId ?? "none"],
    queryFn: () => fetchDeptOpportunities(departmentId as string),
    enabled: Boolean(departmentId),
    staleTime: 60_000,
  });
}

/** Save announcement settings, then refresh the announcements read. */
export function useSaveAnnouncementSettings(target: AnnouncementTarget) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<AnnouncementSettings>) =>
      saveAnnouncementSettings(target, patch),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "announcements"] }),
  });
}

export function useSendAnnouncementTest(target: AnnouncementTarget) {
  return useMutation({ mutationFn: () => sendAnnouncementTest(target) });
}

export function useCreateAnnouncementChannels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bindingId: number) => createAnnouncementChannels(bindingId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal", "announcements"] }),
  });
}

// -- Mylo chat (api/tools/agent/) ---------------------------------------------

/** Where Mylo's model runs (S-3), or why there is none. */
export function useAgentStatus(enabled = true) {
  return useQuery({
    queryKey: ["agent", "status"],
    queryFn: fetchAgentStatus,
    staleTime: 5 * 60_000,
    enabled,
  });
}

/**
 * The gate's answer for this person, as a value rather than a thrown error:
 * a refusal is an answer the panel shows, not a failure to retry.
 */
export function useAgentCatalog() {
  return useQuery<CatalogOutcome>({
    queryKey: ["agent", "catalog"],
    queryFn: async () => {
      try {
        return { ok: true, functions: await fetchAgentCatalog() };
      } catch (error) {
        if (error instanceof AgentError) {
          return { ok: false, status: error.status, refusal: error.refusal };
        }
        throw error;
      }
    },
    staleTime: 5 * 60_000,
  });
}

/** May this person chat with Mylo? Read from the gate, never decided here. */
export function useChatAvailability(): ChatAvailability {
  const catalog = useAgentCatalog();
  const allowedSoFar = catalog.data?.ok === true;
  const status = useAgentStatus(allowedSoFar);
  return availabilityFrom(catalog.data, status.data);
}

export function useAgentThreads(query: ThreadQuery = {}, enabled = true) {
  return useQuery({
    queryKey: ["agent", "threads", query.q ?? "", Boolean(query.archived), query.anchor ?? null],
    queryFn: () => fetchThreads(query),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useAgentThread(id: string | null) {
  return useQuery({
    queryKey: ["agent", "thread", id],
    queryFn: () => fetchThread(id as string),
    enabled: Boolean(id),
  });
}

export function useUpdateAgentThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...changes
    }: {
      id: string;
      title?: string;
      archived?: boolean;
      pinned?: boolean;
    }) => updateThread(id, changes),
    onSuccess: (thread) => {
      queryClient.setQueryData(["agent", "thread", thread.id], thread);
      void queryClient.invalidateQueries({ queryKey: ["agent", "threads"] });
    },
  });
}

export function useDeleteAgentThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteThread(id),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: ["agent", "thread", id] });
      void queryClient.invalidateQueries({ queryKey: ["agent", "threads"] });
    },
  });
}

export function useAgentPreferences() {
  return useQuery({
    queryKey: ["agent", "preferences"],
    queryFn: fetchAgentPreferences,
  });
}

export function useSaveAgentPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: Partial<AgentPreferences>) => saveAgentPreferences(changes),
    onSuccess: (prefs) => {
      queryClient.setQueryData(["agent", "preferences"], prefs);
      // turning chat on or off changes the gate's answer
      void queryClient.invalidateQueries({ queryKey: ["agent", "catalog"] });
    },
  });
}

export function useAgentPolicy(kind: "lab" | "department", ref?: string | null) {
  return useQuery({
    queryKey: ["agent", "policy", kind, ref],
    queryFn: () => fetchAgentPolicy(kind, ref as string),
    enabled: Boolean(ref),
  });
}

export function useSaveAgentPolicy(kind: "lab" | "department", ref: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: Partial<AgentPolicy>) => saveAgentPolicy(kind, ref, changes),
    onSuccess: (policy) => {
      queryClient.setQueryData(["agent", "policy", kind, ref], policy);
    },
  });
}
