/**
 * The ambient profile as the "Mylo & you" page sees it (ambient Plans 06–07).
 * Shapes mirror `/api/ambient/…` (`docs/api-contract.md`). Nothing here is
 * ever a person's words from conversation — none are kept.
 */

export type SuggestionKind =
  | "interest"
  | "skill"
  | "development"
  | "intent"
  | "clarify"
  | "review";

export type Choice = { key: string; label: string };

export type Suggestion = {
  id: number;
  kind: SuggestionKind;
  topic: string;
  question: string;
  explanation: string;
  choices: Choice[];
  project: { id: string; name: string } | null;
  state: "pending" | "asked" | "answered" | "expired" | "withdrawn";
  asked_at: string | null;
  expires_at: string;
};

export type AnswerResult = {
  taken: boolean;
  message: string;
  suggestion: Suggestion;
};

export type ChangeKind =
  | "exploration_confirmed"
  | "exploration_kept"
  | "exploration_dropped"
  | "understanding_confirmed"
  | "development_recorded"
  | "development_confirmed"
  | "profile_edit"
  | "state_edit"
  | "undone";

export type Change = {
  id: number;
  kind: ChangeKind;
  kind_label: string;
  topic: string;
  project: { id: string; name: string } | null;
  field: string;
  old_value: unknown;
  new_value: unknown;
  surface: "" | "dm" | "web" | "told";
  explanation: string;
  visibility: "personal" | "lab";
  by: { id: number; name: string; you: boolean };
  created_at: string;
  undone_at: string | null;
  undo_of: number | null;
  can_undo: boolean;
};

export type UnderstandingEdge = {
  concept_id: number;
  label: string;
  facet: string;
  relation: string;
  tier: "declared" | "demonstrated" | "conversational";
  status: "pending" | "active" | "faded" | "rejected";
  kind: string;
  source: string;
  first_seen: string;
  last_reinforced: string;
  review_on: string | null;
  edited: boolean;
  editable: boolean;
  eligible_again_on?: string;
  resting?: boolean;
};

export type Development = {
  id: number;
  project: { id: string; name: string };
  change: string;
  change_label: string;
  topic: string;
  account: string;
  explanation: string;
  occurred_on: string;
  status: "pending" | "active" | "confirmed" | "superseded" | "rejected";
  origin: "told" | "conversation";
  visibility: "personal" | "lab";
};

export type Understanding = {
  statement: string;
  edges: UnderstandingEdge[];
  developments: Development[];
};

export type AmbientSettings = {
  available: boolean;
  paid: boolean;
  linked: boolean;
  /** Plan 11: linked on Slack, and its own opt-in. */
  slack_linked?: boolean;
  teams_linked?: boolean;
  transcripts?: boolean;
  listening: { discord: boolean; slack?: boolean; teams?: boolean };
  questions_muted: boolean;
  quiet_until: string | null;
  statement: string;
  observations: number;
};

/** One shared server that could hear you: the head's switch, yours, the lock. */
export type RecordingServer = {
  id: number;
  label: string;
  platform: string;
  orgs: string[];
  server_listening: boolean;
  excluded: boolean;
  /** Both halves on: what your switch shows. */
  recording: boolean;
  /** The head switched listening off here; you cannot turn it back on. */
  locked: boolean;
  locked_reason: string;
};

export type RecordingProject = { id: string; name: string; excluded: boolean };

export type RecordingState = {
  servers: RecordingServer[];
  projects: RecordingProject[];
};

/** One of an org's Discord servers and whether Mylo listens there. */
export type OrgServer = {
  guild_id: string;
  name: string;
  listening: boolean;
  available: boolean;
  shared_with: string[];
};
