"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

/**
 * Slack (ambient Plan 11): link a person by a code they DM to Mylo, link a
 * lab's workspace by a code a manager posts in a channel, and the lab's
 * switches. Shapes mirror `/api/integrations/slack/…` (`docs/api-contract.md`).
 */
export type SlackStatus = {
  enabled: boolean;
  installable: boolean;
  identities: { team_id: string; team: string; linked_at: string }[];
  lab_workspace: {
    team_id: string;
    name: string;
    has_channel: boolean;
    listening: boolean;
    primary: boolean;
  } | null;
};

export type SlackCode = { code: string; expires_in: number };

async function call<T>(method: "GET" | "POST", path: string[], query = "", body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") {
    await ensureCsrfCookie();
    const csrfToken = readCsrfToken();
    headers["Content-Type"] = "application/json";
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  }
  const response = await fetch(`${buildApiUrl(getPublicApiBase(), ...path)}${query}`, {
    method,
    credentials: "include",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : "Slack didn't answer. Try again.";
    throw new Error(detail);
  }
  return data as T;
}

const labQuery = (slug?: string) => (slug ? `?lab=${encodeURIComponent(slug)}` : "");

export function useSlackStatus(labSlug?: string) {
  return useQuery({
    queryKey: ["portal", "slack", labSlug ?? ""],
    queryFn: () => call<SlackStatus>("GET", ["integrations", "slack", "status"], labQuery(labSlug)),
  });
}

export function useSlackLinkCode() {
  return useMutation({
    mutationFn: () => call<SlackCode>("POST", ["integrations", "slack", "link-code"]),
  });
}

export function useSlackLabCode(labSlug: string) {
  return useMutation({
    mutationFn: () =>
      call<SlackCode>("POST", ["integrations", "slack", "lab-code"], labQuery(labSlug)),
  });
}

export function useSlackUnlink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) =>
      call<{ unlinked: number }>("POST", ["integrations", "slack", "unlink"], "", { team_id: teamId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal", "slack"] }),
  });
}

export function useSlackLabSwitches(labSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { on?: boolean; primary?: boolean }) =>
      call<{ listening?: boolean; primary: boolean }>(
        "POST",
        ["integrations", "slack", "listening"],
        labQuery(labSlug),
        body,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal", "slack"] }),
  });
}

/** Teams (ambient Plan 11): the same shapes, under /integrations/teams/. */
export type TeamsStatus = {
  enabled: boolean;
  identities: { tenant_id: string; linked_at: string }[];
  lab_team: {
    team_id: string;
    name: string;
    has_channel: boolean;
    listening: boolean;
    primary: boolean;
  } | null;
};

export function useTeamsStatus(labSlug?: string) {
  return useQuery({
    queryKey: ["portal", "teams", labSlug ?? ""],
    queryFn: () => call<TeamsStatus>("GET", ["integrations", "teams", "status"], labQuery(labSlug)),
  });
}

export function useTeamsLinkCode() {
  return useMutation({
    mutationFn: () => call<SlackCode>("POST", ["integrations", "teams", "link-code"]),
  });
}

export function useTeamsLabCode(labSlug: string) {
  return useMutation({
    mutationFn: () =>
      call<SlackCode>("POST", ["integrations", "teams", "lab-code"], labQuery(labSlug)),
  });
}

export function useTeamsLabSwitches(labSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { on?: boolean; primary?: boolean }) =>
      call<{ listening?: boolean; primary: boolean }>(
        "POST",
        ["integrations", "teams", "lab"],
        labQuery(labSlug),
        body,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal", "teams"] }),
  });
}

/** Meeting transcripts (ambient Plan 11): upload, then say who was who. */
export type TranscriptPreview = {
  labels: string[];
  members: { id: number; name: string }[];
};
export type TranscriptRead = {
  meeting: number;
  turns: number;
  participants: number;
  counts: Record<string, number>;
};

export async function uploadTranscript(form: FormData): Promise<TranscriptPreview | TranscriptRead> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(buildApiUrl(getPublicApiBase(), "ambient", "transcripts"), {
    method: "POST",
    credentials: "include",
    headers: csrfToken ? { "X-CSRFToken": csrfToken } : {},
    body: form,
  });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : "The transcript didn't go through.";
    throw new Error(detail);
  }
  return data as TranscriptPreview | TranscriptRead;
}
