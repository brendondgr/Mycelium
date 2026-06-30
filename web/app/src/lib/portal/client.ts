import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import type {
  DailyReport,
  LabMember,
  MyLab,
  Project,
  ProfileData,
  WatchData,
} from "@/lib/portal/types";

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
