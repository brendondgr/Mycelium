export type AuthUser = {
  id: number;
  username: string;
  email: string;
  /** Display name (full name when set, else username) and avatar initials. */
  name?: string;
  initials?: string;
  is_staff: boolean;
  is_superuser: boolean;
  /** False until the user finishes profile onboarding (saves research areas). */
  onboarding_completed: boolean;
};

export type AuthErrorBody = {
  non_field_errors?: string[];
  detail?: string;
};

export type AccountType = "personal" | "lab" | "department";

export type RegisterInput = {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  account_type: AccountType;
  org_name?: string;
  institution?: string;
};

/** A single publication source the onboarding importer can pull an author from. */
export type ResearchSource = "openalex" | "semantic" | "scholar";

/** The contract-shaped research interests stored on a profile. */
export type ResearchInterests = {
  version: number;
  areas: string[];
  statement?: string;
  keywords?: string[];
  skills?: string[];
  sources?: Record<string, unknown>;
};

/** The aggregated author draft returned alongside synthesized interests. */
export type ResearchDraft = {
  display_name: string;
  institution: string;
  areas: string[];
  keywords: string[];
  skills: string[];
  coauthors: string[];
  external_ids: Record<string, string>;
  evidence: Array<Record<string, unknown>>;
};

export type SynthesizeResult = {
  draft: ResearchDraft;
  interests: ResearchInterests;
};

/** Inputs to the synthesize call: at most one site, plus an optional résumé. */
export type SynthesizeInput = {
  source?: ResearchSource;
  identifier?: string;
  resume?: File | null;
};

export type WatchCadence = "daily" | "weekly";

export type WatchPreference = {
  topics: string[];
  categories: string[];
  cadence: WatchCadence;
};

/** Person-global profile basics captured in onboarding (role + institution). */
export type ProfileBasics = {
  academic_title?: string;
  institution?: string;
};
