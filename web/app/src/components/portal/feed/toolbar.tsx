"use client";

import * as React from "react";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";

import { Portal } from "@/components/portal/feed/reader";
import { scrollParent } from "@/lib/portal/scroll-parent";
import { useDismissable } from "@/lib/portal/use-dismissable";

/**
 * The toolbar every feed shares, pinned to the top of the scroll area while
 * the cards scroll under it: the search box on its own line, then one line
 * with the result count on the left and the filter menus and sort pushed to
 * the right (on a phone, one Filters button opening a sheet), then — only
 * while any are set — each active filter as a removable chip.
 *
 * A feed declares its facets as data (`Facet<T>`): each option carries the
 * test it applies, so counts, chips and filtering all come from one place.
 */

export type FacetOption<T> = {
  value: string;
  label: string;
  test: (item: T) => boolean;
};

export type Facet<T> = {
  id: string;
  label: string;
  /** `single` facets have an "any" option and pick one; `multi` facets OR their ticks. */
  mode: "single" | "multi";
  options: FacetOption<T>[];
};

export type FilterState = Record<string, string[]>;

export type SortOption<T> = {
  value: string;
  label: string;
  cmp: (a: T, b: T) => number;
};

/** Keep the items every active facet accepts (multi: any ticked option; single: the picked one). */
export function applyFacets<T>(
  items: T[],
  facets: Facet<T>[],
  filters: FilterState,
): T[] {
  return items.filter((item) =>
    facets.every((f) => {
      const picked = (filters[f.id] ?? []).filter(
        (v) => !(f.mode === "single" && v === "any"),
      );
      if (picked.length === 0) return true;
      return picked.some(
        (v) => f.options.find((o) => o.value === v)?.test(item) ?? true,
      );
    }),
  );
}

/** Every word of the query must appear somewhere in the item's text. */
export function matchesQuery(text: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = text.toLowerCase();
  return q.split(/\s+/).every((w) => hay.includes(w));
}

function countFor<T>(items: T[], facet: Facet<T>, value: string) {
  const opt = facet.options.find((o) => o.value === value);
  return opt ? items.filter(opt.test).length : 0;
}

function selectedLabel<T>(facet: Facet<T>, picked: string[]) {
  if (picked.length === 0 || (facet.mode === "single" && picked[0] === "any"))
    return null;
  if (facet.mode === "single")
    return facet.options.find((o) => o.value === picked[0])?.label ?? null;
  return picked.length === 1
    ? (facet.options.find((o) => o.value === picked[0])?.label ?? null)
    : `${picked.length}`;
}

function FacetFields<T>({
  facet,
  items,
  picked,
  toggle,
  name,
}: {
  facet: Facet<T>;
  items: T[];
  picked: string[];
  toggle: (facet: Facet<T>, value: string) => void;
  name: string;
}) {
  const single = facet.mode === "single";
  const current = single ? (picked[0] ?? "any") : null;
  return (
    <fieldset className="ws-checkset">
      <legend>{facet.label}</legend>
      {facet.options.map((o) => (
        <label key={o.value}>
          <input
            type={single ? "radio" : "checkbox"}
            name={single ? name : undefined}
            checked={single ? current === o.value : picked.includes(o.value)}
            onChange={() => toggle(facet, o.value)}
          />
          <span className="ws-check-text">{o.label}</span>
          {single && o.value === "any" ? null : (
            <span className="ws-check-count">
              {countFor(items, facet, o.value)}
            </span>
          )}
        </label>
      ))}
    </fieldset>
  );
}

