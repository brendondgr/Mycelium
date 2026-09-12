"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { useMyDepartments, useMyLabs, useProjects } from "@/lib/portal/hooks";
import {
  SCOPE_PARAM,
  SECTION_ROUTES,
  projectIdFromPathname,
  projectRoute,
  routeWithScope,
  sectionFromPathname,
} from "@/lib/portal/routes";
import { useTheme, type Theme } from "@/lib/portal/theme";
import {
  buildWorkspaces,
  labSlugForScope,
  scopeFromKey,
  scopeKey,
  type Workspace,
  type WorkspaceScope,
} from "@/lib/portal/workspace";
import {
  PERSONAL_SLUG,
  type MyDepartment,
  type MyLab,
  type Project,
} from "@/lib/portal/types";

export { roleLabel } from "@/lib/portal/workspace";

export type { SectionKey } from "@/lib/portal/routes";
import type { SectionKey } from "@/lib/portal/routes";

/** Minimal identity the dashboard renders (name/initials for the header + greeting). */
export type PortalUser = {
  username: string;
  email: string;
  name: string;
  initials: string;
  isStaff: boolean;
  isSuperuser: boolean;
  /**
   * Whether the account is activated. Verifying the address is what activates
   * it, and until then the backend refuses to create a lab or department or to
   * send an invitation — so the UI shows the lock up front rather than letting
   * someone fill in a form that will 403 on save.
   */
  isVerified: boolean;
};

/** Whether a user may see the admin dashboard (staff or superuser). */
export function isPlatformAdmin(user: Pick<PortalUser, "isStaff" | "isSuperuser">): boolean {
  return user.isStaff || user.isSuperuser;
}

export type PortalContextValue = {
  user: PortalUser;

  // Navigation
  section: SectionKey;
  activeProjectId: string | null;
  goToSection: (section: SectionKey) => void;
  openProjectsList: () => void;
  openProject: (id: string) => void;
  projectsExpanded: boolean;
  toggleProjectsExpanded: () => void;

  // Workspace scope (the switcher). `scope` is the authority; the lab-shaped
  // fields below are derived from it and kept because most of the app only ever
  // asks "am I in a lab, and which one?".
  scope: WorkspaceScope;
  setScope: (scope: WorkspaceScope) => void;
  workspaces: Workspace[];
  currentWorkspace: Workspace;
  workspacesLoading: boolean;

  labs: MyLab[];
  labsLoading: boolean;
  departments: MyDepartment[];
  currentDepartment: MyDepartment | null;

  /** @deprecated Read `scope` instead — this is `scopeKey(scope)`. */
  labScope: string;
  /** @deprecated Call `setScope` instead. */
  setLabScope: (slug: string) => void;
  currentLab: MyLab | null;
  scopeLabel: string;

  // Projects (scoped to labScope)
  projects: Project[];
  projectsLoading: boolean;
  projectsError: boolean;

  // Theme
  theme: Theme;
  toggleTheme: () => void;
};

const PortalContext = createContext<PortalContextValue | null>(null);

/** Where the active workspace scope is remembered across reloads / deep links. */
const LAB_SCOPE_KEY = "mycelium_lab_scope";

export function usePortal(): PortalContextValue {
  const value = useContext(PortalContext);
  if (!value) {
    throw new Error("usePortal must be used within <PortalProvider>");
  }
  return value;
}

