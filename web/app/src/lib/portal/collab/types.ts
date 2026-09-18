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
