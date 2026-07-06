"use client";

import { usePathname } from "next/navigation";

import { PortalFooter } from "@/components/portal/portal-footer";
import { PortalHeader } from "@/components/portal/portal-header";
import { PortalMobileNav } from "@/components/portal/portal-mobile-nav";
import { PortalSidebar } from "@/components/portal/portal-sidebar";
import {
  PortalProvider,
  type PortalUser,
} from "@/components/portal/portal-context";
import { SectionStage } from "@/components/portal/section-stage";

/**
 * The authenticated workspace chrome: header, sidebar, mobile tabs, and footer
 * wrapped around the active route. Each `/app/*` page renders into the
 * `SectionStage`, which cross-fades on navigation (keyed by pathname).
 */
export function WorkspaceShell({
  user,
  children,
}: {
  user: PortalUser;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <PortalProvider user={user}>
      <div
        className="flex h-screen flex-col overflow-hidden bg-background text-foreground"
        style={{ fontFamily: "var(--font-inter)" }}
      >
        <PortalHeader />
        <PortalMobileNav />
        <div className="flex min-h-0 flex-1">
          <PortalSidebar />
          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-7 sm:px-6 lg:px-9 lg:py-8">
            <SectionStage stageKey={pathname}>{children}</SectionStage>
          </main>
        </div>
        <PortalFooter />
      </div>
    </PortalProvider>
  );
}
