/**
 * Workspace routing map. The authenticated portal uses real URLs under `/app`,
 * one segment per section, with project detail at `/app/projects/<id>`. Keeping
 * the section→route table (and the inverse pathname parsers) in one place lets
 * navigation, the sidebar, and the mobile tabs stay in sync with the URL.
 */

export type SectionKey =
  | "overview"
  | "profile"
  | "daily"
  | "papers"
  | "opportunities"
  | "fellowships"
  | "conferences"
  | "deadlines"
  | "projects"
  | "labs"
  | "members"
  | "reports"
  | "suggested";

/** Canonical route for each section. */
export const SECTION_ROUTES: Record<SectionKey, string> = {
  overview: "/app/overview",
  profile: "/app/profile",
  daily: "/app/daily",
  papers: "/app/research-papers",
  opportunities: "/app/grants",
  fellowships: "/app/fellowships",
  conferences: "/app/conferences",
  deadlines: "/app/deadlines",
  projects: "/app/projects",
  labs: "/app/labs",
  members: "/app/members",
  reports: "/app/reports",
  suggested: "/app/suggested",
};

/** Route for a single project's detail view. */
export function projectRoute(id: string): string {
  return `/app/projects/${id}`;
}

/**
 * Which section a pathname belongs to. Falls back to "overview" for `/app`
 * itself and anything unrecognised, so the sidebar always highlights a tab.
 */
export function sectionFromPathname(pathname: string): SectionKey {
  // Longest-prefix wins; "projects" covers both the list and detail routes.
  const keys: SectionKey[] = [
    "profile",
    "daily",
    "papers",
    "opportunities",
    "fellowships",
    "conferences",
    "deadlines",
    "projects",
    "labs",
    "members",
    "reports",
    "suggested",
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
