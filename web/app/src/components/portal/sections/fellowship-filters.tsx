"use client";

import * as React from "react";

import { ChevronDownIcon, CloseIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";
import type { FellowshipOpportunity } from "@/lib/portal/types";

/**
 * The client-side filter + sort model for the Fellowships page. The feed
 * returns the whole matched corpus in one payload; every control here narrows
 * the already-fetched list in memory — no refetch, instant.
 */
export type FellowshipSort = "fit" | "deadline" | "amount";
export type FellowshipStrength = "all" | "qualified";
export type FellowshipDeadlineWindow =
  | "any"
  | "30d"
  | "90d"
  | "rolling-only"
  | "has-deadline";

export type FellowshipFilterState = {
  sort: FellowshipSort;
  /** Eligibility tier: all / qualified (headline === "Strong eligibility match" or match_percent >= 70). */
  strength: FellowshipStrength;
  /** Deadline window filter. */
  deadline: FellowshipDeadlineWindow;
  /** Selected award types (empty = all). OR within group, AND across groups. */
  awardTypes: string[];
  /** Selected research fields (empty = all). */
  fields: string[];
  /** Selected academic stages (empty = all). */
  stages: string[];
  /** Selected citizenship requirements (empty = all). */
  citizenship: string[];
  /** Only items still inside their "New" pin window. */
  newOnly: boolean;
  /** Only items the user has saved. */
  savedOnly: boolean;
};

export const DEFAULT_FELLOWSHIP_FILTERS: FellowshipFilterState = {
  sort: "fit",
  strength: "all",
  deadline: "any",
  awardTypes: [],
  fields: [],
  stages: [],
  citizenship: [],
  newOnly: false,
  savedOnly: false,
};

type Option = { value: string; count: number };

export type FellowshipFilterOptions = {
  awardTypes: Option[];
  fields: Option[];
  stages: Option[];
  citizenship: Option[];
};

// Fixed preferred orderings for legibility — items only appear if present in the feed.
const STAGE_ORDER = [
  "masters",
  "doctoral_early",
  "doctoral_dissertation",
  "postdoc",
];
const STAGE_LABELS: Record<string, string> = {
  masters: "Master's",
  doctoral_early: "Doctoral (early)",
  doctoral_dissertation: "Doctoral (dissertation)",
  postdoc: "Postdoc",
};
const CITIZENSHIP_ORDER = ["us", "international"];
const CITIZENSHIP_LABELS: Record<string, string> = {
  us: "U.S. citizens / permanent residents",
  international: "International students",
};
const FIELD_ORDER = [
  "Social Sciences",
  "Sciences/Engineering/Math",
  "Professional Programs",
  "Fine Arts",
  "Humanities",
];

/** Count hits per facet value from the full feed. */
function countFacet(
  items: FellowshipOpportunity[],
  key: keyof Pick<
    FellowshipOpportunity,
    "fields" | "stages" | "citizenship" | "award_types"
  >,
): Map<string, number> {
  const m = new Map<string, number>();
  for (const item of items) {
    for (const v of item[key]) {
      m.set(v, (m.get(v) ?? 0) + 1);
    }
  }
  return m;
}

/** Build facet option lists with counts, in sensible fixed order. */
export function deriveFellowshipFilterOptions(
  items: FellowshipOpportunity[],
): FellowshipFilterOptions {
  const awardTypeMap = countFacet(items, "award_types");
  const fieldMap = countFacet(items, "fields");
  const stageMap = countFacet(items, "stages");
  const citizenshipMap = countFacet(items, "citizenship");

  const byCountThenName = (a: Option, b: Option) =>
    b.count - a.count || a.value.localeCompare(b.value);
  const toOptions = (m: Map<string, number>): Option[] =>
    [...m.entries()].map(([value, count]) => ({ value, count }));

  // Award types: sort by count descending
  const awardTypes = toOptions(awardTypeMap).sort(byCountThenName);

  // Fields: preserve canonical order from FIELD_ORDER; unknown fields append at end sorted
  const knownFields = FIELD_ORDER.filter((f) => fieldMap.has(f)).map((f) => ({
    value: f,
    count: fieldMap.get(f) ?? 0,
  }));
  const unknownFields = [...fieldMap.entries()]
    .filter(([v]) => !FIELD_ORDER.includes(v))
    .map(([value, count]) => ({ value, count }))
    .sort(byCountThenName);
  const fields = [...knownFields, ...unknownFields];

  // Stages: preserve canonical order
  const knownStages = STAGE_ORDER.filter((s) => stageMap.has(s)).map((s) => ({
    value: s,
    count: stageMap.get(s) ?? 0,
  }));
  const unknownStages = [...stageMap.entries()]
    .filter(([v]) => !STAGE_ORDER.includes(v))
    .map(([value, count]) => ({ value, count }))
    .sort(byCountThenName);
  const stages = [...knownStages, ...unknownStages];

  // Citizenship: canonical order
  const knownCitizenship = CITIZENSHIP_ORDER.filter((c) =>
    citizenshipMap.has(c),
  ).map((c) => ({ value: c, count: citizenshipMap.get(c) ?? 0 }));
  const unknownCitizenship = [...citizenshipMap.entries()]
    .filter(([v]) => !CITIZENSHIP_ORDER.includes(v))
    .map(([value, count]) => ({ value, count }))
    .sort(byCountThenName);
  const citizenship = [...knownCitizenship, ...unknownCitizenship];

  return { awardTypes, fields, stages, citizenship };
}

// --------------------------------------------------------------------------- //
// Pure filter + sort logic
// --------------------------------------------------------------------------- //

/** True when a deadline_type / deadline_date combination is "rolling" for filter purposes. */
function isRollingDeadline(item: FellowshipOpportunity): boolean {
  const t = item.deadline_type;
  if (t === "rolling" || t === "continuous") return true;
  // Anticipated with no usable date also treated as rolling
  if ((t === "anticipated" || t === "varies" || t === "unknown") && !item.deadline_date)
    return true;
  return false;
}

function daysUntil(iso: string, todayIso: string): number | null {
  if (!iso || !todayIso) return null;
  const then = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const today = new Date(`${todayIso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(then.getTime()) || Number.isNaN(today.getTime())) return null;
  return Math.round((then.getTime() - today.getTime()) / 86_400_000);
}

function cmpDeadline(a: FellowshipOpportunity, b: FellowshipOpportunity): number {
  // Rolling/no-date items sort last.
  const aDate = a.deadline_date;
  const bDate = b.deadline_date;
  if (!aDate && !bDate) return 0;
  if (!aDate) return 1;
  if (!bDate) return -1;
  return aDate.localeCompare(bDate);
}

/**
 * Parse a leading number from an amount string for sort purposes.
 * "$25,000 stipend" → 25000; "Up to $50k" → 50000; unknown → -1 (sort last).
 */
function parseAmountForSort(amount: string): number {
  if (!amount) return -1;
  // Strip leading non-numeric noise, then parse
  const m = amount.replace(/[,$\s]/g, "").match(/\d+(?:\.\d+)?/);
  if (!m) return -1;
  let n = parseFloat(m[0]);
  // Handle "k" suffix in original string (e.g. "$50k")
  if (/\d\s*k/i.test(amount)) n *= 1000;
  return n;
}

/**
 * Apply the active filters and sort to the fellowships list. Pure and side-effect
 * free — safe inside a `useMemo`.
 */
export function filterAndSortFellowships(
  items: FellowshipOpportunity[],
  f: FellowshipFilterState,
  todayIso: string,
): FellowshipOpportunity[] {
  const matched = items.filter((item) => {
    // Eligibility strength: "qualified" means headline === "Strong eligibility match"
    // OR match_percent >= 70 (whichever is present).
    if (f.strength === "qualified") {
      const byHeadline = item.headline === "Strong eligibility match";
      const byPct = typeof item.match_percent === "number" && item.match_percent >= 70;
      if (!byHeadline && !byPct) return false;
    }

    // Deadline window
    if (f.deadline === "rolling-only") {
      if (!isRollingDeadline(item)) return false;
    } else if (f.deadline === "has-deadline") {
      if (!item.deadline_date || isRollingDeadline(item)) return false;
    } else if (f.deadline === "30d") {
      const days = daysUntil(item.deadline_date, todayIso);
      if (days === null || days < 0 || days > 30) return false;
    } else if (f.deadline === "90d") {
      const days = daysUntil(item.deadline_date, todayIso);
      if (days === null || days < 0 || days > 90) return false;
    }
    // "any" passes all

    // Facet groups: OR within a group, AND across groups
    if (
      f.awardTypes.length > 0 &&
      !item.award_types.some((v) => f.awardTypes.includes(v))
    )
      return false;
    if (f.fields.length > 0 && !item.fields.some((v) => f.fields.includes(v)))
      return false;
    if (f.stages.length > 0 && !item.stages.some((v) => f.stages.includes(v)))
      return false;
    if (
      f.citizenship.length > 0 &&
      !item.citizenship.some((v) => f.citizenship.includes(v))
    )
      return false;

    if (f.newOnly && !item.is_new) return false;
    if (f.savedOnly && !item.saved) return false;

    return true;
  });

  if (f.sort === "deadline") {
    return [...matched].sort(cmpDeadline);
  }
  if (f.sort === "amount") {
    return [...matched].sort(
      (a, b) => parseAmountForSort(b.amount) - parseAmountForSort(a.amount),
    );
  }
  // "fit": keep server order (score desc, pinned-first)
  return matched;
}

/** True when any facet narrows the feed (drives the "Clear all" affordance). */
export function hasActiveFellowshipFilters(f: FellowshipFilterState): boolean {
  return (
    f.strength !== "all" ||
    f.deadline !== "any" ||
    f.awardTypes.length > 0 ||
    f.fields.length > 0 ||
    f.stages.length > 0 ||
    f.citizenship.length > 0 ||
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
// UI building blocks (shared with grant-filters visual language)
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
 * The Fellowships filter rail: sticky on desktop; a collapsible disclosure
 * below `lg`. Same interaction pattern as GrantFilters.
 */
export function FellowshipFilters({
  options,
  filters,
  onChange,
  resultCount,
  totalCount,
}: {
  options: FellowshipFilterOptions;
  filters: FellowshipFilterState;
  onChange: (next: FellowshipFilterState) => void;
  resultCount: number;
  totalCount: number;
}) {
  const [open, setOpen] = React.useState(false);
  const patch = (p: Partial<FellowshipFilterState>) =>
    onChange({ ...filters, ...p });
  const active = hasActiveFellowshipFilters(filters);

  // Active-filter count for the mobile toggle label
  const activeGroupCount = [
    filters.strength !== "all",
    filters.deadline !== "any",
    filters.awardTypes.length > 0,
    filters.fields.length > 0,
    filters.stages.length > 0,
    filters.citizenship.length > 0,
    filters.newOnly,
    filters.savedOnly,
  ].filter(Boolean).length;

  return (
    <aside className="lg:w-[236px] lg:shrink-0" aria-label="Fellowship filters">
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
          "lg:sticky lg:top-0 lg:block lg:max-h-[calc(100vh-125px)] lg:overflow-y-auto",
          open ? "block" : "hidden",
        )}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {resultCount === totalCount
              ? `${totalCount} fellowship${totalCount === 1 ? "" : "s"}`
              : `${resultCount} of ${totalCount}`}
          </p>
          {active ? (
            <button
              type="button"
              onClick={() => onChange(DEFAULT_FELLOWSHIP_FILTERS)}
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
              ariaLabel="Sort fellowships"
              value={filters.sort}
              onChange={(sort) => patch({ sort })}
              options={[
                { value: "fit", label: "Best fit" },
                { value: "deadline", label: "Deadline" },
                { value: "amount", label: "Amount" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Eligibility">
            <Segmented
              ariaLabel="Filter by eligibility tier"
              value={filters.strength}
              onChange={(strength) => patch({ strength })}
              options={[
                { value: "all", label: "All" },
                { value: "qualified", label: "Qualified" },
              ]}
            />
          </FilterGroup>

          <FilterGroup label="Deadline">
            <Segmented
              ariaLabel="Filter by deadline window"
              value={filters.deadline}
              onChange={(deadline) => patch({ deadline })}
              options={[
                { value: "any", label: "Any" },
                { value: "30d", label: "30 days" },
                { value: "90d", label: "90 days" },
                { value: "has-deadline", label: "Has date" },
                { value: "rolling-only", label: "Rolling" },
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

          {options.fields.length > 0 ? (
            <CollapsibleFilterGroup
              label="Research field"
              activeCount={filters.fields.length}
            >
              <div className="max-h-52 overflow-y-auto pr-1">
                {options.fields.map((f) => (
                  <CheckRow
                    key={f.value}
                    label={f.value}
                    count={f.count}
                    checked={filters.fields.includes(f.value)}
                    onChange={() =>
                      patch({ fields: toggle(filters.fields, f.value) })
                    }
                  />
                ))}
              </div>
            </CollapsibleFilterGroup>
          ) : null}

          {options.stages.length > 0 ? (
            <CollapsibleFilterGroup
              label="Academic stage"
              activeCount={filters.stages.length}
            >
              {options.stages.map((s) => (
                <CheckRow
                  key={s.value}
                  label={STAGE_LABELS[s.value] ?? s.value}
                  count={s.count}
                  checked={filters.stages.includes(s.value)}
                  onChange={() =>
                    patch({ stages: toggle(filters.stages, s.value) })
                  }
                />
              ))}
            </CollapsibleFilterGroup>
          ) : null}

          {options.citizenship.length > 0 ? (
            <CollapsibleFilterGroup
              label="Citizenship"
              activeCount={filters.citizenship.length}
            >
              {options.citizenship.map((c) => (
                <CheckRow
                  key={c.value}
                  label={CITIZENSHIP_LABELS[c.value] ?? c.value}
                  count={c.count}
                  checked={filters.citizenship.includes(c.value)}
                  onChange={() =>
                    patch({ citizenship: toggle(filters.citizenship, c.value) })
                  }
                />
              ))}
            </CollapsibleFilterGroup>
          ) : null}

          {options.awardTypes.length > 0 ? (
            <CollapsibleFilterGroup
              label="Award type"
              activeCount={filters.awardTypes.length}
            >
              {options.awardTypes.map((a) => (
                <CheckRow
                  key={a.value}
                  label={a.value}
                  count={a.count}
                  checked={filters.awardTypes.includes(a.value)}
                  onChange={() =>
                    patch({ awardTypes: toggle(filters.awardTypes, a.value) })
                  }
                />
              ))}
            </CollapsibleFilterGroup>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
