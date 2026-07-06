"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";
import type {
  InvitationAction,
  LabProfileData,
  MyLab,
  WatchData,
} from "@/lib/portal/types";

/**
 * CSRF-aware writes for the workspace dashboard. Each ensures the CSRF cookie,
 * sends the token as `X-CSRFToken`, and surfaces the first DRF field error as a
 * friendly message the UI can show. Mirrors the auth client's mutation pattern.
 */

function firstError(body: Record<string, unknown> | null): string | null {
  if (!body) {
    return null;
  }
  for (const value of Object.values(body)) {
    if (typeof value === "string" && value) {
      return value;
    }
    if (Array.isArray(value)) {
      const first = value.find((v) => typeof v === "string" && v);
      if (typeof first === "string") {
        return first;
      }
    }
  }
  return null;
}

async function sendJson<T>(
  method: "POST" | "PATCH",
  url: string,
  body: unknown,
  fallbackMessage: string,
): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let parsed: (T & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as T & Record<string, unknown>;
  } catch {
    parsed = null;
  }

  if (!response.ok) {
    throw new Error(firstError(parsed) ?? fallbackMessage);
  }
  return parsed as T;
}

/** Create a lab; the caller becomes its PI. */
export function createLab(name: string): Promise<MyLab> {
  return sendJson<MyLab>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs"),
    { name },
    "Could not create the lab. Try again.",
  );
}

/** Invite a person to a lab by email or username. */
export function inviteToLab(
  slug: string,
  identifier: string,
  role = "member",
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "invitations"),
    { identifier, role },
    "Could not send the invitation.",
  );
}

/** Accept, reject, or ignore one of the caller's pending invitations. */
export function respondToInvitation(
  id: string,
  action: InvitationAction,
): Promise<{ id: string; status: string }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "invitations", id, "respond"),
    { action },
    "Could not respond to the invitation.",
  );
}

/** Create a project scoped to a lab (slug) or personally (no slug). */
export function createProject(
  name: string,
  labSlug?: string,
): Promise<{ id: string; name: string }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects"),
    labSlug ? { name, lab: labSlug } : { name },
    "Could not create the project.",
  );
}

/** The caller joins a lab/department project they are eligible for. */
export function joinProject(id: string): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "join"),
    undefined,
    "Could not join the project.",
  );
}

/** The caller leaves a project they belong to. */
export function leaveProject(id: string): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "leave"),
    undefined,
    "Could not leave the project.",
  );
}

/** A lab manager adds another lab member to one of the lab's projects. */
export function addProjectMember(
  id: string,
  username: string,
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "members"),
    { username },
    "Could not add the member.",
  );
}

/** Update a lab's collective purpose & goals. */
export function updateLabProfile(
  slug: string,
  payload: Partial<
    Pick<
      LabProfileData,
      "statement" | "areas" | "funding_needs" | "strategic_needs" | "interests"
    >
  >,
): Promise<LabProfileData> {
  return sendJson<LabProfileData>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "profile"),
    payload,
    "Could not save the lab's purpose and goals.",
  );
}

/** Update what Milo watches for a lab. */
export function updateLabWatch(
  slug: string,
  payload: Partial<WatchData>,
): Promise<WatchData> {
  return sendJson<WatchData>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "watch"),
    payload,
    "Could not save the lab's watch settings.",
  );
}

/** The draft a lab synthesis returns for the review step (nothing is saved). */
export type LabSynthesisResult = {
  statement: string;
  areas: string[];
  keywords: string[];
};

/**
 * Draft a lab's statement/areas/keywords from the PI's description plus source
 * material — dropped files (parsed to text server-side) and pasted profile links
 * (imported best-effort). Sent as multipart so files ride along.
 */
export async function synthesizeLabProfile(
  slug: string,
  input: {
    description: string;
    areas: string[];
    links: string[];
    files: File[];
  },
): Promise<LabSynthesisResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const form = new FormData();
  form.append("description", input.description);
  form.append("areas", JSON.stringify(input.areas));
  form.append("links", input.links.join("\n"));
  for (const file of input.files) {
    form.append("files", file);
  }

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "intake", "synthesize"),
    {
      method: "POST",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
      body: form,
    },
  );

  let parsed: (LabSynthesisResult & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as LabSynthesisResult &
      Record<string, unknown>;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    throw new Error(
      firstError(parsed) ??
        "Could not synthesize the lab profile. You can fill it in manually.",
    );
  }
  return parsed as LabSynthesisResult;
}
