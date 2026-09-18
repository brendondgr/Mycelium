"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

import type { SlotFeedbackKind } from "./types";

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
