"use client";

import * as React from "react";

import { Pill } from "@/components/portal/primitives/pill";
import { BookmarkIcon, SparkleIcon } from "@/components/portal/icons";
import { useSaveOpportunity } from "@/lib/portal/hooks";

/** Percent-match tiers: strong (green), fair (amber), low (terracotta). */
const STRONG_MATCH = 85;
const FAIR_MATCH = 60;

/** Resolve a percent into a fit tier and its semantic color token + word. */
function matchTier(percent: number): { token: string; word: string } {
  if (percent >= STRONG_MATCH) return { token: "--success", word: "strong" };
  if (percent >= FAIR_MATCH) return { token: "--warning", word: "fair" };
  return { token: "--clay", word: "low" };
}

/**
 * The model's percent match, color-coded by strength: green ≥ 85, amber 60–84,
 * terracotta below 60. The chip always carries the number and a word ("88%
 * strong"), so color is never the only signal — it only reinforces the fit.
 * Null percent (the fallback tail) renders nothing.
 */
export function MatchBadge({ percent }: { percent: number | null }) {
  if (typeof percent !== "number") return null;
  const { token, word } = matchTier(percent);
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold"
      style={{
        borderColor: `color-mix(in srgb, var(${token}) 45%, transparent)`,
        backgroundColor: `color-mix(in srgb, var(${token}) 14%, transparent)`,
        color: `color-mix(in srgb, var(${token}) 72%, var(--text-primary))`,
      }}
      aria-label={`${percent} percent match to your research profile, a ${word} match`}
    >
      <span aria-hidden="true">{percent}%</span>
      <span aria-hidden="true" className="font-medium opacity-80">
        {word}
      </span>
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
 * A short noun for what a saved deadline is counting down to — "Abstract",
 * "Apply to Conference", "Full paper", "Event". Returns "" when the kind is
 * unknown so the caller can fall back to a bare countdown.
 */
export function deadlineKindLabel(kind: string, area: string): string {
  switch (kind) {
    case "abstract":
      return "Abstract";
    case "manuscript":
      return "Full paper";
    case "application":
      return area === "conference" ? "Apply to Conference" : "Apply";
    case "event":
      return "Event";
    default:
      return "";
  }
}

/**
 * A bookmark toggle that saves/unsaves a grant or conference to the user's
 * deadlines. Optimistic feel via the mutation's pending state; disabled while a
 * write is in flight. The label always states the action for screen readers.
 *
 * `variant="icon"` renders a compact, round bookmark-only button (used on the
 * opportunity cards where space is tight); the default renders the labelled
 * pill used on the Deadlines page.
 */
export function SaveButton({
  contentId,
  saved,
  variant = "full",
}: {
  contentId: string;
  saved: boolean;
  variant?: "full" | "icon";
}) {
  const { save, unsave } = useSaveOpportunity();
  const pending = save.isPending || unsave.isPending;
  const toggle = () => {
    if (saved) {
      unsave.mutate(contentId);
    } else {
      save.mutate({ contentId });
    }
  };
  const label = saved ? "Remove from your deadlines" : "Save to your deadlines";
  const tone = saved
    ? {
        borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)",
        color: "var(--accent)",
      }
    : {
        borderColor: "var(--border)",
        backgroundColor: "var(--surface)",
        color: "var(--text-secondary)",
      };

  if (variant === "icon") {
    return (
      <button
        type="button"
        disabled={pending}
        onClick={toggle}
        aria-pressed={saved}
        aria-label={label}
        title={label}
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-60"
        style={tone}
      >
        <BookmarkIcon size={14} aria-hidden="true" />
      </button>
    );
  }

  return (
    <button
      type="button"
      disabled={pending}
      onClick={toggle}
      aria-pressed={saved}
      aria-label={label}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60"
      style={tone}
    >
      <BookmarkIcon size={13} aria-hidden="true" />
      {saved ? "Saved" : "Save deadline"}
    </button>
  );
}
