"use client";

import * as React from "react";

import { ChevronDownIcon, CloseIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";
import type { ConferenceOpportunity } from "@/lib/portal/types";

/**
 * The client-side filter + sort model for the Conferences page. The feed returns
 * the whole matched corpus in one payload; every control here narrows the
 * already-fetched list in memory — no refetch, instant. Mirrors the Fellowships
 * and Grants filter rails.
 */
export type ConferenceSort = "fit" | "deadline" | "event";
export type ConferenceStatus = "any" | "open" | "closed";
export type ConferenceDeadlineWindow = "any" | "30d" | "90d" | "has-date";
export type ConferenceEventWindow = "any" | "3m" | "6m" | "upcoming";

export type ConferenceFilterState = {
  sort: ConferenceSort;
  /** Submission window state: any / open / closed. */
  status: ConferenceStatus;
  /** Only venues still accepting abstracts. */
  abstractOpen: boolean;
  /** Only venues still accepting full papers (manuscripts). */
  paperOpen: boolean;
  /** Submission-deadline window filter (uses the next actionable deadline). */
  deadline: ConferenceDeadlineWindow;
  /** Event-date window filter (when the conference itself happens). */
  event: ConferenceEventWindow;
  /** Selected continents (empty = all). Derived from country. */
  continents: string[];
  /** Selected countries (empty = all). */
  countries: string[];
  /** Selected subject categories (empty = all). */
  subjects: string[];
  /** Only items still inside their "New" pin window. */
  newOnly: boolean;
  /** Only items the user has saved. */
  savedOnly: boolean;
};

export const DEFAULT_CONFERENCE_FILTERS: ConferenceFilterState = {
  sort: "fit",
  status: "any",
  abstractOpen: false,
  paperOpen: false,
  deadline: "any",
  event: "any",
  continents: [],
  countries: [],
  subjects: [],
  newOnly: false,
  savedOnly: false,
};

type Option = { value: string; count: number };

export type ConferenceFilterOptions = {
  continents: Option[];
  countries: Option[];
  subjects: Option[];
};

// --------------------------------------------------------------------------- //
// Country → continent lookup
// --------------------------------------------------------------------------- //

const CONTINENT_ORDER = [
  "North America",
  "Europe",
  "Asia",
  "Oceania",
  "South America",
  "Africa",
  "Other",
];

/**
 * A bounded country-name → continent map. Pivot emits full country names, so we
 * key on those (lower-cased). Anything unrecognized falls through to "Other" —
 * still filterable, just not bucketed to a specific continent.
 */
const COUNTRY_TO_CONTINENT: Record<string, string> = {
  // North America
  "united states": "North America",
  "united states of america": "North America",
  usa: "North America",
  canada: "North America",
  mexico: "North America",
  "costa rica": "North America",
  panama: "North America",
  cuba: "North America",
  jamaica: "North America",
  // Europe
  "united kingdom": "Europe",
  uk: "Europe",
  england: "Europe",
  scotland: "Europe",
  wales: "Europe",
  ireland: "Europe",
  germany: "Europe",
  france: "Europe",
  spain: "Europe",
  portugal: "Europe",
  italy: "Europe",
  netherlands: "Europe",
  belgium: "Europe",
  switzerland: "Europe",
  austria: "Europe",
  sweden: "Europe",
  norway: "Europe",
  denmark: "Europe",
  finland: "Europe",
  iceland: "Europe",
  poland: "Europe",
  "czech republic": "Europe",
  czechia: "Europe",
  slovakia: "Europe",
  hungary: "Europe",
  greece: "Europe",
  romania: "Europe",
  bulgaria: "Europe",
  croatia: "Europe",
  serbia: "Europe",
  slovenia: "Europe",
  estonia: "Europe",
  latvia: "Europe",
  lithuania: "Europe",
  ukraine: "Europe",
  russia: "Europe",
  "russian federation": "Europe",
  turkey: "Europe",
  cyprus: "Europe",
  luxembourg: "Europe",
  malta: "Europe",
  // Asia
  china: "Asia",
  japan: "Asia",
  "south korea": "Asia",
  "korea, republic of": "Asia",
  "republic of korea": "Asia",
  india: "Asia",
  singapore: "Asia",
  malaysia: "Asia",
  indonesia: "Asia",
  thailand: "Asia",
  vietnam: "Asia",
  philippines: "Asia",
  taiwan: "Asia",
  "hong kong": "Asia",
  pakistan: "Asia",
  bangladesh: "Asia",
  "sri lanka": "Asia",
  nepal: "Asia",
  "united arab emirates": "Asia",
  "saudi arabia": "Asia",
  qatar: "Asia",
  israel: "Asia",
  jordan: "Asia",
  lebanon: "Asia",
  iran: "Asia",
  iraq: "Asia",
  kazakhstan: "Asia",
  // Oceania
  australia: "Oceania",
  "new zealand": "Oceania",
  fiji: "Oceania",
  // South America
  brazil: "South America",
  argentina: "South America",
  chile: "South America",
  colombia: "South America",
  peru: "South America",
  ecuador: "South America",
  uruguay: "South America",
  venezuela: "South America",
  bolivia: "South America",
  paraguay: "South America",
  // Africa
  "south africa": "Africa",
  egypt: "Africa",
  nigeria: "Africa",
  kenya: "Africa",
  morocco: "Africa",
  tunisia: "Africa",
  algeria: "Africa",
  ghana: "Africa",
  ethiopia: "Africa",
  tanzania: "Africa",
  uganda: "Africa",
};

/** Continent for a country string, or "Other" when unknown/blank. */
export function continentOf(country: string): string {
  const key = (country || "").trim().toLowerCase();
  if (!key) return "Other";
  return COUNTRY_TO_CONTINENT[key] ?? "Other";
}

/** Split the semicolon-delimited matched_subjects blob into clean tags. */
function subjectTags(conf: ConferenceOpportunity): string[] {
  return conf.matched_subjects
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
}

// --------------------------------------------------------------------------- //
// Facet option derivation
// --------------------------------------------------------------------------- //

/** Build facet option lists with counts, in sensible order. */
export function deriveConferenceFilterOptions(
  items: ConferenceOpportunity[],
): ConferenceFilterOptions {
  const continentMap = new Map<string, number>();
  const countryMap = new Map<string, number>();
  const subjectMap = new Map<string, number>();

  for (const conf of items) {
    const country = (conf.country || "").trim();
    if (country) {
      countryMap.set(country, (countryMap.get(country) ?? 0) + 1);
    }
    // Continent buckets every item (unknown/blank → "Other").
    const continent = continentOf(country);
    continentMap.set(continent, (continentMap.get(continent) ?? 0) + 1);
    for (const subject of subjectTags(conf)) {
      subjectMap.set(subject, (subjectMap.get(subject) ?? 0) + 1);
    }
  }

  const byCountThenName = (a: Option, b: Option) =>
    b.count - a.count || a.value.localeCompare(b.value);

  // Continents: canonical order, only those present.
  const continents = CONTINENT_ORDER.filter((c) => continentMap.has(c)).map(
    (c) => ({ value: c, count: continentMap.get(c) ?? 0 }),
  );

  const countries = [...countryMap.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort(byCountThenName);

  const subjects = [...subjectMap.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort(byCountThenName);

  return { continents, countries, subjects };
}

// --------------------------------------------------------------------------- //
// Pure filter + sort logic
// --------------------------------------------------------------------------- //

function daysUntil(iso: string, todayIso: string): number | null {
  if (!iso || !todayIso) return null;
  const then = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const today = new Date(`${todayIso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(then.getTime()) || Number.isNaN(today.getTime())) return null;
  return Math.round((then.getTime() - today.getTime()) / 86_400_000);
}

/** Sort by an ISO date field ascending; empty/unparseable dates sort last. */
function cmpIsoAsc(a: string, b: string): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b);
}

/**
 * Apply the active filters and sort to the conferences list. Pure and
 * side-effect free — safe inside a `useMemo`.
 */
export function filterAndSortConferences(
  items: ConferenceOpportunity[],
  f: ConferenceFilterState,
  todayIso: string,
): ConferenceOpportunity[] {
  const matched = items.filter((conf) => {
    // Submission status
    if (f.status === "open" && conf.status !== "open") return false;
    if (f.status === "closed" && conf.status !== "closed") return false;

    // Open-submission toggles (AND — both must hold when both are set)
    if (f.abstractOpen && !conf.abstract_open) return false;
    if (f.paperOpen && !conf.manuscript_open) return false;

    // Submission-deadline window (next actionable deadline)
    if (f.deadline === "has-date") {
      if (!conf.deadline_date) return false;
    } else if (f.deadline === "30d") {
      const d = daysUntil(conf.deadline_date, todayIso);
      if (d === null || d < 0 || d > 30) return false;
    } else if (f.deadline === "90d") {
      const d = daysUntil(conf.deadline_date, todayIso);
      if (d === null || d < 0 || d > 90) return false;
    }

    // Event-date window (when the conference happens)
    if (f.event === "upcoming") {
      const d = daysUntil(conf.event_date, todayIso);
      if (d === null || d < 0) return false;
    } else if (f.event === "3m") {
      const d = daysUntil(conf.event_date, todayIso);
      if (d === null || d < 0 || d > 92) return false;
    } else if (f.event === "6m") {
      const d = daysUntil(conf.event_date, todayIso);
      if (d === null || d < 0 || d > 183) return false;
    }

    // Location facets: OR within a group, AND across groups
    if (
      f.continents.length > 0 &&
      !f.continents.includes(continentOf(conf.country))
    )
      return false;
    if (f.countries.length > 0 && !f.countries.includes((conf.country || "").trim()))
      return false;

    // Subject facet
    if (
      f.subjects.length > 0 &&
      !subjectTags(conf).some((s) => f.subjects.includes(s))
    )
      return false;

    if (f.newOnly && !conf.is_new) return false;
    if (f.savedOnly && !conf.saved) return false;

    return true;
  });

  if (f.sort === "deadline") {
    return [...matched].sort((a, b) =>
      cmpIsoAsc(a.deadline_date, b.deadline_date),
    );
  }
  if (f.sort === "event") {
    return [...matched].sort((a, b) => cmpIsoAsc(a.event_date, b.event_date));
  }
  // "fit": keep server order (score desc, pinned-first)
  return matched;
}

/** True when any facet narrows the feed (drives the "Clear all" affordance). */
export function hasActiveConferenceFilters(f: ConferenceFilterState): boolean {
  return (
    f.status !== "any" ||
    f.abstractOpen ||
    f.paperOpen ||
    f.deadline !== "any" ||
    f.event !== "any" ||
    f.continents.length > 0 ||
    f.countries.length > 0 ||
    f.subjects.length > 0 ||
    f.newOnly ||
    f.savedOnly
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

// --------------------------------------------------------------------------- //
// UI building blocks (shared visual language with grant/fellowship filters)
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
        className="flex w-full items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]"
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
 * The Conferences filter rail: sticky on desktop; a collapsible disclosure
 * below `lg`. Same interaction pattern as GrantFilters / FellowshipFilters.
 */
export function ConferenceFilters({
  options,
  filters,
  onChange,
  resultCount,
  totalCount,
}: {
  options: ConferenceFilterOptions;
  filters: ConferenceFilterState;
  onChange: (next: ConferenceFilterState) => void;
  resultCount: number;
  totalCount: number;
}) {
  const [open, setOpen] = React.useState(false);
  const patch = (p: Partial<ConferenceFilterState>) =>
    onChange({ ...filters, ...p });
  const active = hasActiveConferenceFilters(filters);

  // Active-filter count for the mobile toggle label
  const activeGroupCount = [
    filters.status !== "any",
    filters.abstractOpen,
    filters.paperOpen,
    filters.deadline !== "any",
    filters.event !== "any",
    filters.continents.length > 0,
    filters.countries.length > 0,
    filters.subjects.length > 0,
    filters.newOnly,
    filters.savedOnly,
  ].filter(Boolean).length;

  return (
    <aside className="lg:w-[236px] lg:shrink-0" aria-label="Conference filters">
      {/* Mobile: a disclosure toggle; the panel is always shown at lg+. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-3 flex w-full items-center justify-between rounded-xl border border-border bg-surface-alt px-3.5 py-2.5 text-sm font-semibold text-[var(--text-primary)] lg:hidden"
      >
        <span>
          Filters
          {active ? ` · ${activeGroupCount} active` : ""}
        </span>
        <span className="text-xs text-[var(--text-secondary)]">
          {open ? "Hide" : "Show"}
        </span>
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
              ? `${totalCount} conference${totalCount === 1 ? "" : "s"}`
              : `${resultCount} of ${totalCount}`}
          </p>
          {active ? (
            <button
              type="button"
              onClick={() => onChange(DEFAULT_CONFERENCE_FILTERS)}
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
              ariaLabel="Sort conferences"
              value={filters.sort}
              onChange={(sort) => patch({ sort })}
              options={[
                { value: "fit", label: "Best fit" },
                { value: "deadline", label: "Deadline" },
                { value: "event", label: "Event date" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Submissions">
            <Segmented
              ariaLabel="Filter by submission status"
              value={filters.status}
              onChange={(status) => patch({ status })}
              options={[
                { value: "any", label: "Any" },
                { value: "open", label: "Open" },
                { value: "closed", label: "Closed" },
              ]}
            />
            <div className="mt-1.5">
              <CheckRow
                label="Abstract open"
                checked={filters.abstractOpen}
                onChange={() => patch({ abstractOpen: !filters.abstractOpen })}
              />
              <CheckRow
                label="Full paper open"
                checked={filters.paperOpen}
                onChange={() => patch({ paperOpen: !filters.paperOpen })}
              />
            </div>
          </FilterGroup>

          <FilterGroup label="Submission deadline">
            <Segmented
              ariaLabel="Filter by submission deadline window"
              value={filters.deadline}
              onChange={(deadline) => patch({ deadline })}
              options={[
                { value: "any", label: "Any" },
                { value: "30d", label: "30 days" },
                { value: "90d", label: "90 days" },
                { value: "has-date", label: "Has date" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Event date">
            <Segmented
              ariaLabel="Filter by event date window"
              value={filters.event}
              onChange={(event) => patch({ event })}
              options={[
                { value: "any", label: "Any" },
                { value: "3m", label: "3 months" },
                { value: "6m", label: "6 months" },
                { value: "upcoming", label: "Upcoming" },
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

          {options.continents.length > 0 ? (
            <CollapsibleFilterGroup
              label="Continent"
              activeCount={filters.continents.length}
            >
              {options.continents.map((c) => (
                <CheckRow
                  key={c.value}
                  label={c.value}
                  count={c.count}
                  checked={filters.continents.includes(c.value)}
                  onChange={() =>
                    patch({ continents: toggle(filters.continents, c.value) })
                  }
                />
              ))}
            </CollapsibleFilterGroup>
          ) : null}

          {options.countries.length > 0 ? (
            <CollapsibleFilterGroup
              label="Country"
              activeCount={filters.countries.length}
            >
              <div className="max-h-52 overflow-y-auto pr-1">
                {options.countries.map((c) => (
                  <CheckRow
                    key={c.value}
                    label={c.value}
                    count={c.count}
                    checked={filters.countries.includes(c.value)}
                    onChange={() =>
                      patch({ countries: toggle(filters.countries, c.value) })
                    }
                  />
                ))}
              </div>
            </CollapsibleFilterGroup>
          ) : null}

          {options.subjects.length > 0 ? (
            <CollapsibleFilterGroup
              label="Subject"
              activeCount={filters.subjects.length}
            >
              <div className="max-h-52 overflow-y-auto pr-1">
                {options.subjects.map((s) => (
                  <CheckRow
                    key={s.value}
                    label={s.value}
                    count={s.count}
                    checked={filters.subjects.includes(s.value)}
                    onChange={() =>
                      patch({ subjects: toggle(filters.subjects, s.value) })
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
