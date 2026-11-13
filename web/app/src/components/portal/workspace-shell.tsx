"use client";

import { usePathname } from "next/navigation";

import { DemoBanner } from "@/components/demo/demo-banner";
import { DemoProvider } from "@/components/demo/demo-context";
import { canonicalPath } from "@/lib/demo";

import { CollaboratorSearchHost } from "@/components/portal/collab/search-panel";
import { ChatHost } from "@/components/portal/mylo/chat-host";
import { PortalHeader } from "@/components/portal/portal-header";
import { PortalSidebar } from "@/components/portal/portal-sidebar";
import { ScopeGuard } from "@/components/portal/scope-guard";
import { WorkspacePalette } from "@/components/portal/workspace-palette";
import {
  PortalProvider,
  type PortalUser,
} from "@/components/portal/portal-context";
import { WorkspaceGround } from "@/components/portal/motion/workspace-ground";
import { SectionStage } from "@/components/portal/section-stage";
import { parseSettingsPath, SETTINGS_BASE } from "@/lib/portal/settings";

import "./workspace.css";

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
  const pathname = canonicalPath(usePathname());
  // Inside Settings the workspace sidebar gives way to the area's own top bar
  // (context picker + page tabs); the header stays.
  const inSettings = parseSettingsPath(pathname) !== null || pathname === SETTINGS_BASE;

  return (
    <DemoProvider demo={user.demo}>
    <PortalProvider user={user}>
      <div
        className="ws-shell flex h-screen flex-col overflow-hidden bg-background text-foreground"
        style={{ fontFamily: "var(--font-inter)", fontSize: "var(--d-fs)" }}
      >
        <ScopeGuard />
        <WorkspacePalette />
        <CollaboratorSearchHost />
        <ChatHost />
        <DemoBanner />
        <PortalHeader />
        {/*
          No secondary mobile nav row. At phone width the rail and the sidebar
          are both hidden and everything lives in the header's sheet, so the
          chrome is one row instead of two.
        */}
        <div className="flex min-h-0 flex-1">
          {inSettings ? null : <PortalSidebar />}
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
            <WorkspaceGround />
            <main className="ws-main relative min-w-0 flex-1 overflow-y-auto px-4 py-7 sm:px-6 lg:px-9 lg:py-8">
              {/* Moving between settings tabs keeps the area's top bar in place
                  rather than cross-fading the whole page. */}
              <SectionStage stageKey={inSettings ? SETTINGS_BASE : pathname}>{children}</SectionStage>
            </main>
          </div>
        </div>
      </div>
    </PortalProvider>
    </DemoProvider>
  );
}
