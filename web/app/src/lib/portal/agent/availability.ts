/**
 * Whether this person may chat with Mylo, read from the gate's own answer.
 *
 * The web holds no permission logic. The catalog route runs the agent's gate
 * for this person (instance switch, plan, their own setting) and, when it
 * refuses, returns a single `*` row with the refusal; the web surface refuses
 * an unverified email before that with a 403. The model status says whether a
 * model is configured at all. This module only maps those answers onto the
 * four states the panel draws.
 */

import type {
  AgentRefusal,
  AgentStatus,
  CatalogEntry,
  ChatAvailability,
} from "./types";

/** What the fix line says when the server's refusal carries none. */
const FALLBACK_FIX: Record<string, string> = {
  unverified: "Open the link in the email we sent you, or send it again from Account.",
};

export function withFix(refusal: AgentRefusal): AgentRefusal {
  return refusal.fix ? refusal : { ...refusal, fix: FALLBACK_FIX[refusal.code] ?? "" };
}

export type CatalogOutcome =
  | { ok: true; functions: CatalogEntry[] }
  | { ok: false; status: number; refusal: AgentRefusal };

export function availabilityFrom(
  catalog: CatalogOutcome | undefined,
  status: AgentStatus | undefined,
): ChatAvailability {
  if (!catalog) return { state: "loading" };
  if (!catalog.ok) {
    // No agent routes at all: the tool is not installed here. Draw nothing.
    if (catalog.status === 404) return { state: "absent" };
    return { state: "denied", refusal: withFix(catalog.refusal) };
  }
  const gate = catalog.functions.find((f) => f.name === "*" && !f.allowed);
  if (gate) {
    return {
      state: "denied",
      refusal: withFix({
        code: gate.code ?? "not_allowed",
        detail: gate.detail ?? "Mylo chat isn't available to you.",
        fix: gate.fix ?? "",
      }),
    };
  }
  if (!status) return { state: "loading" };
  if (status.model === null) {
    return {
      state: "denied",
      refusal: { code: status.code, detail: status.detail, fix: status.fix },
    };
  }
  return { state: "allowed", model: status.model };
}

/**
 * The line under the composer. Nothing for a model on this machine; when the
 * answer comes from somewhere else the chat says so (S-3).
 */
export function modelLine(model: { label: string; name: string; location: string }): string | null {
  if (model.location === "local") return null;
  const name = model.label || model.name;
  if (model.location === "cloud") return `${name} · runs on a cloud service`;
  return `${name} · runs on another server`;
}
