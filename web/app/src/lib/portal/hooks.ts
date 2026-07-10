"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchConferences,
  fetchDailyReport,
  fetchDeadlines,
  fetchFellowships,
  fetchGrants,
  fetchLabMembers,
  fetchLabProfile,
  fetchLabProjects,
  fetchLabRecommendations,
  fetchLabWatch,
  fetchMyInvitations,
  fetchMyLabs,
  fetchNotifications,
  fetchProfile,
  fetchProjectFeed,
  fetchProjectRecommendations,
  fetchProjects,
  fetchWatch,
} from "@/lib/portal/client";
import {
  addProjectMember,
  createLab,
  createProject,
  ingestProjectLink,
  inviteToLab,
  joinProject,
  leaveProject,
  respondToInvitation,
  saveOpportunity,
  shareToProject,
  synthesizeLabProfile,
  unsaveOpportunity,
  updateLabProfile,
  updateLabWatch,
} from "@/lib/portal/mutations";
import { PERSONAL_SLUG, type InvitationAction } from "@/lib/portal/types";

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

/** What Milo watches for the caller. */
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

/** Deadline alerts due within a week (the header notification bell). */
export function useNotifications() {
  return useQuery({
    queryKey: ["portal", "notifications"],
    queryFn: fetchNotifications,
    staleTime: 60_000,
  });
}

/** Save or unsave a grant/conference/fellowship; refreshes the feeds, deadlines, and bell. */
export function useSaveOpportunity() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    for (const key of [
      "grants",
      "conferences",
      "fellowships",
      "deadlines",
      "notifications",
    ]) {
      queryClient.invalidateQueries({ queryKey: ["portal", key] });
    }
  };
  const save = useMutation({
    mutationFn: ({ contentId, note }: { contentId: string; note?: string }) =>
      saveOpportunity(contentId, note),
    onSuccess: invalidate,
  });
  const unsave = useMutation({
    mutationFn: (contentId: string) => unsaveOpportunity(contentId),
    onSuccess: invalidate,
  });
  return { save, unsave };
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

/** What Milo watches for a lab. Disabled for the personal-workspace scope. */
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
