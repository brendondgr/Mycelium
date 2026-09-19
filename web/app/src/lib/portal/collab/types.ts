/**
 * Collaboration matching (the collaboration-network plan series).
 *
 * Plan CN-03: what a funding call asks a team to bring (its requirement
 * slots), and which of it the reader or their own lab already covers.
 */

/** What a slot asks for. A `role` is a kind of partner, not expertise — it is
 * shown and never matched against anyone. */
export type SlotFacet = "problem" | "method" | "data" | "role";

export type TeamFitSlot = {
  text: string;
  facet: SlotFacet;
  /** The call says a team must include it (as opposed to being about it). */
  required: boolean;
  /** "you" on a reader's own card, "lab" when lab-mates' profiles cover it,
   * null for a gap (always null for a role). */
  covered_by: "you" | "lab" | null;
  /** Lab-mates whose stated profile covers it. Names resolve live. */
  people: { username: string; name: string }[];
  /** The holder's own wording that matched. */
  matched: string;
};

/** Stored with each grant at scoring time (`signals["team_fit"]`). */
export type TeamFit = {
  covered: number;
  /** Slots that can be matched (roles are not counted). */
  total: number;
  gaps: string[];
  roles: string[];
  slots: TeamFitSlot[];
};

export type SlotFeedbackKind = "not_a_requirement" | "we_cover_this" | "missed_one";

/** Who may find a person (plan CN-04). */
export type Audience = "institution" | "country" | "anywhere";
export type OpenTo = "co_authoring" | "grant_partner" | "data_sharing" | "mentoring";

/** `GET/PUT /api/collab/settings/` — the reader's own setting. */
export type CollaborationSetting = {
  open: boolean;
  audience: Audience;
  open_to: OpenTo[];
  /** ISO time the setting ends, while it is on. */
  expires_at: string | null;
  /** The account's email is verified (nothing can be turned on otherwise). */
  verified: boolean;
  /** From the verified email's domain, never from the typed affiliation. */
  institution: string;
  country: string;
  /** Empty when unverified; only "anywhere" for a personal address. */
  allowed_audiences: Audience[];
};

/** `GET /api/collab/preview/` — exactly what a seeker would see. */
export type CollaborationPreview = {
  name: string;
  institution: string;
  facets: Partial<
    Record<"problem" | "method" | "setting" | "area", { label: string; sources: string[] }[]>
  >;
};

/** The collaborator search (plan CN-05). */
export type Lane = "in_field" | "method_bridge" | "problem_bridge" | "resource";

export type QuerySlot = {
  facet: SlotFacet;
  text: string;
  required?: boolean;
  /** Shown on the chip when the need came from a team-fit line; never sent
   * as a filter — the lanes decide who is looked for. */
  covered_by?: "you" | "lab" | null;
};

export type SearchEntry =
  | { entry: "call"; content_id: string }
  | { entry: "project"; project_id: string }
  | { entry: "manual"; text: string };

/** One person found: a coarse pointer, never a profile. */
export type SearchHit = {
  username: string;
  name: string;
  institution: string;
  lane: Lane;
  /** The need it answers. */
  slot: string;
  facet: string;
  /** Their own words for what matched. */
  matched: string;
  tier: "declared" | "demonstrated";
  /** Mylo's one line; "" when the model was unavailable. */
  reason: string;
};

export type SearchResponse = {
  slots: QuerySlot[];
  lanes: Partial<Record<Lane, SearchHit[]>>;
  groups: { fills_a_gap: SearchHit[]; shares_expertise: SearchHit[] };
  explained: boolean;
  search_id: number;
};

export type SearchAvailability = {
  available: boolean;
  /** Why not, for a surface choosing what to show instead. */
  code: "" | "not_enabled" | "unverified" | "paid_plan" | "daily_limit" | "refused";
  /** The same, in words. */
  reason: string;
  max_scope: Audience | null;
};

export type SavedPerson = {
  username: string;
  name: string;
  lane: Lane;
  slots: string[];
  saved_at: string;
};

/** "Assemble a team" (plan CN-07): people who together cover the gaps. */
export type TeamMember = {
  username: string;
  name: string;
  institution: string;
  covers: { slot: string; facet: string; matched: string; tier: "declared" | "demonstrated" }[];
  /** Co-authorships between you and them, when three or fewer. */
  distance: number | null;
};

export type TeamResponse = {
  slots: QuerySlot[];
  team: TeamMember[];
  /** Gaps nobody open to you covers. */
  uncovered: string[];
  search_id: number;
};

/** "Who can introduce me?" — only people open to you are ever named. */
export type Introduction = {
  hops: number | null;
  path: { username: string; name: string; institution: string }[] | null;
};
