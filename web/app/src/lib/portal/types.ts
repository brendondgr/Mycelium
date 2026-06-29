/** Shapes returned by the workspace read endpoints (see docs/api-contract.md). */

export type LabRole = "owner" | "admin" | "member" | "viewer";

/** One of the signed-in user's lab memberships — powers the workspace switcher. */
export type MyLab = {
  slug: string;
  name: string;
  role: LabRole;
  is_lead: boolean;
  department: string | null;
};

/** A lab member row (also used for project members). */
export type LabMember = {
  username: string;
  name: string;
  initials: string;
  email: string;
  role: LabRole;
  is_lead: boolean;
};

export type ProjectMember = {
  username: string;
  name: string;
  initials: string;
};

export type ProjectScope = "user" | "lab" | "department";

export type Project = {
  id: string;
  name: string;
  scope: ProjectScope;
  scope_name: string;
  goals: Record<string, unknown>;
  /** Optional display hints read from `goals`; null when the author set none. */
  status: string | null;
  progress: number | null;
  member_count: number;
  members: ProjectMember[];
  updated_at: string;
};

/** Synthetic "All labs" scope the switcher prepends client-side. */
export const ALL_LABS_SLUG = "__all__";
