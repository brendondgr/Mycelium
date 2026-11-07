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
  /**
   * Whether the account is activated. Verifying the email is what activates it,
   * and until then the backend refuses to create a lab or department, edit
   * either's profile, or send an invitation.
   */
  is_verified?: boolean;
  /** The institution the verified email proves; "" until verified or for a
   *  personal address. Never typed — see `InstitutionFromEmail`. */
  institution?: string;
  institution_verified?: boolean;
  /** What the current address would prove once verified; "" for none. */
  institution_from_email?: string;
};

/** The Account page's view of who the user is — `GET /api/auth/account/`. */
export type AccountDetails = {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  /** Derived from the verified email by the backend; read-only. */
  institution: string;
  institution_verified: boolean;
  /** What the current address would prove once verified; "" for none. */
  institution_from_email: string;
  academic_title: string;
  is_verified: boolean;
  /** A new address waiting on its code, or "" when no change is in flight. */
  pending_email: string;
};

/** The subset of `AccountDetails` this page may write directly. */
export type AccountUpdate = Partial<
  Pick<
    AccountDetails,
    "first_name" | "last_name" | "academic_title"
  >
>;

export type AuthErrorBody = {
  non_field_errors?: string[];
  detail?: string;
};

/** Which kind of organization an invitation leads into. */
export type OrgKind = "lab" | "department";

/** Sign-up makes one solo account. Labs and departments come later, in the app. */
export type RegisterInput = {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  /**
   * The instance's shared sign-up code, when its policy is `mode: "code"`. Never
   * needed with an `invite_token` — someone already inside asked for this person
   * by name.
   */
  access_code?: string;
  /** A join link's token, from `/join/<token>`. */
  invite_token?: string;
};

/** How this instance lets people in — `[signup]` in the operator's mycelium.toml. */
export type SignupPolicy = {
  mode: "closed" | "invite" | "code" | "domain" | "open";
  /** Whether a new account must answer a mailed code before it is active. */
  verify_email: boolean;
  /** The allowed email domains, for `mode: "domain"`. */
  domains: string[];
};

/** What an invitation link says about itself, before anyone has an account. */
export type InvitePreview = {
  org_kind: OrgKind;
  org_name: string;
  role: string;
  /** `email` is bound to one address; `link` is bounded by uses and a clock. */
  kind: "email" | "link";
  /** The address an email invite is spendable by; "" for a share link. */
  email: string;
  message: string;
  invited_by: string;
  expires_at: string;
  /** Present only when the visitor is already signed in. */
  signed_in_as?: string;
  email_matches?: boolean;
};

/** Why a link no longer works — an invitation is not simply "not found". */
export type InviteDeadReason =
  | "invalid"
  | "revoked"
  | "expired"
  | "exhausted"
  | "wrong_email";

/** What accepting an invitation lands the caller in. */
export type InviteAccepted = {
  org_kind: OrgKind;
  org_name: string;
  slug: string | null;
  department_id: string | null;
  role: string;
};

/** A single publication source the onboarding importer can pull an author from. */
export type ResearchSource = "openalex" | "semantic" | "scholar";

/**
 * Fellowship eligibility block stored inside `interests.eligibility`.
 * Sent to the backend via `confirmInterests`; returned on profile GET.
 * The pre-existing `career_stage` key is preserved if present.
 */
export type ProfileEligibility = {
  citizenship: "us" | "international";
  /**
   * Where the applicant stands on the career ladder — the rule engine's one
   * asymmetric gate: an award whose earliest acceptable stage is above this is
   * hidden, while standing past an award's range only softens it. `""` means
   * unknown, and the backend then derives it from `career_stage` or the profile's
   * academic title before giving up and leaving stage unfiltered.
   */
  stage: "masters" | "doctoral_early" | "doctoral_dissertation" | "postdoc" | "";
  /** Broad discipline buckets matched against fellowship field restrictions. */
  fields: string[];
  /**
   * Opt-in restriction groups the user belongs to.
   * Subset of ["Women", "Equity"].
   */
  eligible_restrictions: string[];
  /**
   * Opt-in: may this member's fellowship eligibility be shown to their labs?
   * Default false — a lab fellowship names only members who consent, never who was
   * ineligible, so citizenship/stage can't be inferred (D-11).
   */
  lab_visible?: boolean;
  /**
   * Year the doctorate was conferred. The only input for awards that limit how
   * long ago that was ("within 24 months of the PhD"); such a limit is enforced
   * only when both it and this are known. Asked of postdocs only.
   */
  phd_completed_year?: number;
  /** Pre-existing key — never dropped; set only by other code paths. */
  career_stage?: string;
};

/**
 * One named grouping of a profile's research areas (interest-clusters feature).
 * `id` is a stable slug — never regenerated on rename, only assigned when a
 * cluster is first created (mirrors the backend's `make_cluster_id`).
 */
export type ClusterGroup = {
  id: string;
  label: string;
  areas: string[];
};

