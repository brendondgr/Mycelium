"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  fetchConferences,
  fetchDailyBriefing,
  fetchDailyReport,
  fetchDiscordStart,
  fetchDiscordStatus,
  fetchEntitlements,
  fetchLabDailyBriefing,
  fetchLabDiscordStart,
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
  fetchMyInvitations,
  fetchMyLabs,
  fetchNotifications,
  fetchReminders,
  fetchSaves,
  fetchProfile,
  fetchProjectCollection,
  fetchProjectCollections,
  fetchProjectFeed,
  fetchProjectRecommendations,
  fetchProjects,
  fetchSearch,
  fetchWatch,
} from "@/lib/portal/client";
import {
  actOnNotification,
  addProjectMember,
  addToCollection,
  createCollection,
  createLab,
  createProject,
  createReminder,
  deleteLabLogo,
  deleteReminder,
  disconnectDiscord,
  dismissSuggestion,
  ingestProjectLink,
  issueActivationCode,
  testDiscordDm,
  inviteToLab,
  joinProject,
  leaveProject,
  removeFromCollection,
  respondToInvitation,
  saveOpportunity,
  shareToProject,
  synthesizeLabProfile,
  unsaveOpportunity,
  updateCollection,
  updateLabProfile,
  updateLabWatch,
  uploadLabLogo,
} from "@/lib/portal/mutations";
import {
  PERSONAL_SLUG,
  type InvitationAction,
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

/** Create + delete reminders; both refresh the reminders list and the bell. */
export function useReminderMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal", "reminders"] });
    queryClient.invalidateQueries({ queryKey: ["portal", "notifications"] });
  };
  const create = useMutation({ mutationFn: createReminder, onSuccess: invalidate });
  const remove = useMutation({
    mutationFn: (id: string) => deleteReminder(id),
    onSuccess: invalidate,
  });
  return { create, remove };
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
    mutationFn: (input: { name: string; labSlug?: string }) =>
      createProject(input.name, input.labSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal", "projects"] });
      queryClient.invalidateQueries({ queryKey: ["portal", "lab-projects"] });
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
