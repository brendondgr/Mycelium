"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import { useMyLabs, useProjects } from "@/lib/portal/hooks";
import {
  SECTION_ROUTES,
  projectIdFromPathname,
  projectRoute,
  sectionFromPathname,
} from "@/lib/portal/routes";
import { useTheme, type Theme } from "@/lib/portal/theme";
import { PERSONAL_SLUG, type MyLab, type Project } from "@/lib/portal/types";

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

  // Lab scope (workspace switcher)
  labs: MyLab[];
  labsLoading: boolean;
  labScope: string;
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

  // Navigation is derived from the URL — the route is the source of truth.
  const section = sectionFromPathname(pathname);
  const activeProjectId = projectIdFromPathname(pathname);

  const [projectsExpanded, setProjectsExpanded] = useState<boolean>(() =>
    pathname.startsWith(SECTION_ROUTES.projects),
  );
  const [labScope, setLabScopeState] = useState<string>(PERSONAL_SLUG);

  // Restore the last active workspace scope after mount so a refresh or a
  // deep-link stays in the lab (localStorage isn't available during SSR, so we
  // start on Personal and hydrate here — a stale/removed lab self-heals because
  // `currentLab` resolves to null and the UI falls back to Personal).
  useEffect(() => {
    const stored = window.localStorage.getItem(LAB_SCOPE_KEY);
    if (stored && stored !== PERSONAL_SLUG) {
      // Reading a browser-only store on mount: SSR can't see it, so hydrating the
      // restored scope here (once) is the intended pattern, not a cascading render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLabScopeState(stored);
    }
  }, []);

  const { theme, toggleTheme } = useTheme();
  const labsQuery = useMyLabs();
  const projectsQuery = useProjects(labScope);

  const labs = useMemo(() => labsQuery.data ?? [], [labsQuery.data]);
  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data],
  );

  const currentLab = useMemo(
    () => labs.find((lab) => lab.slug === labScope) ?? null,
    [labs, labScope],
  );

  const scopeLabel = useMemo(() => {
    if (currentLab) {
      return currentLab.name;
    }
    return "your personal workspace";
  }, [currentLab]);

  const goToSection = useCallback(
    (next: SectionKey) => {
      router.push(SECTION_ROUTES[next]);
    },
    [router],
  );

  const openProjectsList = useCallback(() => {
    setProjectsExpanded(true);
    router.push(SECTION_ROUTES.projects);
  }, [router]);

  const openProject = useCallback(
    (id: string) => {
      setProjectsExpanded(true);
      router.push(projectRoute(id));
    },
    [router],
  );

  const toggleProjectsExpanded = useCallback(
    () => setProjectsExpanded((open) => !open),
    [],
  );

  // The active workspace is remembered across reloads, so a refresh keeps you
  // in the same lab.
  const setLabScope = useCallback((slug: string) => {
    setLabScopeState(slug);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LAB_SCOPE_KEY, slug);
    }
  }, []);

  const value: PortalContextValue = {
    user,
    section,
    activeProjectId,
    goToSection,
    openProjectsList,
    openProject,
    projectsExpanded,
    toggleProjectsExpanded,
    labs,
    labsLoading: labsQuery.isLoading,
    labScope,
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
