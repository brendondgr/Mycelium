"use client";

import { ChevronDownIcon, PlusIcon, SporeNode } from "@/components/portal/icons";
import { roleLabel, usePortal } from "@/components/portal/portal-context";
import { useDismissable } from "@/lib/portal/use-dismissable";
import { PERSONAL_SLUG } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * The workspace context switch: a two-position slider between the caller's
 * **Personal** space (left) and their **Lab** space (right). Sliding into Lab
 * activates the current lab; with several labs the Lab side is a dropdown that
 * picks which one (and offers "Browse & create"). Switching always lands on the
 * relevant overview so the change is visible. Replaces the old dropdown-only
 * "Switch context" menu, and is the sole home for lab create/browse now that the
 * sidebar no longer lists labs.
 */
export function LabSwitcher() {
  const { labs, labsLoading, labScope, currentLab, setLabScope, goToSection } =
    usePortal();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  if (labsLoading) {
    return (
      <div
        className="h-9 w-[220px] animate-pulse rounded-full bg-surface-alt"
        aria-hidden
      />
    );
  }

  const onPersonal = labScope === PERSONAL_SLUG || !currentLab;

  const goPersonal = () => {
    setLabScope(PERSONAL_SLUG);
    setOpen(false);
    goToSection("overview");
  };

  const activateLab = (slug: string) => {
    setLabScope(slug);
    setOpen(false);
    goToSection("overview");
  };

  // Clicking the Lab side: no labs → send to create; one lab → open it; many →
  // open the picker (or, if already on a lab, let the picker switch between them).
  const onLabSide = () => {
    if (labs.length === 0) {
      setLabScope(PERSONAL_SLUG);
      setOpen(false);
      goToSection("labs");
      return;
    }
    if (labs.length === 1) {
      activateLab(labs[0].slug);
      return;
    }
    setOpen((value) => !value);
  };

  const labSegmentLabel =
    labs.length === 0
      ? "New lab"
      : currentLab
        ? currentLab.name
        : labs.length === 1
          ? labs[0].name
          : "Lab";

  const hasPicker = labs.length > 1;

  return (
    <div ref={ref} className="relative shrink-0">
      <div
        role="group"
        aria-label="Workspace"
        className="inline-flex items-center rounded-full border border-border bg-surface-alt p-0.5 text-[13px] font-medium"
      >
        <button
          type="button"
          onClick={goPersonal}
          aria-pressed={onPersonal}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            onPersonal
              ? "bg-surface text-[var(--text-primary)] shadow-[var(--shadow)]"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              onPersonal ? "bg-primary" : "bg-[var(--text-muted)]",
            )}
          />
          Personal
        </button>

        <button
          type="button"
          onClick={onLabSide}
          aria-pressed={!onPersonal}
          aria-haspopup={hasPicker ? "menu" : undefined}
          aria-expanded={hasPicker ? open : undefined}
          className={cn(
            "inline-flex max-w-[180px] items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            !onPersonal
              ? "bg-surface text-[var(--text-primary)] shadow-[var(--shadow)]"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          {labs.length === 0 ? (
            <PlusIcon size={13} className="shrink-0" />
          ) : (
            <SporeNode size={13} className="shrink-0" />
          )}
          <span className="truncate">{labSegmentLabel}</span>
          {hasPicker ? (
            <ChevronDownIcon size={13} className="shrink-0 text-[var(--text-secondary)]" />
          ) : null}
        </button>
      </div>

      {open && hasPicker ? (
        <div
          role="menu"
          className="absolute left-0 top-11 z-40 min-w-[248px] rounded-2xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          <p className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Choose a lab
          </p>
          {labs.map((lab) => (
            <button
              key={lab.slug}
              type="button"
              role="menuitemradio"
              aria-checked={labScope === lab.slug}
              onClick={() => activateLab(lab.slug)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                labScope === lab.slug && "bg-surface-alt",
              )}
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-surface-alt text-brand-secondary">
                <SporeNode size={13} />
              </span>
              <span className="flex-1 truncate">{lab.name}</span>
              <span className="text-[11px] text-[var(--text-secondary)]">
                {roleLabel(lab)}
              </span>
            </button>
          ))}
          <div className="my-1 border-t border-[var(--divider)]" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setLabScope(PERSONAL_SLUG);
              setOpen(false);
              goToSection("labs");
            }}
            className="flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-surface-alt text-brand-secondary">
              <PlusIcon size={13} />
            </span>
            Browse &amp; create labs
          </button>
        </div>
      ) : null}
    </div>
  );
}
