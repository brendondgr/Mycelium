/**
 * What a "workspace" is in the portal.
 *
 * The switcher used to be a two-position slider between Personal and Lab, so
 * the active scope could be a bare string (a lab slug, or the sentinel
 * `PERSONAL_SLUG`). The backend has always had a third org kind — departments
 * own projects, hold a roster, and pay for seats — and a bare string cannot say
 * which kind a key belongs to.
 *
 * `WorkspaceScope` is a tagged union so it can. Passing a department id where a
 * lab slug is expected (`?lab=` on every feed route) becomes a type error rather
 * than a request that quietly returns the wrong rows.
 */

import type { MyDepartment, MyLab } from "@/lib/portal/types";
import { PERSONAL_SLUG } from "@/lib/portal/types";

export type WorkspaceKind = "personal" | "lab" | "department";

export type WorkspaceScope =
  | { kind: "personal" }
  | { kind: "lab"; slug: string }
  | { kind: "department"; id: string };

export const PERSONAL_SCOPE: WorkspaceScope = { kind: "personal" };

/** One row in the switcher — a lab, a department, or the personal space. */
export type Workspace = {
  kind: WorkspaceKind;
  /** Stable identity: the lab slug, the department id, or `PERSONAL_SLUG`. */
  key: string;
  name: string;
  /** Display role ("PI", "Owner", "Member", …); "You" for the personal space. */
  role: string;
  /** Secondary line — a lab's department, a department's institution. */
  sub: string;
  /** The lab behind this row, when it is one. */
  lab?: MyLab;
  /** The department behind this row, when it is one. */
  department?: MyDepartment;
};

/** Human label for a workspace kind, used in captions and pills. */
export const KIND_LABEL: Record<WorkspaceKind, string> = {
  personal: "Personal",
  lab: "Lab",
  department: "Department",
};

/* -------------------------------------------------------------------------- */
/* Scope ⇄ key                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The scope's stable key. Lab slugs and department ids share one namespace here;
 * a collision would need a lab slug identical to a department UUID, and
 * `scopeFromKey` resolves against the caller's actual memberships anyway.
 */
export function scopeKey(scope: WorkspaceScope): string {
  switch (scope.kind) {
    case "lab":
      return scope.slug;
    case "department":
      return scope.id;
    default:
      return PERSONAL_SLUG;
  }
}

/**
 * Resolve a key back into a scope, against what the caller is actually a member
 * of. An unknown key — a lab they left, a department that was deleted, a typo in
 * a pasted URL — resolves to personal rather than erroring, which is the
 * self-healing behaviour the portal already relied on.
 */
export function scopeFromKey(
  key: string | null | undefined,
  labs: MyLab[],
  departments: MyDepartment[],
): WorkspaceScope {
  if (!key || key === PERSONAL_SLUG) {
    return PERSONAL_SCOPE;
  }
  if (labs.some((lab) => lab.slug === key)) {
    return { kind: "lab", slug: key };
  }
  if (departments.some((dept) => dept.id === key)) {
    return { kind: "department", id: key };
  }
  return PERSONAL_SCOPE;
}

/** Whether two scopes point at the same workspace. */
export function sameScope(a: WorkspaceScope, b: WorkspaceScope): boolean {
  return scopeKey(a) === scopeKey(b) && a.kind === b.kind;
}

/**
 * The lab slug a request should be scoped to, or `undefined`. Personal *and*
 * department scopes both yield `undefined`: there is no department scoring
 * target, so there is no department-scoped feed to ask for.
 */
export function labSlugForScope(scope: WorkspaceScope): string | undefined {
  return scope.kind === "lab" ? scope.slug : undefined;
}

/* -------------------------------------------------------------------------- */
/* Building the switcher's list                                                */
/* -------------------------------------------------------------------------- */

/** Human label for a membership role (raw role + PI lead flag → display). */
export function roleLabel(lab: Pick<MyLab, "role" | "is_lead">): string {
  if (lab.is_lead) {
    return "PI";
  }
  switch (lab.role) {
    case "owner":
      return "Owner";
    case "admin":
      return "Admin";
    case "viewer":
      return "Viewer";
    default:
      return "Member";
  }
}

/** Title-case a raw department role string ("admin" → "Admin"). */
function departmentRoleLabel(dept: MyDepartment): string {
  if (dept.is_owner) {
    return "Owner";
  }
  const role = dept.role?.trim();
  if (!role) {
    return "Member";
  }
  return role.charAt(0).toUpperCase() + role.slice(1);
}

/**
 * The switcher's rows, in the order they are shown everywhere: personal first,
 * then departments, then labs. One ordering, so the rail, the sheet and the
 * palette cannot disagree about what comes first.
 */
export function buildWorkspaces(
  labs: MyLab[],
  departments: MyDepartment[],
  personalName = "Personal",
): Workspace[] {
  const personal: Workspace = {
    kind: "personal",
    key: PERSONAL_SLUG,
    name: personalName,
    role: "You",
    sub: "Your own research",
  };
  const deptRows: Workspace[] = departments.map((dept) => ({
    kind: "department",
    key: dept.id,
    name: dept.name,
    role: departmentRoleLabel(dept),
    sub: dept.institution || "Department",
    department: dept,
  }));
  const labRows: Workspace[] = labs.map((lab) => ({
    kind: "lab",
    key: lab.slug,
    name: lab.name,
    role: roleLabel(lab),
    sub: lab.department || "Independent lab",
    lab,
  }));
  return [personal, ...deptRows, ...labRows];
}

/* -------------------------------------------------------------------------- */
/* Display                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Words that carry no identity in an org name. Without this,
 * "Dept. of Scientific Computing" abbreviates to "DO" — a mark made entirely of
 * filler, which is worse than no mark.
 */
const FILLER = new Set([
  "of", "the", "and", "for", "at", "in",
  "dept", "department", "div", "division",
  "lab", "labs", "laboratory", "group", "center", "centre", "institute",
]);

/** A workspace's one-or-two letter mark, for the rail tile and menu rows. */
export function workspaceInitials(name: string): string {
  const words = name
    .split(/\s+/)
    .map((word) => word.replace(/[^A-Za-z0-9]/g, ""))
    .filter((word) => word.length > 0);
  const meaningful = words.filter((word) => !FILLER.has(word.toLowerCase()));
  const use = meaningful.length > 0 ? meaningful : words;
  if (use.length === 0) {
    return "?";
  }
  // A single surviving word ("PULSE Lab" → PULSE) gives two letters, so a mark
  // is never a lonely character.
  if (use.length === 1) {
    return use[0].slice(0, 2).toUpperCase();
  }
  return use
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

/**
 * A stable decorative hue per workspace, drawn from the eight cluster accents.
 * Those tokens are deliberately clear of the semantic green/gold/terracotta, so
 * a workspace mark can never read as a fit or urgency signal. Personal has no
 * hue — it uses the fixed brand panel.
 */
export function workspaceHue(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return `var(--cluster-${(hash % 8) + 1})`;
}
