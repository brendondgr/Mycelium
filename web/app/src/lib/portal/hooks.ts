"use client";

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  fetchAdminLab,
  fetchAdminLabs,
  fetchAdminUser,
  fetchAdminUsers,
  fetchConferences,
  fetchBriefingByDate,
  fetchBriefings,
  fetchDailyBriefing,
  fetchDailyReport,
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
  fetchLabMembers,
  fetchLabProfile,
  fetchLabProjects,
  fetchLabRecommendations,
  fetchLabWatch,
  fetchMemberSuggestions,
  fetchLabReminderChannels,
  fetchMyInvitations,
  fetchMyLabs,
  fetchNotifications,
  fetchReminderAccess,
  fetchReminders,
  fetchSaves,
  fetchProfile,
  fetchProjectCollection,
  fetchProjectCollections,
  fetchProjectDigest,
  fetchProjectFeed,
  fetchProjectRecommendations,
  fetchProjects,
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
  attachLabToDept,
  cancelInvitation,
  createCollection,
  createLab,
  createLabInDept,
  createProject,
  createReminder,
  deleteLabLogo,
  deleteReminder,
  detachLabFromDept,
  disconnectDiscord,
  dismissSuggestion,
  ingestProjectLink,
  issueActivationCode,
  issueLabActivationCode,
  removeDeptMember,
  removeLabMember,
  setDiscordDailyReport,
  setLabMemberRole,
  setLabPlanInclusion,
  testDiscordDm,
  inviteToLab,
  joinProject,
  leaveProject,
  removeFromCollection,
  respondToInvitation,
  saveOpportunity,
  shareToProject,
  synthesizeLabProfile,
  unarchiveProject,
  unsaveOpportunity,
  updateAdminLab,
  updateAdminUser,
  updateCollection,
  updateLabProfile,
  updateLabWatch,
  updateProjectCategories,
  updateProjectFocus,
  updateReminder,
  uploadLabLogo,
} from "@/lib/portal/mutations";
import {
  PERSONAL_SLUG,
  type AdminLabUpdate,
  type AdminUsersQuery,
  type AdminUserUpdate,
  type BriefingCategory,
  type InvitationAction,
  type ReminderUpdateInput,
  type SearchSort,
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

/** The caller's retained report history — the Reports page's date list. */
export function useBriefings() {
  return useQuery({
    queryKey: ["portal", "briefings"],
    queryFn: fetchBriefings,
    staleTime: 60_000,
  });
}

/** One archived day of the caller's history. Idle until a date is picked. */
export function useBriefing(date?: string) {
  return useQuery({
    queryKey: ["portal", "briefing", date ?? "none"],
    queryFn: () => fetchBriefingByDate(date as string),
    enabled: Boolean(date),
    // An archived day never changes once written, so there is nothing to refetch.
    staleTime: Infinity,
  });
}

/** A lab's retained report history. Disabled for personal scope. */
export function useLabBriefings(slug?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG);
  return useQuery({
    queryKey: ["portal", "lab-briefings", slug ?? "none"],
    queryFn: () => fetchLabBriefings(slug as string),
    enabled,
    staleTime: 60_000,
  });
}

/** One archived day of a lab's history. Idle until a lab and a date are picked. */
export function useLabBriefing(slug?: string, date?: string) {
  const enabled = Boolean(slug && slug !== PERSONAL_SLUG && date);
  return useQuery({
    queryKey: ["portal", "lab-briefing", slug ?? "none", date ?? "none"],
    queryFn: () => fetchLabBriefingByDate(slug as string, date as string),
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

/** Join / leave / add-member on a project, refreshing both project lists. */
export function useProjectMembership() {
  const queryClient = useQueryClient();
  const invalidate = () => {
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
  return { join, leave, addMember };
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

/** The caller's Discord link status (profile "Connected services" card). */
export function useDiscordStatus() {
  return useQuery({
    queryKey: ["portal", "discord"],
    queryFn: fetchDiscordStatus,
    staleTime: 30_000,
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
  return { add, remove, setRole, cancelInvite };
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
