"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

import type {
  Audience,
  CollaborationPreview,
  CollaborationSetting,
  Lane,
  OpenTo,
  QuerySlot,
  SavedPerson,
  SearchAvailability,
  SearchEntry,
  SearchResponse,
  SlotFeedbackKind,
} from "./types";

/** Tell Mylo a call's slot is wrong, covered, or missing. Append-only. */
export async function sendSlotFeedback(
  contentId: string,
  body: { kind: SlotFeedbackKind; slot_text?: string; note?: string },
): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "collab", "calls", contentId, "slot-feedback"),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    throw new Error("Mylo could not record that just now.");
  }
}

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : fallback;
    throw new Error(detail);
  }
  return body as T;
}

export async function fetchCollaborationSetting(): Promise<CollaborationSetting> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "collab", "settings"), {
    credentials: "include",
  });
  return readJson(response, "Could not load your collaboration setting.");
}

export async function saveCollaborationSetting(body: {
  open: boolean;
  audience: Audience;
  open_to: OpenTo[];
  renew?: boolean;
}): Promise<CollaborationSetting> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(buildApiUrl(getPublicApiBase(), "collab", "settings"), {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: JSON.stringify(body),
  });
  return readJson(response, "Could not save your collaboration setting.");
}

export async function fetchCollaborationPreview(): Promise<CollaborationPreview> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "collab", "preview"), {
    credentials: "include",
  });
  return readJson(response, "Could not load the preview.");
}


async function postJson<T>(path: string[], body: unknown, fallback: string): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(buildApiUrl(getPublicApiBase(), ...path), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: JSON.stringify(body),
  });
  return readJson(response, fallback);
}

export async function fetchSearchAvailability(): Promise<SearchAvailability> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "collab", "search"), {
    credentials: "include",
  });
  return readJson(response, "Could not check collaborator search.");
}

/** The pre-filled query for an entry point, without searching. */
export function prefillSearch(entry: SearchEntry): Promise<{ slots: QuerySlot[] }> {
  return postJson(["collab", "search"], { ...entry, dry_run: true }, "Could not prepare the search.");
}

export function runSearch(
  entry: SearchEntry,
  options: { slots: QuerySlot[]; lanes: Lane[]; scope: Audience },
): Promise<SearchResponse> {
  return postJson(["collab", "search"], { ...entry, ...options }, "The search did not run.");
}

export function sendMatchFeedback(
  searchId: number,
  body: { candidate: string; lane: Lane; kind: "save" | "not_relevant" },
): Promise<unknown> {
  return postJson(
    ["collab", "searches", String(searchId), "feedback"],
    body,
    "Could not record that.",
  );
}

export async function fetchSavedPeople(): Promise<{ people: SavedPerson[] }> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "collab", "saved"), {
    credentials: "include",
  });
  return readJson(response, "Could not load saved people.");
}
