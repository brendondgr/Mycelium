"use client";

import { ApiError } from "@/lib/api-error";
import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";

import type {
  AgentAnchor,
  AgentEvent,
  AgentPolicy,
  AgentPreferences,
  AgentRefusal,
  AgentStatus,
  AgentThread,
  CatalogEntry,
  RefSearchResult,
  SendResult,
  ThreadScope,
  ThreadState,
} from "./types";

/**
 * Mylo's agent API (`api/tools/agent/`). Every error the agent returns is
 * `{code, detail, fix}`; `AgentError` keeps all three so the panel can say
 * what happened and where to change it, in the agent's own words.
 */

export class AgentError extends ApiError {
  readonly code: string;
  readonly fix: string;

  constructor(refusal: AgentRefusal, status: number) {
    super(refusal.detail, status);
    this.name = "AgentError";
    this.code = refusal.code;
    this.fix = refusal.fix;
  }

  get refusal(): AgentRefusal {
    return { code: this.code, detail: this.message, fix: this.fix };
  }
}

export function agentUrl(...segments: string[]): string {
  return buildApiUrl(getPublicApiBase(), "tools", "agent", ...segments);
}

/** `{code, detail, fix}` from an error body, whatever shape it came in. */
export function refusalFrom(
  body: unknown,
  status: number,
  fallback: string,
): AgentRefusal {
  const b = (body && typeof body === "object" ? body : {}) as Record<
    string,
    unknown
  >;
  const detail = typeof b.detail === "string" && b.detail ? b.detail : fallback;
  let code = typeof b.code === "string" && b.code ? b.code : "";
  if (!code) {
    // DRF's own refusals carry no code. A 403 before the gate is the
    // verified-email check (the web surface's only precondition).
    code = status === 403 ? "unverified" : status === 404 ? "not_found" : "error";
  }
  const fix = typeof b.fix === "string" ? b.fix : "";
  return { code, detail, fix };
}

async function request<T>(
  url: string,
  init: RequestInit & { json?: unknown },
  fallback: string,
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {};
  if (method !== "GET") {
    await ensureCsrfCookie();
    const token = readCsrfToken();
    if (token) headers["X-CSRFToken"] = token;
  }
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const response = await fetch(url, {
    method,
    credentials: "include",
    cache: "no-store",
    headers,
    body,
  });
  if (response.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new AgentError(refusalFrom(data, response.status, fallback), response.status);
  }
  return data as T;
}

// -- reads -------------------------------------------------------------------

export function fetchAgentStatus(): Promise<AgentStatus> {
  return request(agentUrl("status"), {}, "Could not reach Mylo.");
}

export async function fetchAgentCatalog(): Promise<CatalogEntry[]> {
  const data = await request<{ functions: CatalogEntry[] }>(
    agentUrl("catalog"),
    {},
    "Could not reach Mylo.",
  );
  return data.functions;
}

export type ThreadQuery = {
  q?: string;
  archived?: boolean;
  anchor?: AgentAnchor | null;
};

export function threadQueryString(query: ThreadQuery = {}): string {
  const params = new URLSearchParams();
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.archived) params.set("archived", "1");
  if (query.anchor) params.set("anchor", `${query.anchor.kind}:${query.anchor.key}`);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function fetchThreads(query: ThreadQuery = {}): Promise<AgentThread[]> {
  const data = await request<{ threads: AgentThread[] }>(
    agentUrl("threads") + threadQueryString(query),
    {},
    "Could not load your conversations.",
  );
  return data.threads;
}

export function fetchThread(id: string): Promise<AgentThread> {
  return request(agentUrl("threads", id), {}, "Could not load this conversation.");
}

export function fetchThreadEvents(
  id: string,
  after = 0,
): Promise<{ events: AgentEvent[]; state: ThreadState }> {
  // `view` is left out on purpose: the default is the activity view, and the
  // panel never asks for anything else.
  const qs = after > 0 ? `?after=${after}` : "";
  return request(
    agentUrl("threads", id, "events") + qs,
    {},
    "Could not load this conversation.",
  );
}

export async function searchRefs(
  q: string,
  threadId?: string | null,
): Promise<RefSearchResult[]> {
  const params = new URLSearchParams({ q });
  if (threadId) params.set("thread", threadId);
  const data = await request<{ results: RefSearchResult[] }>(
    agentUrl("refs", "search") + `?${params}`,
    {},
    "Could not search.",
  );
  return data.results;
}

export function fetchAgentPreferences(): Promise<AgentPreferences> {
  return request(agentUrl("preferences"), {}, "Could not load your Mylo settings.");
}

export function fetchAgentPolicy(
  kind: "lab" | "department",
  ref: string,
): Promise<AgentPolicy> {
  return request(agentUrl("policy", kind, ref), {}, "Could not load the policy.");
}

// -- writes ------------------------------------------------------------------

export type NewThread = {
  scope?: ThreadScope;
  ref?: string | null;
  anchor?: AgentAnchor | null;
  title?: string;
};

export function createThread(input: NewThread): Promise<AgentThread> {
  const json: Record<string, unknown> = {};
  if (input.scope && input.scope !== "personal") {
    json.scope = input.scope;
    json.ref = input.ref;
  }
  if (input.anchor) json.anchor = input.anchor;
  if (input.title) json.title = input.title;
  return request(
    agentUrl("threads"),
    { method: "POST", json },
    "Could not start a conversation.",
  );
}

export function sendMessage(
  id: string,
  text: string,
  mentions: string[] = [],
): Promise<SendResult> {
  return request(
    agentUrl("threads", id, "messages"),
    { method: "POST", json: { text, mentions } },
    "Mylo did not get that message.",
  );
}

export function answerQuestion(id: string, text: string): Promise<SendResult> {
  return request(
    agentUrl("threads", id, "answer"),
    { method: "POST", json: { text } },
    "Mylo did not get that answer.",
  );
}

export function cancelTurn(id: string): Promise<{ status: string }> {
  return request(
    agentUrl("threads", id, "cancel"),
    { method: "POST", json: {} },
    "Could not stop Mylo.",
  );
}

export function updateThread(
  id: string,
  changes: { title?: string; archived?: boolean; pinned?: boolean },
): Promise<AgentThread> {
  return request(
    agentUrl("threads", id),
    { method: "PATCH", json: changes },
    "Could not change this conversation.",
  );
}

export function deleteThread(id: string): Promise<void> {
  return request(
    agentUrl("threads", id),
    { method: "DELETE" },
    "Could not delete this conversation.",
  );
}

export function saveAgentPreferences(
  changes: Partial<AgentPreferences>,
): Promise<AgentPreferences> {
  return request(
    agentUrl("preferences"),
    { method: "PATCH", json: changes },
    "Could not save your Mylo settings.",
  );
}

export function saveAgentPolicy(
  kind: "lab" | "department",
  ref: string,
  changes: Partial<AgentPolicy>,
): Promise<AgentPolicy> {
  return request(
    agentUrl("policy", kind, ref),
    { method: "PATCH", json: changes },
    "Could not save the policy.",
  );
}