function FacetMenu<T>({
  facet,
  items,
  picked,
  toggle,
  idPrefix,
}: {
  facet: Facet<T>;
  items: T[];
  picked: string[];
  toggle: (facet: Facet<T>, value: string) => void;
  idPrefix: string;
}) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const active = selectedLabel(facet, picked);
  return (
    <div className="ws-facet" ref={ref}>
      <button
        type="button"
        className="ws-facet-btn"
        data-active={active ? true : undefined}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        {facet.label}
        {active ? <span className="ws-facet-value">{active}</span> : null}
        <ChevronDown
          size={13}
          aria-hidden="true"
          className="ws-caret"
          data-open={open || undefined}
        />
      </button>
      {open ? (
        <div className="ws-menu ws-facet-menu">
          <FacetFields
            facet={facet}
            items={items}
            picked={picked}
            toggle={(f, v) => {
              toggle(f, v);
              if (f.mode === "single") setOpen(false);
            }}
            name={`${idPrefix}-${facet.id}-menu`}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Search, sort and facet state for one feed, plus the filtered + sorted rows. */
export function useFeedControls<T>({
  items,
  facets,
  sorts,
  text,
}: {
  items: T[];
  facets: Facet<T>[];
  sorts: SortOption<T>[];
  /** The searchable text of one item. */
  text: (item: T) => string;
}) {
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState(sorts[0]?.value ?? "");
  const [filters, setFilters] = React.useState<FilterState>({});

  const toggle = React.useCallback(
    (facet: Facet<T>, value: string) =>
      setFilters((prev) => {
        const cur = prev[facet.id] ?? [];
        const next =
          facet.mode === "single"
            ? [value]
            : cur.includes(value)
              ? cur.filter((v) => v !== value)
              : [...cur, value];
        return { ...prev, [facet.id]: next };
      }),
    [],
  );

  const visible = React.useMemo(() => {
    const sorter = sorts.find((s) => s.value === sort) ?? sorts[0];
    const rows = applyFacets(items, facets, filters).filter((i) =>
      matchesQuery(text(i), query),
    );
    return sorter ? [...rows].sort(sorter.cmp) : rows;
  }, [items, facets, filters, query, sort, sorts, text]);

  const active = facets.flatMap((f) =>
    (filters[f.id] ?? [])
      .filter((v) => !(f.mode === "single" && v === "any"))
      .map((v) => ({
        facet: f,
        value: v,
        label: f.options.find((x) => x.value === v)?.label ?? v,
      })),
  );

  const clear = React.useCallback(() => {
    setFilters({});
    setQuery("");
  }, []);

  return {
    query,
    setQuery,
    sort,
    setSort,
    filters,
    setFilters,
    toggle,
    visible,
    active,
    clear,
  };
}

export type FeedControls<T> = ReturnType<typeof useFeedControls<T>>;

/**
 * The pinned controls' height, published as `--ws-tools-h` on the feed page so
 * the reading pane beside the cards pins *below* them instead of under them,
 * and whether they are currently stuck (which is when they draw a backdrop).
 */
function usePinnedControls() {
  const pinRef = React.useRef<HTMLDivElement | null>(null);
  const [stuck, setStuck] = React.useState(false);

  React.useEffect(() => {
    const el = pinRef.current;
    if (!el) return;
    const page = el.closest<HTMLElement>(".ws-feedpage");
    const publish = () => page?.style.setProperty("--ws-tools-h", `${el.offsetHeight}px`);
    publish();
    const resize = new ResizeObserver(publish);
    resize.observe(el);

    const scroller = scrollParent(el);
    const measure = () => {
      const top = scroller ? scroller.getBoundingClientRect().top : 0;
      setStuck(el.getBoundingClientRect().top <= top + 1);
    };
    // Measured again on the next frame: a long jump (a restored scroll
    // position, a keyboard End) fires before sticky layout has settled.
    let frame = 0;
    const onScroll = () => {
      measure();
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    onScroll();
    (scroller ?? window).addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      (scroller ?? window).removeEventListener("scroll", onScroll);
      page?.style.removeProperty("--ws-tools-h");
    };
  }, []);

  return { pinRef, stuck };
}

export function FeedToolbar<T>({
  controls,
  items,
  facets,
  sorts,
  placeholder,
  noun,
  idPrefix,
}: {
  controls: FeedControls<T>;
  /** All rows (counts are over everything, not the current filter). */
  items: T[];
  facets: Facet<T>[];
  sorts: SortOption<T>[];
  placeholder: string;
  noun: string;
  idPrefix: string;
}) {
  const {
    query,
    setQuery,
    sort,
    setSort,
    filters,
    setFilters,
    toggle,
    visible,
    active,
  } = controls;
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const { pinRef, stuck } = usePinnedControls();

  React.useEffect(() => {
    if (!sheetOpen) return;
    const onKey = (e: KeyboardEvent) =>
      e.key === "Escape" && setSheetOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  return (
    <>
      <div className="ws-feed-controls" ref={pinRef} data-stuck={stuck || undefined}>
        <div className="ws-toolbar">
          <label className="ws-feed-search">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={placeholder}
              aria-label={`Search ${noun}`}
            />
          </label>
        </div>

        <div className="ws-results-line">
          <span className="ws-results-count" aria-live="polite">
            <strong>{visible.length}</strong> of {items.length} {noun}
          </span>
          {/* Menus, the phone Filters button and the sort share one wrapping
              row, so the sort flows after the last menu instead of being
              pushed onto a line of its own. */}
          <div className="ws-feed-tools" role="group" aria-label="Filters and sort">
            {facets.map((f) => (
              <FacetMenu
                key={f.id}
                facet={f}
                items={items}
                picked={filters[f.id] ?? []}
                toggle={toggle}
                idPrefix={idPrefix}
              />
            ))}
            {facets.length ? (
              <button
                type="button"
                className="ws-btn ws-btn-line ws-filters-btn"
                aria-expanded={sheetOpen}
                onClick={() => setSheetOpen(true)}
              >
                <SlidersHorizontal size={14} aria-hidden="true" />
                Filters{active.length ? ` · ${active.length}` : ""}
              </button>
            ) : null}
            {sorts.length > 1 ? (
              <label className="ws-sort">
                <span className="ws-sr">Sort by</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)}>
                  {sorts.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} aria-hidden="true" />
              </label>
            ) : null}
          </div>
        </div>

        {active.length ? (
          <div className="ws-active-filters">
            {active.map((a) => (
              <button
                key={`${a.facet.id}-${a.value}`}
                type="button"
                className="ws-chip ws-chip-active"
                onClick={() =>
                  toggle(a.facet, a.facet.mode === "single" ? "any" : a.value)
                }
                aria-label={`Remove filter ${a.facet.label}: ${a.label}`}
              >
                <span className="ws-meta-text">{a.facet.label}:</span> {a.label}
                <X size={12} aria-hidden="true" />
              </button>
            ))}
            <button
              type="button"
              className="ws-link"
              onClick={() => setFilters({})}
            >
              Clear all
            </button>
          </div>
        ) : null}
      </div>

      {facets.length ? (
        <Portal>
          <div className="ws-sheet-layer" data-open={sheetOpen || undefined}>
            <button
              type="button"
              className="ws-scrim"
              aria-label="Close filters"
              tabIndex={sheetOpen ? 0 : -1}
              onClick={() => setSheetOpen(false)}
            />
            <div
              className="ws-sheet"
              role="dialog"
              aria-modal="true"
              aria-label="Filters"
              aria-hidden={!sheetOpen}
            >
              <div className="ws-sheet-head">
                <h2 className="ws-h ws-panel-title">Filters</h2>
                <button
                  type="button"
                  className="ws-icon-btn"
                  aria-label="Close filters"
                  tabIndex={sheetOpen ? 0 : -1}
                  onClick={() => setSheetOpen(false)}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
              <div className="ws-sheet-fields">
                {facets.map((f) => (
                  <FacetFields
                    key={f.id}
                    facet={f}
                    items={items}
                    picked={filters[f.id] ?? []}
                    toggle={toggle}
                    name={`${idPrefix}-${f.id}-sheet`}
                  />
                ))}
              </div>
              <div className="ws-sheet-foot">
                <button
                  type="button"
                  className="ws-link"
                  tabIndex={sheetOpen ? 0 : -1}
                  onClick={() => setFilters({})}
                >
                  Clear all
                </button>
                <button
                  type="button"
                  className="ws-btn ws-btn-solid"
                  tabIndex={sheetOpen ? 0 : -1}
                  onClick={() => setSheetOpen(false)}
                >
                  Show {visible.length} {noun}
                </button>
              </div>
            </div>
          </div>
        </Portal>
      ) : null}
    </>
  );
}
