/**
 * Workspace routing map. The authenticated portal uses real URLs under `/app`,
 * one segment per section, with project detail at `/app/projects/<id>`. Keeping
 * the section→route table (and the inverse pathname parsers) in one place lets
 * navigation, the sidebar, and the mobile tabs stay in sync with the URL.
 */

import { PERSONAL_SLUG } from "@/lib/portal/types";

export type SectionKey =
  | "overview"
  | "profile"
  | "account"
  | "search"
  | "daily"
  | "papers"
  | "opportunities"
  | "fellowships"
  | "conferences"
  | "saves"
  | "reminders"
  | "projects"
  | "labs"
  | "members"
  | "reports"
  | "suggested"
  | "mylo"
  | "admin";

/** Canonical route for each section. */
export const SECTION_ROUTES: Record<SectionKey, string> = {
  overview: "/app/overview",
  profile: "/app/profile",
  account: "/app/account",
  search: "/app/search",
  daily: "/app/daily",
  papers: "/app/research-papers",
  opportunities: "/app/grants",
  fellowships: "/app/fellowships",
  conferences: "/app/conferences",
  saves: "/app/saves",
  reminders: "/app/reminders",
  projects: "/app/projects",
  labs: "/app/labs",
  members: "/app/members",
  reports: "/app/reports",
  suggested: "/app/suggested",
  mylo: "/app/mylo-and-you",
  admin: "/app/admin",
};

/** Route for a single project's detail view. */
export function projectRoute(id: string): string {
  return `/app/projects/${id}`;
}

/**
 * The query parameter carrying the active workspace.
 *
 * Scope used to live only in `localStorage`, which made a URL dishonest: a link
 * pasted to a labmate opened in *their* last workspace, not the one being
 * discussed, and two tabs could not hold two workspaces. Putting it in the URL
 * fixes both.
 *
 * It is a query parameter rather than a path segment deliberately. A path change
 * would touch every entry in `SECTION_ROUTES`, every `goToSection` call, the
 * nginx location blocks and every emailed deep link, for the same benefit.
 */
export const SCOPE_PARAM = "ws";

/**
 * A section route carrying a workspace. The personal scope is the default and
 * writes no parameter, so personal URLs stay exactly as they are today.
 */
export function routeWithScope(route: string, scopeKey: string | null): string {
  if (!scopeKey || scopeKey === PERSONAL_SLUG) {
    return route;
  }
  return `${route}?${SCOPE_PARAM}=${encodeURIComponent(scopeKey)}`;
}

/**
 * Which section a pathname belongs to. Falls back to "overview" for `/app`
 * itself and anything unrecognised, so the sidebar always highlights a tab.
 */
export function sectionFromPathname(pathname: string): SectionKey {
  // Longest-prefix wins; "projects" covers both the list and detail routes.
  const keys: SectionKey[] = [
    "profile",
    "account",
    "search",
    "daily",
    "papers",
    "opportunities",
    "fellowships",
    "conferences",
    "saves",
    "reminders",
    "projects",
    "labs",
    "members",
    "reports",
    "suggested",
    "mylo",
    "admin",
    "overview",
  ];
  for (const key of keys) {
    const base = SECTION_ROUTES[key];
    if (pathname === base || pathname.startsWith(`${base}/`)) {
      return key;
    }
  }
  return "overview";
}

/**
 * The project id from a `/app/projects/<id>` pathname, or null on the list view
 * (or any non-project route).
 */
export function projectIdFromPathname(pathname: string): string | null {
  const base = SECTION_ROUTES.projects;
  if (!pathname.startsWith(`${base}/`)) {
    return null;
  }
  const rest = pathname.slice(base.length + 1);
  const id = rest.split("/")[0];
  return id ? decodeURIComponent(id) : null;
}
