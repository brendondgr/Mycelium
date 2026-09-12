"use client";

import { usePathname } from "next/navigation";

import { PortalHeader } from "@/components/portal/portal-header";
import { PortalSidebar } from "@/components/portal/portal-sidebar";
import { ScopeGuard } from "@/components/portal/scope-guard";
import { WorkspacePalette } from "@/components/portal/workspace-palette";
import { WorkspaceRail } from "@/components/portal/workspace-rail";
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
        <ScopeGuard />
        <WorkspacePalette />
        <PortalHeader />
        {/*
          No secondary mobile nav row. At phone width the rail and the sidebar
          are both hidden and everything lives in the header's sheet, so the
          chrome is one row instead of two.
        */}
        <div className="flex min-h-0 flex-1">
          <WorkspaceRail />
          <PortalSidebar />
          {/*
            The ground sits in a wrapper that does not itself scroll, so it
            stays put behind the section instead of sliding up with the feed.

            Two constraints on this wrapper, both learned the hard way:

            - It must NOT be `isolate`. Every dialog in the workspace is a
              `fixed inset-0 z-50` element rendered inside `main`; a stacking
              context here traps them below the sticky header and they open
              behind the chrome. `main` therefore also carries no `z-index` —
              the ground and `main` are both positioned with `z-index` auto/0,
              so plain DOM order puts the content above the ground.
            - It mirrors the constraint chain `main` used to have directly
              (`flex min-h-0 min-w-0 flex-1`), so `main` keeps exactly the
              classes it always had and the row can still shrink to the screen.
          */}
          <div className="relative flex min-h-0 min-w-0 flex-1">
            <PortalGround pathname={pathname} />
            <main className="relative min-w-0 flex-1 overflow-y-auto px-4 py-7 sm:px-6 lg:px-9 lg:py-8">
              <SectionStage stageKey={pathname}>{children}</SectionStage>
            </main>
          </div>
        </div>
      </div>
    </PortalProvider>
  );
}
