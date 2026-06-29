"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import { useMyLabs, useProjects } from "@/lib/portal/hooks";
import { useTheme, type Theme } from "@/lib/portal/theme";
import { ALL_LABS_SLUG, type MyLab, type Project } from "@/lib/portal/types";

export type SectionKey =
  | "overview"
  | "daily"
  | "opportunities"
  | "deadlines"
  | "projects"
  | "goals"
  | "members"
  | "reports";

/** Minimal identity the dashboard renders (name/initials for the header + greeting). */
export type PortalUser = {
  username: string;
  email: string;
  name: string;
  initials: string;
  isSuperuser: boolean;
};

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
  const [section, setSection] = useState<SectionKey>("overview");
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [projectsExpanded, setProjectsExpanded] = useState(false);
  const [labScope, setLabScopeState] = useState<string>(ALL_LABS_SLUG);

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
    const count = labs.length;
    if (count === 0) {
      return "your workspace";
    }
    return `all ${count} of your lab${count === 1 ? "" : "s"}`;
  }, [currentLab, labs.length]);

  const goToSection = useCallback((next: SectionKey) => {
    setSection(next);
    setActiveProjectId(null);
  }, []);

  const openProjectsList = useCallback(() => {
    setSection("projects");
    setActiveProjectId(null);
    setProjectsExpanded(true);
  }, []);

  const openProject = useCallback((id: string) => {
    setSection("projects");
    setActiveProjectId(id);
    setProjectsExpanded(true);
  }, []);

  const toggleProjectsExpanded = useCallback(
    () => setProjectsExpanded((open) => !open),
    [],
  );

  const setLabScope = useCallback((slug: string) => {
    setLabScopeState(slug);
    // Leaving a project open under a different scope can show a stale detail.
    setActiveProjectId(null);
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
