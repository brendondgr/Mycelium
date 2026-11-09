/**
 * Shapes of Mylo's agent API (`api/tools/agent/`, docs/api-contract.md "Mylo
 * agent"). The panel only ever reads the **activity view**: what Mylo is
 * doing, never its reasoning (S-9). Nothing here can carry thinking text —
 * the activity view sends `{state: "thinking"}` and nothing else.
 */

export type AgentModel = {
  name: string;
  label: string;
  /** `local` runs on this machine; `remote` / `cloud` do not (S-3). */
  location: "local" | "remote" | "cloud" | string;
};

export type AgentStatus =
  | { model: AgentModel }
  | { model: null; code: string; detail: string; fix: string };

/** Anything a conversation can be about (S2). */
export type AnchorKind = "item" | "project" | "lab" | "department";

export type AgentAnchor = { kind: AnchorKind | string; key: string };

export type ThreadScope = "personal" | "lab" | "department" | "project";

export type ThreadState = "idle" | "running" | "waiting" | "error" | string;

/** One numbered reference in a thread (`#n` in Mylo's text). */
export type AgentReference = {
  n: number;
  ref: string;
  kind: string;
  key: string;
  title: string;
};

export type AgentTodo = { text?: string; title?: string; status?: string; done?: boolean };

export type AgentThread = {
  id: string;
  title: string;
  purpose: string;
  state: ThreadState;
  scope: ThreadScope;
  scope_ref: string | null;
  archived: boolean;
  pinned: boolean;
  parent: string | null;
  fork_seq: number | null;
  created_at: string;
  last_activity_at: string;
  anchor: AgentAnchor | null;
  todos: AgentTodo[];
  references: AgentReference[];
};

/** A stored event from `events/`. */
export type AgentEvent = {
  seq: number;
  type: string;
  ts: string | null;
  payload: Record<string, unknown>;
};

/**
 * A message from `stream/`. Stored events carry their seq as `id`; transient
 * ones (text deltas, a collapsed thinking marker, the context meter) do not.
 */
export type StreamMessage = {
  id?: number;
  type: string;
  thread?: string;
  ts?: string | null;
  payload?: Record<string, unknown>;
  /** `delta` only. */
  kind?: string;
  text?: string;
};

export type ActivityPayload =
  | { state: "thinking" }
  | {
      state: "running" | "ok" | "failed";
      label: string;
      call_id: string;
      name: string;
    };

export type SendResult = { status: "started" | "queued" | "steered"; seq?: number };

export type AgentPreferences = {
  chat_enabled: boolean;
  learning: boolean;
  discord_allowed: boolean;
  groups_off: string[];
};

export type AgentPolicy = {
  groups_off: string[];
  discord_channels_off: string[];
  max_risk: string;
  members_inform_org: boolean;
  set: boolean;
};

export type CatalogEntry = {
  name: string;
  group: string;
  summary: string;
  allowed: boolean;
  layer?: number;
  code?: string;
  detail?: string;
  fix?: string;
};

/** A refusal in the agent's own words: what happened and how to change it. */
export type AgentRefusal = { code: string; detail: string; fix: string };

/**
 * Whether this person may chat, as the gate answers it. The web decides
 * nothing: it reads the catalog's answer and the model status.
 */
export type ChatAvailability =
  | { state: "loading" }
  | { state: "absent" }
  | { state: "allowed"; model: AgentModel }
  | { state: "denied"; refusal: AgentRefusal };

export type RefSearchResult = {
  ref: string;
  kind: string;
  title: string;
  card: string;
};
