"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

import type {
  Audience,
  CollaborationPreview,
  CollaborationSetting,
  OpenTo,
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
