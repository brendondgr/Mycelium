"use client";

import { PortalFooter } from "@/components/portal/portal-footer";
import { PortalHeader } from "@/components/portal/portal-header";
import { PortalMobileNav } from "@/components/portal/portal-mobile-nav";
import { PortalSidebar } from "@/components/portal/portal-sidebar";
import {
  PortalProvider,
  usePortal,
  type PortalUser,
} from "@/components/portal/portal-context";
import { SectionStage } from "@/components/portal/section-stage";
import { DailyReportsSection } from "@/components/portal/sections/daily-reports-section";
import { DeadlinesSection } from "@/components/portal/sections/deadlines-section";
import { GoalsSection } from "@/components/portal/sections/goals-section";
import { MembersSection } from "@/components/portal/sections/members-section";
import { OpportunitiesSection } from "@/components/portal/sections/opportunities-section";
import { OverviewSection } from "@/components/portal/sections/overview-section";
import { ProjectDetailSection } from "@/components/portal/sections/project-detail-section";
import { ProjectsListSection } from "@/components/portal/sections/projects-list-section";
import { ReportsSection } from "@/components/portal/sections/reports-section";

function PortalContent() {
  const { section, activeProjectId } = usePortal();

  const stageKey =
    section === "projects"
      ? `projects:${activeProjectId ?? "list"}`
      : section;

  let body: React.ReactNode;
  switch (section) {
    case "overview":
      body = <OverviewSection />;
      break;
    case "daily":
      body = <DailyReportsSection />;
      break;
    case "opportunities":
      body = <OpportunitiesSection />;
      break;
    case "deadlines":
      body = <DeadlinesSection />;
      break;
    case "projects":
      body = activeProjectId ? <ProjectDetailSection /> : <ProjectsListSection />;
      break;
    case "goals":
      body = <GoalsSection />;
      break;
    case "members":
      body = <MembersSection />;
      break;
    case "reports":
      body = <ReportsSection />;
      break;
  }

  return (
    <main className="min-w-0 flex-1 px-4 py-7 sm:px-6 lg:px-9 lg:py-8">
      <SectionStage stageKey={stageKey}>{body}</SectionStage>
    </main>
  );
}

/** The authenticated home feed: a compartmentalized lab-intelligence dashboard. */
export function Portal({ user }: { user: PortalUser }) {
  return (
    <PortalProvider user={user}>
      <div
        className="flex min-h-screen flex-col bg-background text-foreground"
        style={{ fontFamily: "var(--font-inter)" }}
      >
        <PortalHeader />
        <PortalMobileNav />
        <div className="flex flex-1 items-start">
          <PortalSidebar />
          <PortalContent />
        </div>
        <PortalFooter />
      </div>
    </PortalProvider>
  );
}
