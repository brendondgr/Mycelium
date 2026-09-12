"use client";

import { PlusIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { KIND_LABEL, scopeForWorkspace } from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

/**
 * The desktop workspace rail — a narrow always-visible column at the far left,
 * before the section sidebar: the personal space, then departments, then labs,
 * then a way to create or join one.
 *
 * It replaces a two-position slider whose right half changed meaning depending
 * on how many labs you were in (a button with one, a dropdown with several).
 * A rail has no such ambiguity: every workspace is its own target, always in the
 * same place, and switching costs one click with nothing to open first.
 *
 * Hidden below `lg`. A rail is a desktop idea — shrunk to phone width the marks
 * stop being recognisable — so mobile drops it entirely and uses
 * `WorkspaceSheet` instead.
 */
export function WorkspaceRail() {
  const { workspaces, workspacesLoading, scope, setScope, goToSection } =
    usePortal();

  if (workspacesLoading) {
    return (
      <div
        className="hidden w-[60px] shrink-0 flex-col items-center gap-2 border-r border-[var(--divider)] py-3 lg:flex"
        aria-hidden
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-[34px] w-[34px] animate-pulse rounded-[11px] bg-surface-alt"
          />
        ))}
      </div>
    );
  }

  const personal = workspaces.filter((w) => w.kind === "personal");
  const orgs = workspaces.filter((w) => w.kind !== "personal");
  const activeKey =
    scope.kind === "lab"
      ? scope.slug
      : scope.kind === "department"
        ? scope.id
        : personal[0]?.key;

  return (
    <nav
      aria-label="Workspaces"
      className="hidden w-[60px] shrink-0 flex-col items-center gap-1.5 overflow-y-auto border-r border-[var(--divider)] bg-[color-mix(in_srgb,var(--surface-alt)_55%,var(--background))] py-3 lg:flex"
    >
      {[personal, orgs].map((group, groupIndex) =>
        group.length === 0 ? null : (
          <div
            key={groupIndex}
            className="flex w-full flex-col items-center gap-1.5"
          >
            {groupIndex === 1 ? (
              <span
                className="my-1 h-px w-6 shrink-0 bg-[var(--divider)]"
                aria-hidden
              />
            ) : null}
            {group.map((workspace) => {
              const active = workspace.key === activeKey;
              return (
                <button
                  key={workspace.key}
                  type="button"
                  onClick={() => setScope(scopeForWorkspace(workspace))}
                  aria-current={active ? "true" : undefined}
                  aria-label={`${workspace.name} · ${KIND_LABEL[workspace.kind]}`}
                  title={`${workspace.name} · ${KIND_LABEL[workspace.kind]}`}
                  className={cn(
                    "group relative grid h-[38px] w-[38px] shrink-0 place-items-center rounded-xl transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "opacity-100" : "opacity-70 hover:opacity-100",
                  )}
                >
                  {/*
                    The active workspace is marked twice over: a green edge bar
                    and a ring. Neither is colour alone — `aria-current` carries
                    it for anyone who can't see either.
                  */}
                  {active ? (
                    <span
                      aria-hidden
                      className="absolute -left-[11px] top-1/2 h-[22px] w-[3px] -translate-y-1/2 rounded-r-[3px] bg-primary"
                    />
                  ) : null}
                  <WorkspaceMark
                    workspace={workspace}
                    size={34}
                    radius={active ? 9 : 11}
                    className={cn(
                      "transition-[border-radius]",
                      active &&
                        "ring-2 ring-primary ring-offset-2 ring-offset-[var(--background)]",
                    )}
                  />
                </button>
              );
            })}
          </div>
        ),
      )}

      <span className="my-1 h-px w-6 shrink-0 bg-[var(--divider)]" aria-hidden />
      <button
        type="button"
        onClick={() => goToSection("labs")}
        aria-label="Browse and create workspaces"
        title="Browse and create workspaces"
        className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[11px] border border-dashed border-border text-[var(--text-muted)] transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <PlusIcon size={16} />
      </button>
    </nav>
  );
}
