"use client";

import * as React from "react";

import { Pill } from "@/components/portal/primitives/pill";
import { BookmarkIcon, SparkleIcon } from "@/components/portal/icons";
import { useSaveOpportunity } from "@/lib/portal/hooks";

/** A grant/conference at or above this percent match is highlighted as strong. */
const STRONG_MATCH = 75;

/**
 * The model's percent match. Text always carries the value ("88% match"), so
 * color is never the only signal; the gold accent only reinforces a strong fit.
 * Null percent (the fallback tail) renders nothing.
 */
export function MatchBadge({ percent }: { percent: number | null }) {
  if (typeof percent !== "number") return null;
  const strong = percent >= STRONG_MATCH;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold"
      style={
        strong
          ? {
              borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
              backgroundColor: "color-mix(in srgb, var(--accent) 14%, transparent)",
              color: "var(--accent)",
            }
          : {
              borderColor: "var(--border)",
              backgroundColor: "var(--surface-alt)",
              color: "var(--text-secondary)",
            }
      }
      aria-label={`${percent} percent match to your research profile${
        strong ? ", a strong match" : ""
      }`}
    >
      <span aria-hidden="true">{percent}%</span>
      <span className="text-[var(--text-muted)]">match</span>
    </span>
  );
}

/**
 * The "New" tag for a fresh, high-fit item pinned to the top for its first week.
 * Carries an icon + text (never color alone) so the distinction is clear.
 */
export function NewTag() {
  return (
    <Pill tone="accent" className="shrink-0">
      <SparkleIcon size={12} aria-hidden="true" />
      New — worth a look
    </Pill>
  );
}

/** Human label for the actionable deadline, e.g. "Application due Nov 12, 2026". */
export function deadlineLabel(kind: string, dateIso: string): string {
  if (!dateIso) return "";
  const date = new Date(dateIso);
  const when = Number.isNaN(date.getTime())
    ? dateIso
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
  const label: Record<string, string> = {
    application: "Application due",
    abstract: "Abstract due",
    manuscript: "Full paper due",
    event: "Event",
  };
  return `${label[kind] ?? "Deadline"} ${when}`;
}

/**
 * A bookmark toggle that saves/unsaves a grant or conference to the user's
 * deadlines. Optimistic feel via the mutation's pending state; disabled while a
 * write is in flight. The label always states the action for screen readers.
 */
export function SaveButton({
  contentId,
  saved,
}: {
  contentId: string;
  saved: boolean;
}) {
  const { save, unsave } = useSaveOpportunity();
  const pending = save.isPending || unsave.isPending;

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        if (saved) {
          unsave.mutate(contentId);
        } else {
          save.mutate({ contentId });
        }
      }}
      aria-pressed={saved}
      aria-label={saved ? "Remove from your deadlines" : "Save to your deadlines"}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60"
      style={
        saved
          ? {
              borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
              backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)",
              color: "var(--accent)",
            }
          : {
              borderColor: "var(--border)",
              backgroundColor: "var(--surface)",
              color: "var(--text-secondary)",
            }
      }
    >
      <BookmarkIcon size={13} aria-hidden="true" />
      {saved ? "Saved" : "Save deadline"}
    </button>
  );
}
