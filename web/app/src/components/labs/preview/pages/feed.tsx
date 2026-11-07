"use client";

import * as React from "react";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";

import type { FeedKey, OptionValue } from "@/components/labs/schema";
import {
  FEED_CONFIGS,
  applyFilters,
  groupItems,
  searchText,
  type Facet,
  type FilterState,
} from "@/components/labs/preview/feeds";
import type { FeedItem } from "@/components/labs/preview/fixtures";
import { FeedCard, ItemDetail, PageHead, useDismiss, usePreview } from "@/components/labs/preview/parts";

function countFor(items: FeedItem[], facet: Facet, value: string) {
  const opt = facet.options.find((o) => o.value === value);
  return opt ? items.filter(opt.test).length : 0;
}

function selectedLabel(facet: Facet, picked: string[]) {
  if (picked.length === 0 || (facet.mode === "single" && picked[0] === "any")) return null;
  if (facet.mode === "single") return facet.options.find((o) => o.value === picked[0])?.label ?? null;
  return picked.length === 1 ? (facet.options.find((o) => o.value === picked[0])?.label ?? null) : `${picked.length}`;
}

/** The ticks or radios for one facet — shared by the bar's menus, the column and the sheet. */
function FacetFields({
  facet,
  items,
  picked,
  toggle,
  name,
}: {
  facet: Facet;
  items: FeedItem[];
  picked: string[];
  toggle: (facet: Facet, value: string) => void;
  name: string;
}) {
  const single = facet.mode === "single";
  const current = single ? (picked[0] ?? "any") : null;
  return (
    <fieldset className="lx-checkset">
      <legend>{facet.label}</legend>
      {facet.options.map((o) => (
        <label key={o.value}>
          <input
            type={single ? "radio" : "checkbox"}
            name={single ? name : undefined}
            checked={single ? current === o.value : picked.includes(o.value)}
            onChange={() => toggle(facet, o.value)}
          />
          <span className="lx-check-text">{o.label}</span>
          {single && o.value === "any" ? null : <span className="lx-check-count">{countFor(items, facet, o.value)}</span>}
        </label>
      ))}
    </fieldset>
  );
}