/** One profile edit made from a person's yes to one of Mylo's questions. */
export type AmbientProvenance = {
  field: string;
  value: string;
  suggestion: string | number;
  confirmed_on: string;
  surface: string;
  provenance: "stated";
};

/** The contract-shaped research interests stored on a profile. */
export type ResearchInterests = {
  version: number;
  areas: string[];
  statement?: string;
  keywords?: string[];
  skills?: string[];
  /** Ambient Plan 05's contract fields: filled only by the person, or by a yes
   * they gave to one of Mylo's questions (Plan 08). */
  learning_goals?: string[];
  preferences?: string[];
  trajectory?: { direction?: string };
  /** Where fields came from. `ambient` lists each edit made from a yes to one
   * of Mylo's questions — the field, the value, the day, where it was answered. */
  sources?: Record<string, unknown> & { ambient?: AmbientProvenance[] };
  /** Fellowship eligibility block — optional until the user completes step 4. */
  eligibility?: ProfileEligibility;
  /** Research-interest clusters derived from the profile's areas (interest-
   * clusters feature) — absent on a single/no-cluster profile. */
  clusters?: ClusterGroup[];
};

/**
 * Input to `proposeClusters` (`POST /api/auth/intake/clusters/`). Two modes on
 * one shape: **propose** (`areas` [+ `keywords`/`statement`]) groups areas into
 * named clusters; **sort** (`clusters` + `unsorted`) routes new areas into the
 * given clusters, preserving their ids. The caller picks a mode by which fields
 * it populates — the backend branches on `clusters && unsorted` both present.
 */
export type ProposeClustersInput = {
  /** Optional so the sort mode (`clusters` + `unsorted`, no full `areas` list)
   * type-checks — the propose mode is the one that populates this. */
  areas?: string[];
  keywords?: string[];
  statement?: string;
  clusters?: ClusterGroup[];
  unsorted?: string[];
};

/**
 * Input to `composeClusters` (the "instruct" mode of the clusters endpoint):
 * a free-text `instruction` plus the caller's *current* profile as context so
 * Mylo refines rather than blindly replaces (a persisting theme keeps its id).
 * Unlike propose/sort, this can invent concrete sub-topics — so the response's
 * `areas` is a widened union the returned clusters partition.
 */
export type ComposeClustersInput = {
  instruction: string;
  clusters?: ClusterGroup[];
  areas?: string[];
  keywords?: string[];
  statement?: string;
  watch_topics?: string[];
};

/** The response shape for `proposeClusters` and `composeClusters`. `areas` is
 * the union the clusters partition — unchanged for propose/sort, widened (with
 * invented sub-topics) for compose. */
export type ProposeClustersResult = {
  clusters: ClusterGroup[];
  areas: string[];
  watch_topics: string[];
  source: string;
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
  /**
   * How often Mylo messages you **on Discord**. The nightly run scores you and
   * writes your report every day whatever this says, and the web app shows both
   * every day — cadence asks not to be interrupted, not for Mylo to stop.
   */
  cadence: WatchCadence;
  /** IANA zone the send hour is read in. */
  timezone: string;
  /** Local hour (0–23) the Discord push targets. */
  send_hour_local: number;
  /** Weekly cadence only: allow one DM between Mondays for a moved deadline. */
  urgent_alerts: boolean;
  /** Days of slack you want between a milestone and a deadline to call it a fit. */
  deadline_buffer_days: number;
  /** Fewest days you consider enough to write a full paper. */
  min_paper_window_days: number;
};

/** A lab's shared watch row. Its send hour and zone live on the lab itself. */
export type LabWatchPreference = {
  topics: string[];
  categories: string[];
  cadence: WatchCadence;
  deadline_buffer_days: number;
  min_paper_window_days: number;
};

/** The four areas the post-onboarding live match can run, in report order. */
export type OnboardingMatchArea =
  | "papers"
  | "grants"
  | "fellowships"
  | "conferences";

/** One matched item previewed in the live-match table. */
export type OnboardingMatchSample = {
  title: string;
  /** read / skim / file / skip — see `Verdict` in `lib/portal/types`. */
  verdict: "read" | "skim" | "file" | "skip" | null;
  /** Its place in the theme that surfaced it. */
  position: number | null;
};

/** The result of matching one area over the existing corpus for the caller. */
export type OnboardingMatchResult = {
  area: OnboardingMatchArea;
  status: string;
  /** How many items were surfaced for this area. */
  matched: number;
  /** How many of those got a genuine language-model score (vs. deterministic). */
  llm: number;
  fallback: number;
  /**
   * Papers only: true when the latest batch was too thin, so a background scan of
   * the user's watch topics is running and fresh results will arrive shortly.
   */
  scanning: boolean;
  sample: OnboardingMatchSample[];
};

/** Person-global profile basics captured in onboarding (the role; the
 *  institution is derived from the verified email, never sent). */
export type ProfileBasics = {
  academic_title?: string;
};
