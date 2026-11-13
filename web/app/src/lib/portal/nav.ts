/**
 * What each workspace scope can navigate to.
 *
 * The sidebar and the mobile sheet are genuinely different components — a rail
 * and a column make no sense on a phone, and a sheet makes none on a desktop —
 * but they must never disagree about which sections a scope offers. So the
 * answer lives here once and both render it.
 *
 * A department works like a lab: it has the same four research feeds — Papers,
 * Grants, Fellowships, Conferences — read from
 * `/api/departments/<id>/recommendations/`, which is the lab's feed over the
 * department's own profile. Beside them it keeps one page a lab does not have,
 * **Opportunities**: the calls only a department can take on
 * (`tools/delivery/dept_level.py`).
 */

import type { SectionKey } from "@/lib/portal/routes";
import { FEATURE, type MyDepartment, type MyLab } from "@/lib/portal/types";
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
  | "account"
  | "settings";

export type NavGroup = { label: string; items: NavItem[] };

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
  const { scope, isAdmin, hasFeature } = ctx;

  const common: NavItem[] = [
    { key: "saves", label: "Saves", icon: "saves" },
    { key: "reminders", label: "Reminders", icon: "reminders" },
  ];

  // A lab or a department is on its own plan, so its members always get its
  // feeds; the personal feeds are gated on the personal plan.
  const inLab = scope.kind === "lab" || scope.kind === "department";
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

  // One Settings entry at the foot, for everyone. It opens the active
  // workspace's context in the Settings area, where every page the reader may
  // open is listed — so no settings page is a workspace entry any more.
  const settings: NavGroup = {
    label: "Settings",
    items: [{ key: "settings", label: "Settings", icon: "settings" }],
  };

  if (scope.kind === "department") {
    groups.push({
      label: "Workspace",
      items: [
        { key: "overview", label: "Overview", icon: "overview" },
        { key: "deptOpportunities", label: "Opportunities", icon: "grants" },
        // One directory: the department's labs, then its people.
        { key: "members", label: "Members", icon: "members" },
        ...common,
      ],
    });
    // The lab's four feeds over the department's own profile; Opportunities
    // stays its own page in the Workspace group above.
    groups.push({ label: "Research", items: [...feeds, projects] });
    groups.push(settings);
    return groups;
  }

  if (scope.kind === "lab") {
    groups.push({
      label: "Workspace",
      items: [
        { key: "overview", label: "Overview", icon: "overview" },
        { key: "members", label: "Members", icon: "members" },
        ...common,
      ],
    });
    groups.push({ label: "Research", items: [...feeds, projects] });
    groups.push(settings);
    return groups;
  }

  groups.push({
    label: "Workspace",
    items: [{ key: "overview", label: "Overview", icon: "overview" }, ...common],
  });
  groups.push({ label: "Research", items: [...feeds, projects] });
  if (isAdmin) {
    groups.push({
      label: "Admin",
      items: [{ key: "admin", label: "Admin dashboard", icon: "admin" }],
    });
  }
  groups.push(settings);
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
  // Your own settings pages and the Settings area belong to no workspace: the
  // area decides from its own path what the reader may open.
  "account",
  "profile",
  "mylo",
  "settings",
];

/**
 * Whether a section may be shown in this scope. This is what stops a scope
 * rendering a section that would answer for the wrong owner: every feed section
 * falls back to the *personal* feed when the workspace has no org, so a section
 * reached by a stale link must be checked against what the scope offers.
 *
 * It is a navigation guard, not a permission boundary — the API enforces access.
 */
export function sectionAllowed(ctx: NavContext, section: SectionKey): boolean {
  if (ALWAYS_ALLOWED.includes(section)) {
    return true;
  }
  return sectionsFor(ctx).has(section);
}