function FacetMenu({
  facet,
  items,
  picked,
  toggle,
  feed,
}: {
  facet: Facet;
  items: FeedItem[];
  picked: string[];
  toggle: (facet: Facet, value: string) => void;
  feed: string;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const close = React.useCallback(() => setOpen(false), []);
  useDismiss(open, close, ref);
  const active = selectedLabel(facet, picked);

  return (
    <div className="lx-facet" ref={ref}>
      <button
        type="button"
        className="lx-facet-btn"
        data-active={active ? true : undefined}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        {facet.label}
        {active ? <span className="lx-facet-value">{active}</span> : null}
        <ChevronDown size={13} aria-hidden="true" className="lx-caret" data-open={open || undefined} />
      </button>
      {open ? (
        <div className="lx-menu lx-facet-menu">
          <FacetFields
            facet={facet}
            items={items}
            picked={picked}
            toggle={(f, v) => {
              toggle(f, v);
              if (f.mode === "single") setOpen(false);
            }}
            name={`${feed}-${facet.id}-menu`}
          />
        </div>
      ) : null}
    </div>
  );
}

export function FeedPage({ feed, o }: { feed: FeedKey; o: Record<string, OptionValue> }) {
  const cfg = FEED_CONFIGS[feed];
  const { open } = usePreview();
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState(cfg.sorts[0].value);
  const [filters, setFilters] = React.useState<FilterState>({});
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<string | null>(null);
  const paneRef = React.useRef<HTMLElement>(null);

  const layout = o.layout as string;
  const filterMode = o.filters as string;
  const show = o.card as string[];
  const deadline = (o.deadline as string | undefined) ?? "both";
  const reader = layout === "reader";

  const toggle = (facet: Facet, value: string) =>
    setFilters((prev) => {
      const cur = prev[facet.id] ?? [];
      const next =
        facet.mode === "single" ? [value] : cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      return { ...prev, [facet.id]: next };
    });

  const q = query.trim().toLowerCase();
  const sorter = cfg.sorts.find((s) => s.value === sort) ?? cfg.sorts[0];
  const visible = applyFilters(cfg.items, cfg.facets, filters)
    .filter((i) => !q || q.split(/\s+/).every((w) => searchText(i).includes(w)))
    .sort(sorter.cmp);
  const groups = groupItems(visible, o.groupBy as string);
  // Nothing picked yet: the first card the reader sees, which grouping may
  // have moved away from the top of the sorted list.
  const current = visible.find((i) => i.id === selected) ?? groups[0]?.items[0] ?? visible[0];

  const active = cfg.facets.flatMap((f) =>
    (filters[f.id] ?? [])
      .filter((v) => !(f.mode === "single" && v === "any"))
      .map((v) => ({ facet: f, value: v, label: f.options.find((x) => x.value === v)?.label ?? v })),
  );
  const newCount = cfg.items.filter((i) => i.isNew).length;

  const openItem = (item: FeedItem) => {
    if (reader) {
      setSelected(item.id);
      // Below the reader breakpoint the pane is not drawn; fall back to the
      // normal way of opening an item.
      if (!paneRef.current || paneRef.current.offsetParent === null) open(item);
    } else {
      open(item);
    }
  };

  const card = (item: FeedItem) => (
    <FeedCard
      key={item.id}
      item={item}
      show={show}
      deadline={deadline}
      selected={reader && current?.id === item.id}
      onOpen={() => openItem(item)}
    />
  );

  const allFields = (suffix: string) =>
    cfg.facets.map((f) => (
      <FacetFields
        key={f.id}
        facet={f}
        items={cfg.items}
        picked={filters[f.id] ?? []}
        toggle={toggle}
        name={`${feed}-${f.id}-${suffix}`}
      />
    ));

  const list =
    layout === "board" ? (
      <div className="lx-board">
        {(
          [
            ["new", "New"],
            ["closing", "Closing soon"],
            ["saved", "Saved"],
          ] as const
        ).map(([status, label]) => {
          const items = visible.filter((i) => i.kind === "grant" && i.status === status);
          return (
            <section key={status} className="lx-board-col" aria-label={label}>
              <h2 className="lx-group-label">
                {label} <span className="lx-count">{items.length}</span>
              </h2>
              <div className="lx-feed-items">{items.map(card)}</div>
            </section>
          );
        })}
      </div>
    ) : (
      <div className="lx-feed" data-layout={layout}>
        {groups.map((g) => (
          <section key={g.key} className="lx-feed-group" aria-label={g.label || cfg.title}>
            {g.label ? (
              <h2 className="lx-group-label">
                {g.label} <span className="lx-count">{g.items.length}</span>
              </h2>
            ) : null}
            <div className="lx-feed-items">{g.items.map(card)}</div>
          </section>
        ))}
        {visible.length === 0 ? (
          <div className="lx-empty">
            <p>No {cfg.noun} match these filters.</p>
            <button
              type="button"
              className="lx-btn lx-btn-line"
              onClick={() => {
                setFilters({});
                setQuery("");
              }}
            >
              Clear search and filters
            </button>
          </div>
        ) : null}
      </div>
    );

  return (
    <div className="lx-feedpage" data-filters={filterMode} data-layout={layout}>
      <PageHead
        title={cfg.title}
        lede={
          <>
            {cfg.lede} <strong>{newCount} new</strong> this week.
          </>
        }
      />

      <div className="lx-toolbar lx-rise">
        <label className="lx-feed-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={cfg.searchPlaceholder}
            aria-label={`Search ${cfg.noun}`}
          />
        </label>
        <label className="lx-sort">
          <span className="lx-sr">Sort by</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {cfg.sorts.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <ChevronDown size={14} aria-hidden="true" />
        </label>
        <button
          type="button"
          className="lx-btn lx-btn-line lx-filters-btn"
          aria-expanded={sheetOpen}
          onClick={() => setSheetOpen(true)}
        >
          <SlidersHorizontal size={14} aria-hidden="true" />
          Filters{active.length ? ` · ${active.length}` : ""}
        </button>
      </div>

      {filterMode === "bar" ? (
        <div className="lx-facetbar lx-rise" role="group" aria-label="Filters">
          {cfg.facets.map((f) => (
            <FacetMenu
              key={f.id}
              facet={f}
              items={cfg.items}
              picked={filters[f.id] ?? []}
              toggle={toggle}
              feed={feed}
            />
          ))}
        </div>
      ) : null}

      <div className="lx-results-line">
        <span className="lx-meta-text" aria-live="polite">
          {visible.length} of {cfg.items.length} {cfg.noun}
        </span>
        {active.map((a) => (
          <button
            key={`${a.facet.id}-${a.value}`}
            type="button"
            className="lx-chip lx-chip-active"
            onClick={() => toggle(a.facet, a.facet.mode === "single" ? "any" : a.value)}
            aria-label={`Remove filter ${a.facet.label}: ${a.label}`}
          >
            <span className="lx-meta-text">{a.facet.label}:</span> {a.label}
            <X size={12} aria-hidden="true" />
          </button>
        ))}
        {active.length ? (
          <button type="button" className="lx-link" onClick={() => setFilters({})}>
            Clear all
          </button>
        ) : null}
      </div>

      <div className="lx-feed-body" data-rail={filterMode === "rail" || undefined}>
        {filterMode === "rail" ? (
          <aside className="lx-filter-rail" aria-label="Filters">
            {allFields("rail")}
          </aside>
        ) : null}
        <div className="lx-feed-wrap" data-reader={reader || undefined}>
          {list}
          {reader && current ? (
            <aside ref={paneRef} className="lx-reading-pane lx-panel-box" aria-label={`Selected: ${current.title}`}>
              <ItemDetail key={current.id} item={current} />
            </aside>
          ) : null}
        </div>
      </div>

      <div className="lx-sheet-layer" data-open={sheetOpen || undefined}>
        <button
          type="button"
          className="lx-scrim"
          aria-label="Close filters"
          tabIndex={sheetOpen ? 0 : -1}
          onClick={() => setSheetOpen(false)}
        />
        <div className="lx-sheet" role="dialog" aria-label="Filters" aria-hidden={!sheetOpen}>
          <div className="lx-sheet-head">
            <h2 className="lx-h lx-panel-title">Filters</h2>
            <button
              type="button"
              className="lx-icon-btn"
              aria-label="Close filters"
              tabIndex={sheetOpen ? 0 : -1}
              onClick={() => setSheetOpen(false)}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="lx-sheet-fields">{allFields("sheet")}</div>
          <div className="lx-sheet-foot">
            <button type="button" className="lx-link" onClick={() => setFilters({})}>
              Clear all
            </button>
            <button type="button" className="lx-btn lx-btn-solid" onClick={() => setSheetOpen(false)}>
              Show {visible.length} {cfg.noun}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
