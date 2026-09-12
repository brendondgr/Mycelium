"use client";

import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { KIND_LABEL } from "@/lib/portal/workspace";

/**
 * The header's statement of where you are, on desktop only.
 *
 * The rail beside it is what you *click*; a rail of marks alone cannot spell a
 * name, so this spells it. Deliberately not a control — two things to press that
 * do the same job is how the old switcher became ambiguous.
 */
export function WorkspaceCaption() {
  const { currentWorkspace, workspacesLoading } = usePortal();

  if (workspacesLoading) {
    return (
      <div
        className="hidden h-9 w-[160px] animate-pulse rounded-full bg-surface-alt lg:block"
        aria-hidden
      />
    );
  }

  return (
    <div className="hidden min-w-0 shrink-0 items-center gap-2.5 lg:flex">
      <WorkspaceMark workspace={currentWorkspace} size={28} />
      <span className="min-w-0 leading-tight">
        <span className="block text-[9.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
          {KIND_LABEL[currentWorkspace.kind]}
        </span>
        <span className="block max-w-[180px] truncate text-[14px] font-semibold text-[var(--text-primary)]">
          {currentWorkspace.name}
        </span>
      </span>
    </div>
  );
}
