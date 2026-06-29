"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type ProgressBarProps = {
  /** 0–100. */
  value: number;
  className?: string;
  /** Track fill color token; defaults to sage. */
  tone?: "primary" | "secondary";
  /** Visually-hidden label context for assistive tech. */
  label?: string;
};

/**
 * A thin rounded progress track. The fill grows from 0 on mount (motion-safe) so
 * a readiness/progress value reads as "filling in" rather than appearing static.
 */
export function ProgressBar({
  value,
  className,
  tone = "secondary",
  label,
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(clamped));
    return () => cancelAnimationFrame(frame);
  }, [clamped]);

  return (
    <div
      className={cn(
        "h-2 overflow-hidden rounded-full bg-[var(--divider)]",
        className,
      )}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className={cn(
          "h-full rounded-full motion-safe:transition-[width] motion-safe:duration-700 motion-safe:ease-out",
          tone === "primary" ? "bg-primary" : "bg-brand-secondary",
        )}
        style={{ width: `${shown}%` }}
      />
    </div>
  );
}
