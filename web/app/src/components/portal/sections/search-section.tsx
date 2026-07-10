"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { SearchIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { SearchResultCard } from "@/components/portal/sections/search-result-card";
import { useSearchResults } from "@/lib/portal/hooks";
import type {
  SearchContentType,
  SearchFacetBucket,
  SearchFacets,
  SearchSort,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const SORTS: { value: SearchSort; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "date", label: "Newest" },
  { value: "deadline", label: "Deadline" },
];

const TYPE_LABELS: Record<string, string> = {
  paper: "Papers",
  grant: "Grants",
  fellowship: "Fellowships",
  conference: "Conferences",
};

/** The per-type facet field + its rail title (one scalar filter per type). */
const PER_TYPE_FACET: Record<
  SearchContentType,
  { key: keyof SearchFacets & string; title: string }
> = {
  paper: { key: "year", title: "Year" },
  grant: { key: "sponsor", title: "Sponsor" },
  fellowship: { key: "award_class", title: "Award type" },
  conference: { key: "country", title: "Country" },
};

/** Every per-type facet URL param — cleared together with the type selection. */
const FACET_KEYS = ["year", "sponsor", "award_class", "country"] as const;

function isSort(value: string | null): value is SearchSort {
  return value === "relevance" || value === "date" || value === "deadline";
}

