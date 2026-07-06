"use client";

import * as React from "react";

import { ChevronDownIcon, SporeNode } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import type { MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * One lab as a sidebar tab. Clicking the row makes that lab the active
 * workspace (and lands on its overview); the chevron opens an inline action
 * menu — open, edit setup, manage & invite. The menu is inline (not an absolute
 * popover) so the sidebar's `overflow-y-auto` never clips it.
 */
export function LabNavItem({ lab }: { lab: MyLab }) {
  const { labScope, setLabScope, goToSection, openLabEditor } = usePortal();
  const [open, setOpen] = React.useState(false);
  const active = labScope === lab.slug;

  const activate = () => {
    setLabScope(lab.slug);
    goToSection("overview");
  };

  return (
    <div>
      <div
        className={cn(
          "relative flex items-center rounded-[10px] transition-colors",
          active ? "" : "hover:bg-surface-alt",
        )}
      >
        {active ? (
          <>
            <span
              aria-hidden
              className="absolute inset-0 rounded-[10px] bg-[color-mix(in_srgb,var(--primary)_13%,transparent)]"
            />
            <span
              aria-hidden
              className="absolute bottom-2 left-0 top-2 w-[3px] rounded-full bg-primary"
            />
          </>
        ) : null}

        <button
          type="button"
          onClick={activate}
          aria-current={active ? "page" : undefined}
          className={cn(
            "relative flex min-w-0 flex-1 items-center gap-3 rounded-l-[10px] py-2.5 pl-4 text-left text-[13.5px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active
              ? "font-semibold text-[var(--text-primary)]"
              : "font-medium text-[var(--text-secondary)]",
          )}
        >
          <span className="shrink-0 text-brand-secondary">
            <SporeNode size={15} />
          </span>
          <span className="truncate">{lab.name}</span>
        </button>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={`${lab.name} actions`}
          aria-expanded={open}
          className="relative mr-1 rounded-md p-1.5 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronDownIcon
            size={14}
            className={cn("transition-transform", open && "rotate-180")}
          />
        </button>
      </div>

      {open ? (
        <div className="ml-4 mt-0.5 flex flex-col border-l border-[var(--divider)] pl-2">
          <MenuItem onClick={activate}>Open Overview</MenuItem>
          <MenuItem onClick={() => openLabEditor(lab.slug)}>Edit Setup</MenuItem>
          <MenuItem
            onClick={() => {
              setLabScope(lab.slug);
              goToSection("labs");
            }}
          >
            Manage &amp; Invite
          </MenuItem>
        </div>
      ) : null}
    </div>
  );
}

function MenuItem({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md px-2.5 py-1.5 text-left text-[12.5px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
    </button>
  );
}
