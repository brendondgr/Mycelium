"use client";

import * as React from "react";

import { ChevronDownIcon, CloseIcon, SearchIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";
import type { SavedArea, SavedItem } from "@/lib/portal/types";

/**
 * The client-side filter + sort model for the Saves page. The saves feed
 * returns every bookmark in one payload, so every control here narrows an
 * already-fetched list in memory — no refetch, instant. Mirrors the grant /
 * fellowship / conference filter rails, plus a free-text search box since a
 * saves list mixes all four kinds.
 */
export type SavesSort = "saved" | "deadline" | "match" | "title";
export type SavesDeadline = "all" | "d7" | "d30" | "d90" | "none";

export type SavesFilterState = {
  /** Free-text search over titles, subtitles, notes, and card blurbs. */
  query: string;
  /** Selected kinds (empty = all four). */
  areas: SavedArea[];
  /** Deadline window from today, or "none" for undated saves (papers). */
  deadline: SavesDeadline;
  /** Only saves whose deadline falls within the next week. */
  dueSoonOnly: boolean;
  sort: SavesSort;
};

export const DEFAULT_SAVES_FILTERS: SavesFilterState = {
  query: "",
  areas: [],
  deadline: "all",
  dueSoonOnly: false,
  sort: "saved",
};

/** Human labels for the kind facet, in display order. */
export const AREA_LABELS: Record<SavedArea, string> = {
  paper: "Research papers",
  grant: "Grants",
  fellowship: "Fellowships",
  conference: "Conferences",
};
const AREA_ORDER: SavedArea[] = ["paper", "grant", "fellowship", "conference"];

type Option = { value: SavedArea; count: number };
export type SavesFilterOptions = {
  areas: Option[];
};

/** Build the kind facet list (with counts) from the saves feed. */
export function deriveSavesFilterOptions(items: SavedItem[]): SavesFilterOptions {
  const counts = new Map<SavedArea, number>();
  for (const item of items) {
    counts.set(item.area, (counts.get(item.area) ?? 0) + 1);
  }
  return {
    areas: AREA_ORDER.filter((a) => counts.has(a)).map((a) => ({
      value: a,
      count: counts.get(a) ?? 0,
    })),
  };
}

/** The text a free-text query searches over, per save (lowercased once). */
function searchableText(item: SavedItem): string {
  const parts: string[] = [item.title, item.subtitle, item.note];
  const card = item.card;
  if (card) {
    if ("sponsor" in card) parts.push(card.sponsor, card.description);
    if ("venue" in card) parts.push(card.venue, card.abstract, ...card.authors);
    if ("location" in card) parts.push(card.location, card.matched_subjects);
    if ("award_class" in card) {
      parts.push(card.award_class, card.description, ...card.fields);
    }
    parts.push(card.reason ?? "");
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}

/** A save's percent match (from its card), for the match sort. */
function matchPercent(item: SavedItem): number {
  const card = item.card;
  if (!card) return -1;
  return card.match_percent ?? card.embedding_match ?? -1;
}

/**
 * Apply the active filters and sort to the saves list. Pure and side-effect
 * free so it is trivially testable and cheap to run inside a `useMemo`.
 * "saved" preserves the server order (newest save first).
 */
export function filterAndSortSaves(
  items: SavedItem[],
  f: SavesFilterState,
): SavedItem[] {
  const query = f.query.trim().toLowerCase();
  const matched = items.filter((item) => {
    if (f.areas.length && !f.areas.includes(item.area)) return false;

    if (f.deadline === "none") {
      if (item.deadline_date) return false;
    } else if (f.deadline !== "all") {
      const days = item.days_remaining;
      const cap = f.deadline === "d7" ? 7 : f.deadline === "d30" ? 30 : 90;
      if (days === null || days < 0 || days > cap) return false;
    }

    if (f.dueSoonOnly && !item.within_week) return false;
    if (query && !searchableText(item).includes(query)) return false;
    return true;
  });

  if (f.sort === "deadline") {
    // Soonest deadline first; undated saves (papers) sort last.
    return [...matched].sort((a, b) => {
      if (a.deadline_date === b.deadline_date) return 0;
      if (!a.deadline_date) return 1;
      if (!b.deadline_date) return -1;
      return a.deadline_date.localeCompare(b.deadline_date);
    });
  }
  if (f.sort === "match") {
    return [...matched].sort((a, b) => matchPercent(b) - matchPercent(a));
  }
  if (f.sort === "title") {
    return [...matched].sort((a, b) => a.title.localeCompare(b.title));
  }
  return matched; // saved: keep server order (newest save first)
}

/** True when any control narrows the feed (drives the "Clear all" affordance). */
export function hasActiveSavesFilters(f: SavesFilterState): boolean {
  return (
    f.query.trim() !== "" ||
    f.areas.length > 0 ||
    f.deadline !== "all" ||
    f.dueSoonOnly
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

// --------------------------------------------------------------------------- //
// UI building blocks (matches the grant/fellowship/conference filter rails)
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
      <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        {label}
      </p>
      {children}
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
    <div role="group" aria-label={ariaLabel} className="flex flex-wrap gap-1.5">
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
        <span className="shrink-0 text-xs text-[var(--text-secondary)]">{count}</span>
      ) : null}
    </label>
  );
}

