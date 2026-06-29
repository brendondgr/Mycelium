"use client";

import { ChevronDownIcon, SporeNode } from "@/components/portal/icons";
import { roleLabel, usePortal } from "@/components/portal/portal-context";
import { useDismissable } from "@/lib/portal/use-dismissable";
import { ALL_LABS_SLUG } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * Workspace context switcher. Lists the signed-in user's labs (with their role)
 * plus an "All labs" overview scope; selecting one rescopes projects and the
 * member roster. Personal accounts with no labs show a static label.
 */
export function LabSwitcher() {
  const { labs, labsLoading, labScope, setLabScope, currentLab } = usePortal();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  if (labsLoading) {
    return (
      <div className="h-8 w-40 animate-pulse rounded-full bg-surface-alt" aria-hidden />
    );
  }

  if (labs.length === 0) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-alt px-3 py-1.5 text-[13px] font-medium text-foreground">
        <span className="h-2 w-2 rounded-full bg-primary" />
        Personal workspace
      </span>
    );
  }

  const label = currentLab ? currentLab.name : "All labs";

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-border bg-surface-alt px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="h-2 w-2 rounded-full bg-primary" />
        {label}
        <ChevronDownIcon size={14} className="text-[var(--text-muted)]" />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute left-0 top-11 z-40 min-w-[248px] rounded-2xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          <p className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            Switch context
          </p>
          <SwitcherItem
            label="All labs"
            meta="Overview"
            active={labScope === ALL_LABS_SLUG}
            onSelect={() => {
              setLabScope(ALL_LABS_SLUG);
              setOpen(false);
            }}
          />
          {labs.map((lab) => (
            <SwitcherItem
              key={lab.slug}
              label={lab.name}
              meta={roleLabel(lab)}
              active={labScope === lab.slug}
              onSelect={() => {
                setLabScope(lab.slug);
                setOpen(false);
              }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SwitcherItem({
  label,
  meta,
  active,
  onSelect,
}: {
  label: string;
  meta: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={active}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "bg-surface-alt",
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-surface-alt text-brand-secondary">
        <SporeNode size={13} />
      </span>
      <span className="flex-1 truncate">{label}</span>
      <span className="text-[11px] text-[var(--text-muted)]">{meta}</span>
    </button>
  );
}
