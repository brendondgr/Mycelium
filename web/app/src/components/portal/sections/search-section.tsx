"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { SearchIcon } from "@/components/portal/icons";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { FeedListSkeleton } from "@/components/portal/skeleton";
import { SearchResultCard } from "@/components/portal/sections/search-result-card";
import { useDailyReport, useSearchResults } from "@/lib/portal/hooks";
import type {
  SearchContentType,
  SearchFacets,
  SearchSort,
} from "@/lib/portal/types";

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

  const groups = React.useMemo(() => {
    // Grouped by kind when the reader hasn't narrowed to one kind; within a
    // group the backend's order (relevance, date or deadline) is kept.
    if (types.length === 1) return [{ key: types[0], label: TYPE_LABELS[types[0]] ?? types[0], items: results }];
    const order = ["paper", "grant", "fellowship", "conference"];
    const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
    const map = new Map<string, typeof results>();
    for (const r of results) {
      const k = r.type ?? "other";
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(r);
    }
    return [...map]
      .sort((x, y) => rank(x[0]) - rank(y[0]))
      .map(([key, items]) => ({ key, label: TYPE_LABELS[key] ?? "Other", items }));
  }, [results, types]);

  const suggestions = useSearchSuggestions();

  return (
    <div className="ws-search" data-entry={hasQuery ? "compact" : "centered"}>
      <div className="ws-search-entry">
        {hasQuery ? (
          <h1 className="ws-h ws-page-title ws-search-title-compact">Search</h1>
        ) : (
          <>
            <p className="ws-kicker">Search</p>
            <h1 className="ws-h ws-page-title">The whole library, ranked for you.</h1>
          </>
        )}
        <label className="ws-search-box">
          <SearchIcon size={18} aria-hidden="true" className="ws-search-icon" />
          <span className="ws-sr">Search the content library</span>
          <input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            autoFocus
            placeholder="Papers, grants, fellowships, conferences — a title, an author, an idea…"
          />
        </label>
        {!hasQuery && suggestions.length ? (
          <div className="ws-chips ws-suggest" role="group" aria-label="Suggested searches">
            {suggestions.map((s) => (
              <button key={s} type="button" className="ws-chip" onClick={() => setText(s)}>
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {!hasQuery ? (
        <p className="ws-meta-text ws-search-hint">
          Search the whole library by keyword or concept — an exact title, an author, a funding topic, or an idea in
          your own words.{suggestions.length ? " Your themes above are a place to start." : ""}
        </p>
      ) : (
        <>
          <div className="ws-toolbar ws-search-tools">
            <div className="ws-chips ws-chips-wrap" role="group" aria-label="Kinds">
              {facets.type.map((bucket) => (
                <button
                  key={bucket.value}
                  type="button"
                  className="ws-chip"
                  aria-pressed={types.includes(bucket.value)}
                  onClick={() => toggleType(bucket.value)}
                >
                  {TYPE_LABELS[bucket.value] ?? bucket.value}
                  <span className="ws-count">{bucket.count.toLocaleString()}</span>
                </button>
              ))}
              {perType
                ? perTypeBuckets.slice(0, 8).map((bucket) => (
                    <button
                      key={`${perType.key}-${bucket.value}`}
                      type="button"
                      className="ws-chip"
                      aria-pressed={(facetFilters[perType.key] ?? []).includes(bucket.value)}
                      onClick={() => toggleFacet(perType.key, bucket.value)}
                    >
                      <span className="ws-meta-text">{perType.title}:</span>{" "}
                      {perType.key === "award_class" ? titleCase(bucket.value) : bucket.value}
                    </button>
                  ))
                : null}
              {hasFilters ? (
                <button type="button" className="ws-link" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : null}
            </div>
            <label className="ws-sort">
              <span className="ws-sr">Sort by</span>
              <select value={sort} onChange={(event) => setSort(event.target.value as SearchSort)}>
                {SORTS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <p className="ws-meta-text ws-result-count" aria-live="polite">
            {subtitle}
          </p>

          {confidence === "low" && results.length > 0 ? (
            <p className="ws-note ws-note-quiet ws-note-text">
              These are best-effort matches — try refining your wording or removing filters for a closer fit.
            </p>
          ) : null}

          {query.isLoading ? (
            <FeedListSkeleton count={3} />
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
            <div className="ws-result-groups">
              {groups.map((g) => (
                <section key={g.key} className="ws-feed-group" aria-label={g.label}>
                  {groups.length > 1 ? (
                    <h2 className="ws-group-label">
                      {g.label} <span className="ws-count">{g.items.length}</span>
                    </h2>
                  ) : null}
                  <div className="space-y-4">
                    {g.items.map((item) => (
                      <SearchResultCard key={item.content_id} item={item} />
                    ))}
                  </div>
                </section>
              ))}
              {query.hasNextPage ? (
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={() => query.fetchNextPage()}
                    disabled={query.isFetchingNextPage}
                    className="ws-btn ws-btn-line"
                  >
                    {query.isFetchingNextPage ? "Loading…" : "Load more"}
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Suggested searches: the reader's own themes, from today's matches. */
function useSearchSuggestions(): string[] {
  const { data } = useDailyReport();
  return React.useMemo(() => {
    const labels = new Set<string>();
    for (const s of data?.suggestions ?? []) if (s.cluster?.label) labels.add(s.cluster.label);
    return [...labels].slice(0, 6);
  }, [data]);
}
