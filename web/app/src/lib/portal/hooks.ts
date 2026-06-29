"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchLabMembers,
  fetchMyLabs,
  fetchProfile,
  fetchProjects,
  fetchWatch,
} from "@/lib/portal/client";
import { ALL_LABS_SLUG } from "@/lib/portal/types";

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
