"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchDailyReport,
  fetchLabMembers,
  fetchLabProfile,
  fetchMyInvitations,
  fetchMyLabs,
  fetchProfile,
  fetchProjects,
  fetchWatch,
} from "@/lib/portal/client";
import {
  createLab,
  createProject,
  inviteToLab,
  respondToInvitation,
  updateLabProfile,
} from "@/lib/portal/mutations";
import { ALL_LABS_SLUG, type InvitationAction } from "@/lib/portal/types";

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
 * synthetic "All labs" slug (or nothing) returns the full visible set.
 */
export function useProjects(labSlug?: string) {
  const scoped = labSlug && labSlug !== ALL_LABS_SLUG ? labSlug : undefined;
  return useQuery({
    queryKey: ["portal", "projects", scoped ?? "all"],
    queryFn: () => fetchProjects(scoped),
    staleTime: 30_000,
  });
}

/** Members of a single lab. Disabled for the synthetic "All labs" scope. */
export function useLabMembers(slug?: string) {
  const enabled = Boolean(slug && slug !== ALL_LABS_SLUG);
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

/** The caller's pending lab invitations (notifications panel). */
export function useMyInvitations() {
  return useQuery({
    queryKey: ["portal", "invitations"],
    queryFn: fetchMyInvitations,
    staleTime: 30_000,
  });
}

/** A single lab's collective purpose & goals. Disabled for the "All labs" scope. */
export function useLabProfile(slug?: string) {
  const enabled = Boolean(slug && slug !== ALL_LABS_SLUG);
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
    },
  });
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
