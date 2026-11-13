"use client";

import { SporeNode } from "@/components/portal/icons";
import { NavIconFor } from "@/components/portal/nav-icon";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { useEntitlements } from "@/lib/portal/hooks";
import { useRailCollapsed } from "@/lib/portal/use-rail";
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
        <span className="w-full whitespace-normal break-words text-center font-serif text-[18px] font-semibold leading-tight text-[var(--text-primary)] [text-wrap:balance]">
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
 * The left section navigation (desktop). The header's dropdown chooses *which*
 * workspace; this lists what that workspace can reach, from the single
 * scope→sections model in `lib/portal/nav.ts` that the mobile sheet also
 * renders — so the two can never drift.
 *
 * It starts open and collapses to icons only when the reader uses the header's
 * toggle. The rail is `whitespace-nowrap` so labels don't reflow while its width
 * animates; free text inside it (the workspace name, the department note) must
 * opt back into wrapping with `whitespace-normal`.
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
  const { collapsed } = useRailCollapsed();

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

  // "Settings" is pinned to the foot of the sidebar, away from the day-to-day
  // entries; the rest render in order.
  const footGroup = groups.find((group) => group.label === "Settings");
  const mainGroups = groups.filter((group) => group.label !== "Settings");

  return (
    <aside
      aria-label="Sections"
      data-collapsed={collapsed || undefined}
      className={cn(
        "ws-rail relative z-[1] hidden h-full shrink-0 flex-col overflow-y-auto overflow-x-hidden whitespace-nowrap border-r border-[var(--border-soft)] bg-[color-mix(in_srgb,var(--background)_55%,transparent)] pb-6 pt-[18px] lg:flex",
        collapsed ? "px-2.5" : "px-3.5",
      )}
    >
      {collapsed ? null : <WorkspaceIdentity workspace={currentWorkspace} />}

      {mainGroups.map((group, index) => (
        <div key={group.label}>
          {collapsed ? (
            index > 0 ? <span className="mx-auto mb-3 block h-px w-6 bg-[var(--divider)]" aria-hidden /> : null
          ) : (
            <GroupLabel>{group.label}</GroupLabel>
          )}
          <nav aria-label={group.label} className="mb-[18px] flex flex-col gap-0.5">
            {group.items.map((item) =>
              // Projects owns its own expandable sub-list of the reader's
              // projects, so it renders itself rather than as a flat row.
              item.key === "projects" ? (
                <ProjectsNav key="projects" collapsed={collapsed} />
              ) : (
                <SidebarNavItem
                  key={`${group.label}-${item.key}`}
                  icon={<NavIconFor icon={item.icon} />}
                  label={item.label}
                  active={section === item.key}
                  onClick={() => goToSection(item.key)}
                  collapsed={collapsed}
                />
              ),
            )}
          </nav>
        </div>
      ))}

      {scope.kind === "department" && !collapsed ? (
        <p className="-mt-3 mb-[18px] whitespace-normal px-3.5 text-center text-[11px] leading-relaxed text-[var(--text-muted)] [text-wrap:pretty]">
          Research feeds are matched to a lab or to you. A department&apos;s
          Opportunities lists the calls only a department can take on.
        </p>
      ) : null}

      {footGroup ? (
        <nav aria-label="Settings" className="mt-auto flex flex-col gap-0.5 pt-[18px]">
          {footGroup.items.map((item) => (
            <SidebarNavItem
              key={`foot-${item.key}`}
              icon={<NavIconFor icon={item.icon} />}
              label={item.label}
              active={section === item.key}
              onClick={() => goToSection(item.key)}
              collapsed={collapsed}
            />
          ))}
        </nav>
      ) : null}
    </aside>
  );
}
