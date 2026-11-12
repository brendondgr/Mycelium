/**
 * What each workspace scope can navigate to.
 *
 * The sidebar and the mobile sheet are genuinely different components — a rail
 * and a column make no sense on a phone, and a sheet makes none on a desktop —
 * but they must never disagree about which sections a scope offers. So the
 * answer lives here once and both render it.
 *
 * The department case is the reason this is a model rather than a pair of JSX
 * branches. A department has **no research feeds**: every feed route scopes on
 * `?lab=`, so Papers / Grants / Fellowships / Conferences are absent from a
 * department's navigation rather than present and permanently empty — an entry
 * that always shows nothing teaches people the product is broken. What it has
 * instead is one **Opportunities** page: the calls only a department can take on
 * (`apps/content/dept_level.py`), scored for it only while its announcements are
 * on.
 */

import type { SectionKey } from "@/lib/portal/routes";
import {
  FEATURE,
  type LabMember,
  type LabRole,
  type MyDepartment,
  type MyLab,
} from "@/lib/portal/types";
import type { WorkspaceScope } from "@/lib/portal/workspace";

export type NavItem = {
  key: SectionKey;
  label: string;
  /** Which icon to draw. Resolved by the renderer, so this stays JSX-free. */
  icon: NavIcon;
};

export type NavIcon =
  | "overview"
  | "profile"
  | "members"
  | "labs"
  | "saves"
  | "reminders"
  | "papers"
  | "grants"
  | "fellowships"
  | "conferences"
  | "projects"
  | "admin"
  | "mylo"
  | "account";

export type NavGroup = { label: string; items: NavItem[] };

/** A member with owner/admin/PI rights may edit the lab configuration. */
export function canManageLab(lab: Pick<MyLab, "is_lead" | "role">): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * Lab roles ranked, mirroring ``apps.accounts.permissions.LAB_ROLE_RANK``.
 *
 * The server is the authority; this exists so the UI can hide a control it
 * knows will be refused rather than offer it and show a 403. Keep the two in
 * step — a drift here is a button that lies, not a security hole.
 */
export const LAB_ROLE_RANK: Record<LabRole, number> = {
  owner: 3,
  admin: 2,
  member: 1,
  viewer: 0,
};

/**
 * A membership's rank: its role, raised to admin for a lead PI.
 *
 * Mirrors ``apps.accounts.permissions.membership_rank``. A lead PI holds every
 * right an admin does — grants the roles below admin and acts on members and
 * viewers — without outranking an admin.
 */
export function labRank(m: Pick<MyLab, "is_lead" | "role">): number {
  const rank = LAB_ROLE_RANK[m.role] ?? 0;
  return m.is_lead ? Math.max(rank, LAB_ROLE_RANK.admin) : rank;
}

/** Whether the caller may hand out `role` — strictly below their own. */
export function canGrantLabRole(
  lab: Pick<MyLab, "is_lead" | "role">,
  role: LabRole,
): boolean {
  return labRank(lab) > LAB_ROLE_RANK[role];
}

/** The roles the caller may assign, highest first. */
export function grantableLabRoles(
  lab: Pick<MyLab, "is_lead" | "role">,
): LabRole[] {
  return (["admin", "member", "viewer"] as LabRole[]).filter((role) =>
    canGrantLabRole(lab, role),
  );
}

/** Whether the caller may act on this member at all — re-role or remove them. */
export function outranksLabMember(
  lab: Pick<MyLab, "is_lead" | "role">,
  member: Pick<LabMember, "role"> & { is_lead?: boolean },
): boolean {
  return labRank(lab) > labRank({ role: member.role, is_lead: Boolean(member.is_lead) });
}

/**
 * Department roles ranked, mirroring ``apps.accounts.permissions.DEPT_ROLE_RANK``.
 *
 * The head is the department's owner; anyone else's role tops out at admin.
 * Like the lab table, this only decides which controls to draw.
 */
export const DEPT_ROLE_RANK: Record<LabRole, number> = LAB_ROLE_RANK;

/** The caller's rank in a department: 3 for the head, else their direct role. */
export function deptRank(dept: Pick<MyDepartment, "is_owner" | "role">): number {
  if (dept.is_owner) return DEPT_ROLE_RANK.owner;
  const rank = DEPT_ROLE_RANK[dept.role as LabRole] ?? -1;
  return Math.min(rank, DEPT_ROLE_RANK.admin);
}

/** The department roles the caller may assign, highest first (never owner). */
export function grantableDeptRoles(
  dept: Pick<MyDepartment, "is_owner" | "role">,
): LabRole[] {
  const mine = deptRank(dept);
  return (["admin", "member", "viewer"] as LabRole[]).filter(
    (role) => mine > DEPT_ROLE_RANK[role],
  );
}

/** Whether the caller may re-role or remove a direct department member. */
export function outranksDeptMember(
  dept: Pick<MyDepartment, "is_owner" | "role">,
  member: { role: LabRole; is_head?: boolean },
): boolean {
  const theirs = member.is_head
    ? DEPT_ROLE_RANK.owner
    : Math.min(DEPT_ROLE_RANK[member.role] ?? 0, DEPT_ROLE_RANK.admin);
  return deptRank(dept) > theirs;
}

/** Whether the caller may administer a department. */
export function canManageDepartment(
  dept: Pick<MyDepartment, "can_manage" | "is_owner">,
): boolean {
  return Boolean(dept.can_manage || dept.is_owner);
}

