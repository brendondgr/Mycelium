"use client";

import {
  CalendarIcon,
  DocumentIcon,
  GridIcon,
  MembersIcon,
  ReportIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 px-3.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** The left workspace navigation (desktop). Mobile uses a separate tab strip. */
export function PortalSidebar() {
  const { section, goToSection } = usePortal();

  return (
    <aside className="sticky top-[61px] hidden max-h-[calc(100vh-61px)] w-[244px] shrink-0 self-start overflow-y-auto border-r border-[var(--divider)] px-3.5 pb-6 pt-[18px] lg:block">
      <GroupLabel>Workspace</GroupLabel>
      <nav className="mb-[18px] flex flex-col gap-0.5">
        <SidebarNavItem
          icon={<GridIcon size={18} />}
          label="Overview"
          active={section === "overview"}
          onClick={() => goToSection("overview")}
        />
        <SidebarNavItem
          icon={<TargetIcon size={18} />}
          label="Profile"
          active={section === "profile"}
          onClick={() => goToSection("profile")}
        />
      </nav>

      <GroupLabel>Research</GroupLabel>
      <nav className="mb-[18px] flex flex-col gap-0.5">
        <SidebarNavItem
          icon={<ReportIcon size={18} />}
          label="Daily Reports"
          active={section === "daily"}
          onClick={() => goToSection("daily")}
        />
        <SidebarNavItem
          icon={<SparkleIcon size={18} />}
          label="Opportunities"
          active={section === "opportunities"}
          onClick={() => goToSection("opportunities")}
        />
        <SidebarNavItem
          icon={<CalendarIcon size={18} />}
          label="Deadlines"
          active={section === "deadlines"}
          onClick={() => goToSection("deadlines")}
        />
        <ProjectsNav />
      </nav>

      <GroupLabel>Lab</GroupLabel>
      <nav className="flex flex-col gap-0.5">
        <SidebarNavItem
          icon={<MembersIcon size={18} />}
          label="Members"
          active={section === "members"}
          onClick={() => goToSection("members")}
        />
        <SidebarNavItem
          icon={<DocumentIcon size={18} />}
          label="Reports"
          active={section === "reports"}
          onClick={() => goToSection("reports")}
          trailing={
            <span className="rounded-full border border-dashed border-border px-2 py-0.5 text-[10px] font-semibold text-[var(--text-muted)]">
              Soon
            </span>
          }
        />
      </nav>
    </aside>
  );
}
