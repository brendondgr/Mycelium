"use client";

import {
  BankIcon,
  CalendarIcon,
  ConferenceIcon,
  DocumentIcon,
  GridIcon,
  PlusIcon,
  ReportIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { LabNavItem } from "@/components/portal/lab-nav-item";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";
import { PERSONAL_SLUG } from "@/lib/portal/types";

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 px-3.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** The left workspace navigation (desktop). Mobile uses a separate tab strip. */
export function PortalSidebar() {
  const { section, goToSection, labs, setLabScope } = usePortal();

  return (
    <aside className="hidden h-full w-[244px] shrink-0 overflow-y-auto border-r border-[var(--divider)] px-3.5 pb-6 pt-[18px] lg:block">
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
          icon={<DocumentIcon size={18} />}
          label="Research Papers"
          active={section === "papers"}
          onClick={() => goToSection("papers")}
        />
        <SidebarNavItem
          icon={<BankIcon size={18} />}
          label="Grants"
          active={section === "opportunities"}
          onClick={() => goToSection("opportunities")}
        />
        <SidebarNavItem
          icon={<SparkleIcon size={18} />}
          label="Fellowships"
          active={section === "fellowships"}
          onClick={() => goToSection("fellowships")}
        />
        <SidebarNavItem
          icon={<ConferenceIcon size={18} />}
          label="Conferences"
          active={section === "conferences"}
          onClick={() => goToSection("conferences")}
        />
        <SidebarNavItem
          icon={<CalendarIcon size={18} />}
          label="Deadlines"
          active={section === "deadlines"}
          onClick={() => goToSection("deadlines")}
        />
        <ProjectsNav />
      </nav>

      <GroupLabel>Labs</GroupLabel>
      <nav className="flex flex-col gap-0.5">
        {labs.map((lab) => (
          <LabNavItem key={lab.slug} lab={lab} />
        ))}
        <SidebarNavItem
          icon={<PlusIcon size={18} />}
          label={labs.length === 0 ? "Create a lab" : "Browse & create"}
          active={section === "labs"}
          onClick={() => {
            setLabScope(PERSONAL_SLUG);
            goToSection("labs");
          }}
        />
      </nav>
    </aside>
  );
}
