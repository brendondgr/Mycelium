"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export type StatCardProps = {
  icon: React.ReactNode;
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  onClick?: () => void;
  /** Content alignment. Defaults to "left"; "center" horizontally centers the
   * icon/label row, the value, and the sub line (used by the Daily summaries). */
  align?: "left" | "center";
};

/**
 * A compact metric card for the overview stat grid. Renders as a button when
 * `onClick` is provided so it's keyboard and screen-reader accessible. The
 * large serif value defaults to "—" when the data is missing.
 */
export function StatCard({
  icon,
  label,
  value,
  sub,
  onClick,
  align = "left",
}: StatCardProps) {
  const centered = align === "center";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-2xl border border-border bg-surface shadow-[var(--shadow)] p-[18px] w-full",
        centered ? "text-center" : "text-left",
        "transition-transform motion-safe:hover:-translate-y-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        !onClick && "cursor-default",
      )}
    >
      {/* Icon + label row */}
      <div
        className={cn(
          "flex items-center gap-2 mb-3 text-[var(--text-secondary)]",
          centered && "justify-center",
        )}
      >
        <span className="text-primary">{icon}</span>
        <span className="text-[12.5px] font-medium">{label}</span>
      </div>

      {/* Big value */}
      <div className="font-serif text-[30px] font-semibold leading-none mb-[5px] text-[var(--text-primary)]">
        {value !== null && value !== undefined ? value : "—"}
      </div>

      {/* Muted sub line */}
      {sub && (
        <div className="text-[12px] text-[var(--text-secondary)]">{sub}</div>
      )}
    </button>
  );
}
