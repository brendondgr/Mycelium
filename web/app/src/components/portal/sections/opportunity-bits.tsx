"use client";

import * as React from "react";

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
 * The model's percent match. The number is always dark and bold for legibility;
 * the fit tier (strong ≥ 85, fair 60–84, low below) shows as a small colored dot
 * and the aria-label, so color reinforces but never replaces the reading. When
 * Mylo (the LLM) judged the match, its headshot leads the badge in place of the
 * dot. Null percent (the fallback tail) renders nothing.
 */
export function MatchBadge({
  percent,
  origin,
}: {
  percent: number | null;
  origin?: "llm" | "fallback" | "rules";
}) {
  if (typeof percent !== "number") return null;
  const { token, word } = matchTier(percent);
  const byMylo = origin === "llm";
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      style={{
        borderColor: `color-mix(in srgb, var(${token}) 35%, var(--border))`,
        backgroundColor: `color-mix(in srgb, var(${token}) 10%, var(--surface))`,
      }}
      aria-label={`${percent} percent match to your research profile, a ${word} match${
        byMylo ? ", matched by Mylo" : ""
      }`}
    >
      {byMylo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src="/mylo-headshot.webp"
          alt=""
          width={16}
          height={16}
          className="h-4 w-4 shrink-0 rounded-full object-cover ring-1 ring-[var(--border)]"
        />
      ) : (
        <span
          aria-hidden="true"
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: `var(${token})` }}
        />
      )}
      <span className="text-sm font-bold leading-none text-[var(--text-primary)]">
        {percent}%
      </span>
      <span className="text-[10.5px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        match
      </span>
    </span>
  );
}

/**
 * Mylo's read on why an opportunity fits — the LLM's tailored explanation in a
 * soft green field led by Mylo's headshot. Shared across the Grants,
 * Conferences, and Fellowships cards so the AI note reads identically wherever
 * the language model wrote it (origin === "llm").
 */
export function MyloReason({ reason }: { reason: string }) {
  return (
    <div
      className="mt-3 flex items-start gap-2.5 rounded-xl border p-3"
      style={{
        borderColor: "color-mix(in srgb, var(--primary) 30%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--primary) 8%, transparent)",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/mylo-headshot.webp"
        alt=""
        width={24}
        height={24}
        className="mt-0.5 h-6 w-6 shrink-0 rounded-full object-cover"
      />
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        {reason}
      </p>
    </div>
  );
}

/**
 * The "New" tag for a freshly-seen item pinned to the top for its first week.
 * A solid green pill (with an icon + text, never color alone) so it's unmistakable.
 */
export function NewTag() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold"
      style={{
        backgroundColor: "var(--success)",
        color: "var(--destructive-foreground)",
      }}
    >
      <SparkleIcon size={12} aria-hidden="true" />
      New
    </span>
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
 * A bookmark toggle that saves/unsaves an item (paper, grant, conference, or
 * fellowship) to the user's Saves page. Optimistic feel via the mutation's
 * pending state; disabled while a write is in flight. The label always states
 * the action for screen readers.
 *
 * `variant="icon"` renders a compact, round bookmark-only button (used on the
 * cards where space is tight); the default renders the labelled pill used on
 * the Saves page.
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
  const label = saved ? "Remove from your saves" : "Save for later";
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
    // Colors live in className (not inline style) so the hover state can take
    // effect; each state keeps a clear icon-to-background contrast.
    const iconTone = saved
      ? "border-[color-mix(in_srgb,var(--accent)_45%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-accent hover:bg-[color-mix(in_srgb,var(--accent)_24%,transparent)]"
      : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] hover:text-accent";
    return (
      <button
        type="button"
        disabled={pending}
        onClick={toggle}
        aria-pressed={saved}
        aria-label={label}
        title={label}
        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-60 ${iconTone}`}
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
      {saved ? "Saved" : "Save"}
    </button>
  );
}