/**
 * The Saves filter rail: search box, kind facet, deadline window, and sort.
 * Sticky on desktop; a collapsible disclosure below `lg` — same chrome as the
 * grant / fellowship / conference rails.
 */
export function SavesFilters({
  options,
  filters,
  onChange,
  resultCount,
  totalCount,
}: {
  options: SavesFilterOptions;
  filters: SavesFilterState;
  onChange: (next: SavesFilterState) => void;
  resultCount: number;
  totalCount: number;
}) {
  const [open, setOpen] = React.useState(false);
  const patch = (p: Partial<SavesFilterState>) => onChange({ ...filters, ...p });
  const active = hasActiveSavesFilters(filters);

  return (
    <aside className="lg:w-[236px] lg:shrink-0" aria-label="Saves filters">
      {/* Mobile: a disclosure toggle; the panel is always shown at lg+. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-3 flex w-full items-center justify-between rounded-xl border border-border bg-surface-alt px-3.5 py-2.5 text-sm font-semibold text-[var(--text-primary)] lg:hidden"
      >
        <span>Filters{active ? ` · ${resultCount}` : ""}</span>
        <span className="text-xs text-[var(--text-secondary)]">
          {open ? "Hide" : "Show"}
        </span>
        <ChevronDownIcon
          size={13}
          aria-hidden="true"
          className={cn(
            "shrink-0 transition-transform duration-200 motion-reduce:transition-none",
            open ? "rotate-180" : "",
          )}
        />
      </button>

      <div
        className={cn(
          "lg:sticky lg:top-0 lg:block lg:max-h-[calc(100vh-125px)] lg:overflow-y-auto lg:pr-2.5",
          open ? "block" : "hidden",
        )}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {resultCount === totalCount
              ? `${totalCount} save${totalCount === 1 ? "" : "s"}`
              : `${resultCount} of ${totalCount}`}
          </p>
          {active ? (
            <button
              type="button"
              onClick={() => onChange(DEFAULT_SAVES_FILTERS)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              <CloseIcon size={12} aria-hidden="true" />
              Clear all
            </button>
          ) : null}
        </div>

        <div className="mt-3.5 flex flex-col gap-3.5">
          <FilterGroup label="Search">
            <div className="relative">
              <SearchIcon
                size={14}
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)]"
              />
              <input
                type="search"
                value={filters.query}
                onChange={(e) => patch({ query: e.target.value })}
                placeholder="Search your saves…"
                aria-label="Search your saves"
                className="w-full rounded-full border border-border bg-surface py-1.5 pl-8 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </FilterGroup>

          <FilterGroup label="Sort by">
            <Segmented
              ariaLabel="Sort saves"
              value={filters.sort}
              onChange={(sort) => patch({ sort })}
              options={[
                { value: "saved", label: "Recently saved" },
                { value: "deadline", label: "Deadline" },
                { value: "match", label: "Best match" },
                { value: "title", label: "A–Z" },
              ]}
            />
          </FilterGroup>

          {options.areas.length > 1 ? (
            <FilterGroup label="Kind">
              {options.areas.map((a) => (
                <CheckRow
                  key={a.value}
                  label={AREA_LABELS[a.value]}
                  count={a.count}
                  checked={filters.areas.includes(a.value)}
                  onChange={() => patch({ areas: toggle(filters.areas, a.value) })}
                />
              ))}
            </FilterGroup>
          ) : null}

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

          <FilterGroup label="Show only">
            <CheckRow
              label="Due within a week"
              checked={filters.dueSoonOnly}
              onChange={() => patch({ dueSoonOnly: !filters.dueSoonOnly })}
            />
          </FilterGroup>
        </div>
      </div>
    </aside>
  );
}