export function PortalProvider({
  user,
  children,
}: {
  user: PortalUser;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  // Navigation is derived from the URL — the route is the source of truth.
  const section = sectionFromPathname(pathname);
  const activeProjectId = projectIdFromPathname(pathname);

  const [projectsExpanded, setProjectsExpanded] = useState<boolean>(() =>
    pathname.startsWith(SECTION_ROUTES.projects),
  );
  // The URL is the authority on scope. `localStorage` is demoted to a *default*
  // for a bare `/app/...` entry with no parameter — which is what makes a pasted
  // link honest while a refresh still puts you back where you were.
  const urlScopeKey = searchParams.get(SCOPE_PARAM);
  const [storedScopeKey, setStoredScopeKey] = useState<string | null>(null);

  // localStorage isn't readable during SSR, so the stored default is hydrated
  // once after mount. Until then the URL alone decides, which is correct.
  useEffect(() => {
    const stored = window.localStorage.getItem(LAB_SCOPE_KEY);
    if (stored && stored !== PERSONAL_SLUG) {
      // Reading a browser-only store on mount: SSR can't see it, so hydrating the
      // restored scope here (once) is the intended pattern, not a cascading render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStoredScopeKey(stored);
    }
  }, []);

  // Explicit parameter wins; otherwise the remembered default; otherwise
  // personal. A key that survives neither check self-heals below.
  const scopeRequest = urlScopeKey ?? storedScopeKey ?? PERSONAL_SLUG;

  const { theme, toggleTheme } = useTheme();
  const labsQuery = useMyLabs();
  const departmentsQuery = useMyDepartments();

  const labs = useMemo(() => labsQuery.data ?? [], [labsQuery.data]);
  const departments = useMemo(
    () => departmentsQuery.data ?? [],
    [departmentsQuery.data],
  );

  // Resolving the request against real memberships is what makes an unknown key
  // harmless — a lab you left, a deleted department, a typo in a pasted URL.
  const scope = useMemo(
    () => scopeFromKey(scopeRequest, labs, departments),
    [scopeRequest, labs, departments],
  );

  const workspaces = useMemo(
    () => buildWorkspaces(labs, departments),
    [labs, departments],
  );

  const currentWorkspace = useMemo(
    () =>
      workspaces.find((entry) => entry.key === scopeKey(scope)) ??
      workspaces[0],
    [workspaces, scope],
  );

  // Projects are asked for by lab slug; a department scope has no lab, so it
  // gets the same unscoped list the personal space does.
  const projectsQuery = useProjects(labSlugForScope(scope) ?? PERSONAL_SLUG);
  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data],
  );

  const currentLab = useMemo(
    () =>
      scope.kind === "lab"
        ? (labs.find((lab) => lab.slug === scope.slug) ?? null)
        : null,
    [labs, scope],
  );

  const currentDepartment = useMemo(
    () =>
      scope.kind === "department"
        ? (departments.find((dept) => dept.id === scope.id) ?? null)
        : null,
    [departments, scope],
  );

  const scopeLabel = useMemo(() => {
    if (currentLab) {
      return currentLab.name;
    }
    if (currentDepartment) {
      return currentDepartment.name;
    }
    return "your personal workspace";
  }, [currentLab, currentDepartment]);

  // Every in-app navigation carries the active workspace, so the scope survives
  // a move between sections and the address bar never lies about where you are.
  const activeScopeKey = scopeKey(scope);

  const goToSection = useCallback(
    (next: SectionKey) => {
      router.push(routeWithScope(SECTION_ROUTES[next], activeScopeKey));
    },
    [router, activeScopeKey],
  );

  const openProjectsList = useCallback(() => {
    setProjectsExpanded(true);
    router.push(routeWithScope(SECTION_ROUTES.projects, activeScopeKey));
  }, [router, activeScopeKey]);

  const openProject = useCallback(
    (id: string) => {
      setProjectsExpanded(true);
      router.push(routeWithScope(projectRoute(id), activeScopeKey));
    },
    [router, activeScopeKey],
  );

  const toggleProjectsExpanded = useCallback(
    () => setProjectsExpanded((open) => !open),
    [],
  );

  /**
   * Switch workspace. Writes the scope into the URL (the authority) and into
   * `localStorage` (the default for a bare entry next time), then lands on the
   * overview — switching workspace should show you that workspace, not leave you
   * on a section that may not exist in it.
   */
  const setScope = useCallback(
    (next: WorkspaceScope) => {
      const key = scopeKey(next);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAB_SCOPE_KEY, key);
      }
      router.push(routeWithScope(SECTION_ROUTES.overview, key));
    },
    [router],
  );

  // Kept for the call sites that still speak in lab slugs. A key that is not a
  // lab resolves to personal, which is what those callers already expected.
  const setLabScope = useCallback(
    (slug: string) => setScope(scopeFromKey(slug, labs, departments)),
    [setScope, labs, departments],
  );

  const value: PortalContextValue = {
    user,
    section,
    activeProjectId,
    goToSection,
    openProjectsList,
    openProject,
    projectsExpanded,
    toggleProjectsExpanded,
    scope,
    setScope,
    workspaces,
    currentWorkspace,
    workspacesLoading: labsQuery.isLoading || departmentsQuery.isLoading,
    labs,
    labsLoading: labsQuery.isLoading,
    departments,
    currentDepartment,
    labScope: scopeKey(scope),
    setLabScope,
    currentLab,
    scopeLabel,
    projects,
    projectsLoading: projectsQuery.isLoading,
    projectsError: projectsQuery.isError,
    theme,
    toggleTheme,
  };

  return (
    <PortalContext.Provider value={value}>{children}</PortalContext.Provider>
  );
}
