"use client";

import * as React from "react";

import { ChevronDownIcon, CloseIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";
import type { GrantOpportunity } from "@/lib/portal/types";

/**
 * The client-side filter + sort model for the Grants page. The grants feed
 * returns the whole latest run in one payload, so every control here narrows an
 * already-fetched list in memory — no refetch, instant.
 */
export type GrantSort = "relevance" | "deadline" | "posted";
export type GrantStrength = "all" | "good" | "strong";
export type GrantDeadline = "all" | "d7" | "d30" | "d90" | "none";
export type GrantSource = "all" | "llm" | "fallback";

export type GrantFilterState = {
  /** Minimum fit: all / good (≥50%) / strong (≥75%). */
  strength: GrantStrength;
  /** Deadline window from today, or "none" for undated/rolling. */
  deadline: GrantDeadline;
  /** Selected deadline kinds (empty = all). */
  kinds: string[];
  /** Selected sponsors (empty = all). */
  sponsors: string[];
  /** Selected matched topics; a grant passes only if it matches all (empty = all). */
  topics: string[];
  /** Only items still inside their "New" pin window. */
  newOnly: boolean;
  /** Only items the user has saved. */
  savedOnly: boolean;
  /** Match origin: Mylo (llm) vs similarity-only (fallback). */
  source: GrantSource;
  sort: GrantSort;
};

export const DEFAULT_GRANT_FILTERS: GrantFilterState = {
  strength: "all",
  deadline: "all",
  kinds: [],
  sponsors: [],
  topics: [],
  newOnly: false,
  savedOnly: false,
  source: "all",
  sort: "relevance",
};

/** Human labels for the deadline-kind facet (only present kinds are shown). */
const KIND_LABELS: Record<string, string> = {
  application: "Application",
  abstract: "Abstract",
  manuscript: "Manuscript",
  event: "Event",
  other: "Other",
};
const KIND_ORDER = ["application", "abstract", "manuscript", "event", "other"];

type Option = { value: string; count: number };
export type GrantFilterOptions = {
  sponsors: Option[];
  topics: Option[];
  kinds: Option[];
};

function splitTopics(raw: string): string[] {
  return raw
    .split(";")
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Build the sponsor / topic / kind facet lists (with counts) from the feed. */
export function deriveGrantFilterOptions(
  grants: GrantOpportunity[],
): GrantFilterOptions {
  const sponsors = new Map<string, number>();
  const topics = new Map<string, number>();
  const kinds = new Map<string, number>();
  for (const g of grants) {
    if (g.sponsor) sponsors.set(g.sponsor, (sponsors.get(g.sponsor) ?? 0) + 1);
    for (const t of splitTopics(g.matched_topics)) {
      topics.set(t, (topics.get(t) ?? 0) + 1);
    }
    if (g.deadline_kind) {
      kinds.set(g.deadline_kind, (kinds.get(g.deadline_kind) ?? 0) + 1);
    }
  }
  const byCountThenName = (a: Option, b: Option) =>
    b.count - a.count || a.value.localeCompare(b.value);
  const toOptions = (m: Map<string, number>): Option[] =>
    [...m.entries()].map(([value, count]) => ({ value, count }));
  return {
    sponsors: toOptions(sponsors).sort(byCountThenName),
    topics: toOptions(topics).sort(byCountThenName),
    kinds: KIND_ORDER.filter((k) => kinds.has(k)).map((k) => ({
      value: k,
      count: kinds.get(k) ?? 0,
    })),
  };
}

function daysUntil(iso: string, todayIso: string): number | null {
  if (!iso || !todayIso) return null;
  const then = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const today = new Date(`${todayIso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(then.getTime()) || Number.isNaN(today.getTime())) return null;
  return Math.round((then.getTime() - today.getTime()) / 86_400_000);
}

function cmpDeadline(a: string, b: string): number {
  // Undated items sort last; ISO dates sort lexically.
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b);
}

/**
 * Apply the active filters and sort to the grants list. Pure and side-effect
 * free so it is trivially testable and cheap to run inside a `useMemo`.
 * "relevance" preserves the server order (pinned-first, then rank).
 */
export function filterAndSortGrants(
  grants: GrantOpportunity[],
  f: GrantFilterState,
  todayIso: string,
): GrantOpportunity[] {
  const matched = grants.filter((g) => {
    const pct = g.match_percent ?? 0;
    if (f.strength === "good" && pct < 50) return false;
    if (f.strength === "strong" && pct < 75) return false;

    if (f.deadline === "none") {
      if (g.deadline_date) return false;
    } else if (f.deadline !== "all") {
      const days = daysUntil(g.deadline_date, todayIso);
      const cap = f.deadline === "d7" ? 7 : f.deadline === "d30" ? 30 : 90;
      if (days === null || days < 0 || days > cap) return false;
    }

    if (f.kinds.length && !f.kinds.includes(g.deadline_kind)) return false;
    if (f.sponsors.length && !f.sponsors.includes(g.sponsor)) return false;
    if (f.topics.length) {
      const gt = splitTopics(g.matched_topics);
      // Inclusive AND: the grant must match every selected topic.
      if (!f.topics.every((t) => gt.includes(t))) return false;
    }
    if (f.newOnly && !g.is_new) return false;
    if (f.savedOnly && !g.saved) return false;
    if (f.source !== "all" && g.origin !== f.source) return false;
    return true;
  });

  if (f.sort === "deadline") {
    return [...matched].sort((a, b) =>
      cmpDeadline(a.deadline_date, b.deadline_date),
    );
  }
  if (f.sort === "posted") {
    return [...matched].sort((a, b) => (b.posted || "").localeCompare(a.posted || ""));
  }
  return matched; // relevance: keep server order
}

/** True when any facet narrows the feed (drives the "Clear all" affordance). */
export function hasActiveGrantFilters(f: GrantFilterState): boolean {
  return (
    f.strength !== "all" ||
    f.deadline !== "all" ||
    f.kinds.length > 0 ||
    f.sponsors.length > 0 ||
    f.topics.length > 0 ||
    f.newOnly ||
    f.savedOnly ||
    f.source !== "all"
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

// --------------------------------------------------------------------------- //
// UI building blocks
// --------------------------------------------------------------------------- //

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-[var(--divider)] pt-3.5 first:border-t-0 first:pt-0">
      <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </p>
      {children}
    </div>
  );
}

/**
 * A collapsible facet group. Long facet lists (Sponsor, Matched topic) start
 * collapsed so the rail stays scannable; the count of active selections shows
 * in the header while collapsed. Keyboard-operable via the native button.
 */
function CollapsibleFilterGroup({
  label,
  activeCount,
  defaultOpen = false,
  children,
}: {
  label: string;
  activeCount?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="border-t border-[var(--divider)] pt-3.5 first:border-t-0 first:pt-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
      >
        <span className="min-w-0 flex-1 text-left">{label}</span>
        {activeCount ? (
          <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold leading-none text-[#fffdf8]">
            {activeCount}
          </span>
        ) : null}
        <ChevronDownIcon
          size={13}
          aria-hidden="true"
          className={cn(
            "shrink-0 transition-transform duration-200 motion-reduce:transition-none",
            open ? "rotate-180" : "",
          )}
        />
      </button>
      {open ? <div className="mt-2">{children}</div> : null}
    </div>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="flex flex-wrap gap-1.5"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "border-primary bg-primary text-[#fffdf8]"
                : "border-border bg-surface-alt text-[var(--text-secondary)] hover:bg-surface",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function CheckRow({
  label,
  count,
  checked,
  onChange,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 py-1 text-sm text-[var(--text-secondary)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3.5 w-3.5 shrink-0 rounded border-border text-primary accent-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <span className="min-w-0 flex-1 truncate" title={label}>
        {label}
      </span>
      {typeof count === "number" ? (
        <span className="shrink-0 text-xs text-[var(--text-muted)]">{count}</span>
      ) : null}
    </label>
  );
}

/**
 * The Grants filter rail: a secondary sidebar that sits to the right of the main
 * workspace nav and to the left of the grants list. Sticky on desktop; a
 * collapsible disclosure below `lg`.
 */
export function GrantFilters({
  options,
  filters,
  onChange,
  resultCount,
  totalCount,
}: {
  options: GrantFilterOptions;
  filters: GrantFilterState;
  onChange: (next: GrantFilterState) => void;
  resultCount: number;
  totalCount: number;
}) {
  const [open, setOpen] = React.useState(false);
  const patch = (p: Partial<GrantFilterState>) => onChange({ ...filters, ...p });
  const active = hasActiveGrantFilters(filters);

  return (
    <aside className="lg:w-[236px] lg:shrink-0" aria-label="Grant filters">
      {/* Mobile: a disclosure toggle; the panel is always shown at lg+. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-3 flex w-full items-center justify-between rounded-xl border border-border bg-surface-alt px-3.5 py-2.5 text-sm font-semibold text-[var(--text-primary)] lg:hidden"
      >
        <span>Filters{active ? ` · ${resultCount}` : ""}</span>
        <span className="text-xs text-[var(--text-muted)]">
          {open ? "Hide" : "Show"}
        </span>
      </button>

      <div
        className={cn(
          "lg:sticky lg:top-0 lg:block lg:max-h-[calc(100vh-125px)] lg:overflow-y-auto",
          open ? "block" : "hidden",
        )}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {resultCount === totalCount
              ? `${totalCount} grant${totalCount === 1 ? "" : "s"}`
              : `${resultCount} of ${totalCount}`}
          </p>
          {active ? (
            <button
              type="button"
              onClick={() => onChange(DEFAULT_GRANT_FILTERS)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              <CloseIcon size={12} aria-hidden="true" />
              Clear all
            </button>
          ) : null}
        </div>

        <div className="mt-3.5 flex flex-col gap-3.5">
          <FilterGroup label="Sort by">
            <Segmented
              ariaLabel="Sort grants"
              value={filters.sort}
              onChange={(sort) => patch({ sort })}
              options={[
                { value: "relevance", label: "Best match" },
                { value: "deadline", label: "Deadline" },
                { value: "posted", label: "Newest" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Match strength">
            <Segmented
              ariaLabel="Filter by match strength"
              value={filters.strength}
              onChange={(strength) => patch({ strength })}
              options={[
                { value: "all", label: "All" },
                { value: "good", label: "≥50%" },
                { value: "strong", label: "≥75%" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Deadline">
            <Segmented
              ariaLabel="Filter by deadline window"
              value={filters.deadline}
              onChange={(deadline) => patch({ deadline })}
              options={[
                { value: "all", label: "Any" },
                { value: "d7", label: "7 days" },
                { value: "d30", label: "30 days" },
                { value: "d90", label: "90 days" },
                { value: "none", label: "Undated" },
              ]}
            />
          </FilterGroup>

          {options.kinds.length > 1 ? (
            <FilterGroup label="Deadline type">
              {options.kinds.map((k) => (
                <CheckRow
                  key={k.value}
                  label={KIND_LABELS[k.value] ?? k.value}
                  count={k.count}
                  checked={filters.kinds.includes(k.value)}
                  onChange={() => patch({ kinds: toggle(filters.kinds, k.value) })}
                />
              ))}
            </FilterGroup>
          ) : null}

          <FilterGroup label="Match source">
            <Segmented
              ariaLabel="Filter by match source"
              value={filters.source}
              onChange={(source) => patch({ source })}
              options={[
                { value: "all", label: "All" },
                { value: "llm", label: "Mylo" },
                { value: "fallback", label: "Similarity" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Show only">
            <CheckRow
              label="New this week"
              checked={filters.newOnly}
              onChange={() => patch({ newOnly: !filters.newOnly })}
            />
            <CheckRow
              label="Saved"
              checked={filters.savedOnly}
              onChange={() => patch({ savedOnly: !filters.savedOnly })}
            />
          </FilterGroup>

          {options.sponsors.length > 0 ? (
            <CollapsibleFilterGroup
              label="Sponsor"
              activeCount={filters.sponsors.length}
            >
              <div className="max-h-52 overflow-y-auto pr-1">
                {options.sponsors.map((s) => (
                  <CheckRow
                    key={s.value}
                    label={s.value}
                    count={s.count}
                    checked={filters.sponsors.includes(s.value)}
                    onChange={() =>
                      patch({ sponsors: toggle(filters.sponsors, s.value) })
                    }
                  />
                ))}
              </div>
            </CollapsibleFilterGroup>
          ) : null}

          {options.topics.length > 0 ? (
            <CollapsibleFilterGroup
              label="Matched topic"
              activeCount={filters.topics.length}
            >
              <p className="mb-1.5 text-[11px] leading-snug text-[var(--text-muted)]">
                Selecting more than one shows grants matching every topic.
              </p>
              <div className="max-h-52 overflow-y-auto pr-1">
                {options.topics.map((t) => (
                  <CheckRow
                    key={t.value}
                    label={t.value}
                    count={t.count}
                    checked={filters.topics.includes(t.value)}
                    onChange={() =>
                      patch({ topics: toggle(filters.topics, t.value) })
                    }
                  />
                ))}
              </div>
            </CollapsibleFilterGroup>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
