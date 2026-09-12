"use client";

import { SporeNode } from "@/components/portal/icons";
import { NavIconFor } from "@/components/portal/nav-icon";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { useEntitlements } from "@/lib/portal/hooks";
import { navGroupsFor } from "@/lib/portal/nav";
import { KIND_LABEL, type Workspace } from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 px-3.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
      {children}
    </p>
  );
}

/**
 * The active workspace's brand block: a lab's uploaded logo (or its name), and a
 * pill naming the kind of workspace you are in. The rail to its left says
 * *which* workspace; this says *what kind*, which is what changes the navigation
 * underneath it.
 */
function WorkspaceIdentity({ workspace }: { workspace: Workspace }) {
  if (workspace.kind === "personal") {
    return (
      <div className="mb-4 px-1 pt-1">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-alt px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          Personal workspace
        </span>
      </div>
    );
  }

  const hasLogo = Boolean(workspace.lab && workspace.lab.logo_version !== null);
  return (
    <div className="mb-5 flex flex-col items-center gap-2 px-2 pt-1 text-center">
      {hasLogo ? (
        <WorkspaceMark
          workspace={workspace}
          size={48}
          radius={10}
          className="max-w-[150px]"
        />
      ) : (
        <span className="font-serif text-[18px] font-semibold leading-tight text-[var(--text-primary)]">
          {workspace.name}
        </span>
      )}
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.07em]",
          workspace.kind === "lab"
            ? "bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-primary"
            : "bg-[color-mix(in_srgb,var(--brand-accent)_18%,transparent)] text-[var(--warning)]",
        )}
      >
        <SporeNode size={11} />
        {KIND_LABEL[workspace.kind]} workspace
      </span>
    </div>
  );
}

/**
 * The left section navigation (desktop). The workspace rail sits to its left and
 * chooses *which* workspace; this lists what that workspace can reach, from the
 * single scope→sections model in `lib/portal/nav.ts` that the mobile sheet also
 * renders — so the two can never drift.
 */
export function PortalSidebar() {
  const {
    section,
    goToSection,
    scope,
    currentWorkspace,
    currentLab,
    currentDepartment,
    user,
  } = usePortal();
  const { data: entitlements } = useEntitlements();

  // Personal research entries only populate on a paid personal plan; a lab is on
  // its own (paid) plan, so lab research entries are always shown to members.
  const has = (feature: string) =>
    !entitlements || entitlements.features.includes(feature);

  const groups = navGroupsFor({
    scope,
    currentLab,
    currentDepartment,
    isAdmin: isPlatformAdmin(user),
    hasFeature: has,
  });

  // "Account" is pinned to the foot of the sidebar, away from the day-to-day
  // entries; the rest render in order.
  const accountGroup = groups.find((group) => group.label === "Account");
  const mainGroups = groups.filter((group) => group.label !== "Account");

  return (
    <aside className="hidden h-full w-[244px] shrink-0 flex-col overflow-y-auto border-r border-[var(--divider)] px-3.5 pb-6 pt-[18px] lg:flex">
      <WorkspaceIdentity workspace={currentWorkspace} />

      {mainGroups.map((group) => (
        <div key={group.label}>
          <GroupLabel>{group.label}</GroupLabel>
          <nav className="mb-[18px] flex flex-col gap-0.5">
            {group.items.map((item) =>
              // Projects owns its own expandable sub-list of the reader's
              // projects, so it renders itself rather than as a flat row.
              item.key === "projects" ? (
                <ProjectsNav key="projects" />
              ) : (
                <SidebarNavItem
                  key={`${group.label}-${item.key}`}
                  icon={<NavIconFor icon={item.icon} />}
                  label={item.label}
                  active={section === item.key}
                  onClick={() => goToSection(item.key)}
                />
              ),
            )}
          </nav>
        </div>
      ))}

      {scope.kind === "department" ? (
        <p className="-mt-3 mb-[18px] px-3.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
          Research feeds are matched to a lab or to you — a department
          doesn&apos;t have its own.
        </p>
      ) : null}

      {accountGroup ? (
        <nav className="mt-auto flex flex-col gap-0.5 pt-[18px]">
          {accountGroup.items.map((item) => (
            <SidebarNavItem
              key={`account-${item.key}`}
              icon={<NavIconFor icon={item.icon} />}
              label={item.label}
              active={section === item.key}
              onClick={() => goToSection(item.key)}
            />
          ))}
        </nav>
      ) : null}
    </aside>
  );
}