/** Award-class values are snake tokens ("award_class" → "Award"); prettify them. */
function titleCase(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SearchSection() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const q = params.get("q") ?? "";
  const types = params.getAll("type");
  const facetFilters: Record<string, string[]> = React.useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const key of FACET_KEYS) {
      const values = params.getAll(key);
      if (values.length) map[key] = values;
    }
    return map;
  }, [params]);
  const sort: SearchSort = isSort(params.get("sort"))
    ? (params.get("sort") as SearchSort)
    : "relevance";

  // The text box is local; a debounce writes it to the URL (the source of truth
  // for the query, so a search is shareable/bookmarkable). When `q` changes
  // externally (e.g. the header search navigates here with a new query) we adopt
  // it into the box by adjusting state during render — the React-recommended
  // alternative to a setState-in-effect.
  const [text, setText] = React.useState(q);
  const [syncedQuery, setSyncedQuery] = React.useState(q);
  if (q !== syncedQuery) {
    setSyncedQuery(q);
    setText(q);
  }

  const updateParams = React.useCallback(
    (mutate: (sp: URLSearchParams) => void) => {
      const sp = new URLSearchParams(Array.from(params.entries()));
      mutate(sp);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  React.useEffect(() => {
    if (text.trim() === q) return;
    const id = setTimeout(() => {
      updateParams((sp) => {
        const value = text.trim();
        if (value) sp.set("q", value);
        else sp.delete("q");
      });
    }, 250);
    return () => clearTimeout(id);
  }, [text, q, updateParams]);

  const toggleValue = (sp: URLSearchParams, key: string, value: string) => {
    const current = sp.getAll(key);
    sp.delete(key);
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value];
    next.forEach((entry) => sp.append(key, entry));
  };

  // A per-type facet only makes sense inside one type, so toggling the type also
  // clears any per-type facet selection — otherwise a stale year/sponsor filter
  // would silently scope results after the user switched types.
  const toggleType = (value: string) => {
    updateParams((sp) => {
      FACET_KEYS.forEach((key) => sp.delete(key));
      toggleValue(sp, "type", value);
    });
  };

  const toggleFacet = (key: string, value: string) => {
    updateParams((sp) => toggleValue(sp, key, value));
  };

  const setSort = (value: SearchSort) => {
    updateParams((sp) => {
      if (value === "relevance") sp.delete("sort");
      else sp.set("sort", value);
    });
  };

  const clearFilters = () => {
    updateParams((sp) => {
      sp.delete("type");
      FACET_KEYS.forEach((key) => sp.delete(key));
    });
  };

  const query = useSearchResults({ q, types, facetFilters, sort });
  const pages = query.data?.pages ?? [];
  const first = pages[0];
  const results = pages.flatMap((page) => page.results);
  const facets: SearchFacets = first?.facets ?? { type: [] };
  const count = first?.count ?? 0;
  const confidence = first?.confidence ?? "ok";
  const poolTruncated = first?.pool_truncated ?? false;

  // The contextual per-type facet: shown only when exactly one type is active
  // (the backend returns its bucket under that key only then).
  const activeType =
    types.length === 1 ? (types[0] as SearchContentType) : null;
  const perType =
    activeType && PER_TYPE_FACET[activeType]
      ? PER_TYPE_FACET[activeType]
      : null;
  const perTypeBuckets = perType ? (facets[perType.key] ?? []) : [];

  const hasQuery = q.trim().length > 0;
  const hasFilters =
    types.length > 0 || FACET_KEYS.some((key) => facetFilters[key]?.length);

  const subtitle = !hasQuery
    ? "Search across papers, grants, fellowships, and conferences."
    : query.isLoading
      ? "Searching…"
      : `${count.toLocaleString()} result${count === 1 ? "" : "s"} for “${q}”${
          poolTruncated ? " (top matches)" : ""
        }`;

  return (
    <div className="portal-fade-up">
      <SectionHeader title="Search" subtitle={subtitle} />

      {/* Query box + sort */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Search the content library</span>
          <SearchIcon
            size={16}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            autoFocus
            placeholder="Search papers, grants, fellowships, conferences…"
            className="w-full rounded-full border border-border bg-surface py-2.5 pl-10 pr-4 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring placeholder:text-[var(--text-muted)]"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <span className="hidden sm:inline">Sort</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SearchSort)}
            className="rounded-full border border-border bg-surface px-3.5 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!hasQuery ? (
        <EmptyState
          icon={<SearchIcon size={24} />}
          title="What are you looking for?"
          description="Search the whole content library by keyword or concept — an exact title, an author, a funding topic, or an idea in your own words."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          {/* Filters — sticky on desktop, scroll within if the list runs long. */}
          <aside className="min-w-0 space-y-5 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
            <FacetGroup
              title="Type"
              buckets={facets.type}
              active={types}
              labelFor={(value) => TYPE_LABELS[value] ?? value}
              onToggle={toggleType}
            />
            {perType ? (
              <FacetGroup
                title={perType.title}
                buckets={perTypeBuckets}
                active={facetFilters[perType.key] ?? []}
                labelFor={
                  perType.key === "award_class" ? titleCase : undefined
                }
                onToggle={(value) => toggleFacet(perType.key, value)}
              />
            ) : null}
            {hasFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Clear filters
              </button>
            ) : null}
          </aside>

          {/* Results */}
          <div className="min-w-0">
            {confidence === "low" && results.length > 0 ? (
              <Card className="mb-4 border-dashed p-3.5 text-sm text-[var(--text-secondary)]">
                These are best-effort matches — try refining your wording or
                removing filters for a closer fit.
              </Card>
            ) : null}

            {query.isLoading ? (
              <div className="space-y-4">
                {[0, 1, 2].map((index) => (
                  <SkeletonCard key={index} />
                ))}
              </div>
            ) : query.isError ? (
              <EmptyState
                icon={<SearchIcon size={24} />}
                title="Search is unavailable"
                description="Something went wrong running that search. Please try again in a moment."
              />
            ) : results.length === 0 ? (
              <EmptyState
                icon={<SearchIcon size={24} />}
                title={`No results for “${q}”`}
                description={
                  hasFilters
                    ? "Nothing matched with these filters. Try clearing them or broadening your search."
                    : "Try different or broader terms — search covers papers, grants, fellowships, and conferences."
                }
              />
            ) : (
              <>
                <div className="space-y-4">
                  {results.map((item) => (
                    <SearchResultCard key={item.content_id} item={item} />
                  ))}
                </div>
                {query.hasNextPage ? (
                  <div className="mt-6 flex justify-center">
                    <button
                      type="button"
                      onClick={() => query.fetchNextPage()}
                      disabled={query.isFetchingNextPage}
                      className="rounded-full border border-border bg-surface-alt px-5 py-2 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {query.isFetchingNextPage ? "Loading…" : "Load more"}
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FacetGroup({
  title,
  buckets,
  active,
  labelFor,
  onToggle,
}: {
  title: string;
  buckets: SearchFacetBucket[];
  active: string[];
  labelFor?: (value: string) => string;
  onToggle: (value: string) => void;
}) {
  if (buckets.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
        {title}
      </p>
      <div className="flex flex-wrap gap-1.5 lg:flex-col lg:items-start">
        {buckets.map((bucket) => {
          const on = active.includes(bucket.value);
          return (
            <button
              key={bucket.value}
              type="button"
              onClick={() => onToggle(bucket.value)}
              aria-pressed={on}
              className={cn(
                "inline-flex w-full items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                on
                  ? "border-primary bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] font-semibold text-primary"
                  : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt",
              )}
            >
              <span className="truncate">
                {labelFor ? labelFor(bucket.value) : bucket.value}
              </span>
              <span className="shrink-0 text-xs text-[var(--text-muted)]">
                {bucket.count.toLocaleString()}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <Card className="p-5">
      <div className="animate-pulse space-y-3">
        <div className="h-4 w-20 rounded bg-surface-alt" />
        <div className="h-5 w-3/4 rounded bg-surface-alt" />
        <div className="h-3 w-full rounded bg-surface-alt" />
        <div className="h-3 w-5/6 rounded bg-surface-alt" />
      </div>
    </Card>
  );
}
