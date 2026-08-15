"use client";

import { usePathname } from "next/navigation";

import { PortalHeader } from "@/components/portal/portal-header";
import { PortalMobileNav } from "@/components/portal/portal-mobile-nav";
import { PortalSidebar } from "@/components/portal/portal-sidebar";
import {
  PortalProvider,
  type PortalUser,
} from "@/components/portal/portal-context";
import { PortalGround } from "@/components/portal/motion/section-ground";
import { SectionStage } from "@/components/portal/section-stage";

/**
 * The authenticated workspace chrome: header, sidebar, and mobile tabs wrapped
 * around the active route. Each `/app/*` page renders into the `SectionStage`,
 * which cross-fades on navigation (keyed by pathname).
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
          {/* The ground lives in a wrapper that does not scroll, so it stays
              put behind the section instead of sliding up with the feed. */}
          <div className="relative isolate min-w-0 flex-1">
            <PortalGround pathname={pathname} />
            <main className="relative z-10 h-full overflow-y-auto px-4 py-7 sm:px-6 lg:px-9 lg:py-8">
              <SectionStage stageKey={pathname}>{children}</SectionStage>
            </main>
          </div>
        </div>
      </div>
    </PortalProvider>
  );
}
