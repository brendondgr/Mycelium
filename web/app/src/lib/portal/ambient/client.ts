"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

import type {
  AmbientSettings,
  AnswerResult,
  Change,
  Development,
  OrgServer,
  RecordingState,
  Suggestion,
  Understanding,
} from "./types";

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok && response.status !== 409) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : fallback;
    throw new Error(detail);
  }
  return body as T;
}

async function send<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string[],
  body: unknown,
  fallback: string,
): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(buildApiUrl(getPublicApiBase(), ...path), {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) {
    return undefined as T;
  }
  return readJson(response, fallback);
}

async function get<T>(path: string[], fallback: string): Promise<T> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), ...path), {
    credentials: "include",
  });
  return readJson(response, fallback);
}

export function fetchSuggestions(): Promise<{ suggestions: Suggestion[] }> {
  return get(["ambient", "suggestions"], "Could not load Mylo's questions.");
}

export function answerSuggestion(
  id: number,
  body: { choice: string; correction?: string },
): Promise<AnswerResult> {
  return send("POST", ["ambient", "suggestions", String(id), "answer"], body, "Your answer did not go through.");
}

export function fetchChanges(): Promise<{ changes: Change[] }> {
  return get(["ambient", "changes"], "Could not load what changed.");
}

export function undoChange(id: number): Promise<{ change: Change; undo: Change }> {
  return send("POST", ["ambient", "changes", String(id), "undo"], {}, "Could not undo that.");
}

export function fetchUnderstanding(): Promise<Understanding> {
  return get(["ambient", "understanding"], "Could not load what Mylo knows.");
}

export function editUnderstanding(
  conceptId: number,
  relation: string,
  label: string,
): Promise<Understanding> {
  return send(
    "PATCH",
    ["ambient", "understanding", String(conceptId), relation],
    { label },
    "Could not save that.",
  );
}

export function deleteUnderstanding(conceptId: number, relation: string): Promise<void> {
  return send(
    "DELETE",
    ["ambient", "understanding", String(conceptId), relation],
    undefined,
    "Could not delete that.",
  );
}

export function reopenUnderstanding(conceptId: number, relation: string): Promise<{ change: Change }> {
  return send(
    "POST",
    ["ambient", "understanding", String(conceptId), relation, "reopen"],
    {},
    "Could not reopen that.",
  );
}

export function fetchAmbientSettings(): Promise<AmbientSettings> {
  return get(["ambient", "settings"], "Could not load your settings.");
}

export function saveAmbientSettings(body: {
  listening_discord?: boolean;
  listening_slack?: boolean;
  listening_teams?: boolean;
  questions_muted?: boolean;
  quiet_until?: string | null;
  personal_withheld?: boolean;
}): Promise<AmbientSettings> {
  return send("PUT", ["ambient", "settings"], body, "Could not save your settings.");
}

export function deleteObservations(): Promise<{ deleted_observations: number }> {
  return send("POST", ["ambient", "observations", "delete"], { confirm: true }, "Could not delete.");
}

export function fetchProjectDevelopments(projectId: string): Promise<{ developments: Development[] }> {
  return get(["ambient", "projects", projectId, "developments"], "Could not load this project's developments.");
}

export function fetchLabChanges(slug: string): Promise<{ changes: Change[] }> {
  return get(["ambient", "labs", slug, "changes"], "Could not load the lab's changes.");
}

export function fetchRecording(): Promise<RecordingState> {
  return get(["ambient", "recording"], "Could not load what Mylo records.");
}

export function saveRecording(
  body: { server: number; record: boolean } | { project: string; record: boolean },
): Promise<RecordingState> {
  return send("POST", ["ambient", "recording"], body, "Could not save that.");
}

export function fetchOrgServers(
  kind: "lab" | "department",
  ref: string,
): Promise<{ servers: OrgServer[] }> {
  return get(["ambient", "servers", kind, ref], "Could not load the servers.");
}

export async function saveOrgServer(
  kind: "lab" | "department",
  ref: string,
  body: { guild_id: string; on: boolean },
): Promise<{ servers: OrgServer[] }> {
  const out = await send<{ servers?: OrgServer[]; detail?: string }>(
    "POST",
    ["ambient", "servers", kind, ref],
    body,
    "Could not change listening.",
  );
  // A 409 comes back as a body with only a detail (listening is off here).
  if (!out?.servers) throw new Error(out?.detail ?? "Could not change listening.");
  return { servers: out.servers };
}