/** What the caller's rights and plan allow, passed in rather than read here. */
export type NavContext = {
  scope: WorkspaceScope;
  currentLab: MyLab | null;
  currentDepartment: MyDepartment | null;
  isAdmin: boolean;
  /** Whether a personal-plan feature is entitled. Labs are always allowed. */
  hasFeature: (feature: string) => boolean;
};

const FEED_ITEMS: Record<string, NavItem> = {
  papers: { key: "papers", label: "Research Papers", icon: "papers" },
  grants: { key: "opportunities", label: "Grants", icon: "grants" },
  fellowships: { key: "fellowships", label: "Fellowships", icon: "fellowships" },
  conferences: { key: "conferences", label: "Conferences", icon: "conferences" },
};

/**
 * The navigation for a scope, as ordered groups. `null` groups are filtered, so
 * a caller can render this straight through without re-deciding anything.
 */
export function navGroupsFor(ctx: NavContext): NavGroup[] {
  const { scope, currentLab, currentDepartment, isAdmin, hasFeature } = ctx;

  const common: NavItem[] = [
    { key: "saves", label: "Saves", icon: "saves" },
    { key: "reminders", label: "Reminders", icon: "reminders" },
  ];

  // A lab is on its own paid plan, so its members always get the lab feeds; the
  // personal feeds are gated on the personal plan.
  const inLab = scope.kind === "lab";
  const feeds: NavItem[] = [
    FEED_ITEMS.papers,
    ...(inLab || hasFeature(FEATURE.GRANT_ALERTS) ? [FEED_ITEMS.grants] : []),
    ...(inLab || hasFeature(FEATURE.FELLOWSHIP_MATCHING) ? [FEED_ITEMS.fellowships] : []),
    ...(inLab || hasFeature(FEATURE.CONFERENCE_ALERTS) ? [FEED_ITEMS.conferences] : []),
  ];
  const projects: NavItem = {
    key: "projects",
    label: "Projects",
    icon: "projects",
  };

  const groups: NavGroup[] = [];

  if (scope.kind === "department") {
    const manage = currentDepartment
      ? canManageDepartment(currentDepartment)
      : false;
    groups.push({
      label: "Workspace",
      items: [
        { key: "overview", label: "Overview", icon: "overview" },
        { key: "deptOpportunities", label: "Opportunities", icon: "grants" },
        { key: "labs", label: "Labs", icon: "labs" },
        { key: "members", label: "Members", icon: "members" },
        ...(manage
          ? [
              {
                key: "profile" as SectionKey,
                label: "Department settings",
                icon: "profile" as NavIcon,
              },
            ]
          : []),
        ...common,
      ],
    });
    // Projects only. See the module docstring for why there are no feeds.
    groups.push({ label: "Research", items: [projects] });
    if (manage) {
      groups.push({
        label: "Account",
        items: [{ key: "account", label: "Account", icon: "account" }],
      });
    }
    return groups;
  }

  if (scope.kind === "lab") {
    const manage = currentLab ? canManageLab(currentLab) : false;
    groups.push({
      label: "Workspace",
      items: [
        { key: "overview", label: "Overview", icon: "overview" },
        { key: "members", label: "Members", icon: "members" },
        ...(manage
          ? [
              {
                key: "profile" as SectionKey,
                label: "Lab settings",
                icon: "profile" as NavIcon,
              },
            ]
          : []),
        ...common,
      ],
    });
    groups.push({ label: "Research", items: [...feeds, projects] });
    // A lab's plan is its managers' business; members don't get the entry.
    if (manage) {
      groups.push({
        label: "Account",
        items: [{ key: "account", label: "Account", icon: "account" }],
      });
    }
    return groups;
  }

  groups.push({
    label: "Workspace",
    items: [
      { key: "overview", label: "Overview", icon: "overview" },
      { key: "profile", label: "Profile", icon: "profile" },
      // What Mylo understood from your conversations: personal, always.
      { key: "mylo", label: "Mylo & you", icon: "mylo" },
      ...common,
    ],
  });
  groups.push({ label: "Research", items: [...feeds, projects] });
  if (isAdmin) {
    groups.push({
      label: "Admin",
      items: [{ key: "admin", label: "Admin dashboard", icon: "admin" }],
    });
  }
  groups.push({
    label: "Account",
    items: [{ key: "account", label: "Account", icon: "account" }],
  });
  return groups;
}

/** Every section the scope offers — what the scope guard checks against. */
export function sectionsFor(ctx: NavContext): Set<SectionKey> {
  const keys = navGroupsFor(ctx).flatMap((group) =>
    group.items.map((item) => item.key),
  );
  return new Set(keys);
}

/**
 * Sections that are always reachable regardless of scope, so the guard never
 * bounces someone off a page the navigation simply doesn't list.
 *
 * `search` and `reports` have no nav entry but are opened directly; `labs` is
 * how you browse and create, so it must stay reachable from a lab scope too;
 * project detail lives under `projects`.
 */
const ALWAYS_ALLOWED: SectionKey[] = [
  "search",
  "reports",
  "labs",
  "daily",
  "suggested",
  "account",
];

/**
 * Whether a section may be shown in this scope. This is what stops a department
 * scope rendering *personal* feed results: every feed section falls back to the
 * personal feed when `currentLab` is null, so without a guard
 * `/app/grants?ws=<dept>` would quietly show the reader their own grants.
 *
 * It is a navigation guard, not a permission boundary — the API enforces access.
 */
export function sectionAllowed(ctx: NavContext, section: SectionKey): boolean {
  if (ALWAYS_ALLOWED.includes(section)) {
    return true;
  }
  return sectionsFor(ctx).has(section);
}
