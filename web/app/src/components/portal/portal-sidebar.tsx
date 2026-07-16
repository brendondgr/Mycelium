"use client";

import {
  BankIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  GridIcon,
  PlusIcon,
  ReportIcon,
  SparkleIcon,
  SporeNode,
  TargetIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { LabNavItem } from "@/components/portal/lab-nav-item";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";
import { useEntitlements } from "@/lib/portal/hooks";
import { FEATURE, PERSONAL_SLUG } from "@/lib/portal/types";

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
  const { data: entitlements } = useEntitlements();
  // Show a scheduled/opportunity nav entry only when the plan includes it — a Free
  // account is on-demand, so these products never populate for it. While the query
  // is in flight we show the entries (paid users are the common case, no flicker).
  const has = (feature: string) =>
    !entitlements || entitlements.features.includes(feature);

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
        <SidebarNavItem
          icon={<BookmarkIcon size={18} />}
          label="Saves"
          active={section === "saves"}
          onClick={() => goToSection("saves")}
        />
      </nav>

      <GroupLabel>Research</GroupLabel>
      <nav className="mb-[18px] flex flex-col gap-0.5">
        {has(FEATURE.SCHEDULED_REPORTS) && (
          <SidebarNavItem
            icon={<ReportIcon size={18} />}
            label="Daily Reports"
            active={section === "daily"}
            onClick={() => goToSection("daily")}
          />
        )}
        <SidebarNavItem
          icon={<SporeNode size={18} />}
          label="Suggested for you"
          active={section === "suggested"}
          onClick={() => goToSection("suggested")}
        />
        <SidebarNavItem
          icon={<DocumentIcon size={18} />}
          label="Research Papers"
          active={section === "papers"}
          onClick={() => goToSection("papers")}
        />
        {has(FEATURE.GRANT_ALERTS) && (
          <SidebarNavItem
            icon={<BankIcon size={18} />}
            label="Grants"
            active={section === "opportunities"}
            onClick={() => goToSection("opportunities")}
          />
        )}
        {has(FEATURE.FELLOWSHIP_MATCHING) && (
          <SidebarNavItem
            icon={<SparkleIcon size={18} />}
            label="Fellowships"
            active={section === "fellowships"}
            onClick={() => goToSection("fellowships")}
          />
        )}
        {has(FEATURE.CONFERENCE_ALERTS) && (
          <SidebarNavItem
            icon={<ConferenceIcon size={18} />}
            label="Conferences"
            active={section === "conferences"}
            onClick={() => goToSection("conferences")}
          />
        )}
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
