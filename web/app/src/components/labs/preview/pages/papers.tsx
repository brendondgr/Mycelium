"use client";

import * as React from "react";
import { ChevronDown, SlidersHorizontal, X } from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import { PAPERS, THEMES, themeOf, type Paper } from "@/components/labs/preview/fixtures";
import { DetailBody, PageHead, PaperItem, usePreview } from "@/components/labs/preview/parts";

function ThemeFilter({ active, toggle, asChecks = false }: {
  active: Set<string>;
  toggle: (id: string | null) => void;
  asChecks?: boolean;
}) {
  if (asChecks) {
    return (
      <fieldset className="lx-checkset">
        <legend>Themes</legend>
        {THEMES.map((t) => (
          <label key={t.id}>
            <input type="checkbox" checked={active.has(t.id)} onChange={() => toggle(t.id)} />
            {t.label}
          </label>
        ))}
      </fieldset>
    );
  }
  return (
    <div className="lx-chips" role="group" aria-label="Filter by theme">
      <button type="button" className="lx-chip" aria-pressed={active.size === 0} onClick={() => toggle(null)}>
        All themes
      </button>
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          className="lx-chip"
          aria-pressed={active.has(t.id)}
          style={{ "--tone": `var(--lx-tone-${t.tone})` } as React.CSSProperties}
          onClick={() => toggle(t.id)}
        >
          <span className="lx-theme-dot" aria-hidden="true" />
          {t.label}
        </button>
      ))}
    </div>
  );
}

function groupPapers(papers: Paper[], by: string): { key: string; label: string; items: Paper[] }[] {
  if (by === "none") return [{ key: "all", label: "", items: papers }];
  const keys =
    by === "theme" ? THEMES.map((t) => t.id) : (["today", "yesterday", "this week"] as string[]);
  return keys
    .map((k) => ({
      key: k,
      label: by === "theme" ? themeOf(k).label : k[0].toUpperCase() + k.slice(1),
      items: papers.filter((p) => (by === "theme" ? p.theme === k : p.found === k)),
    }))
    .filter((g) => g.items.length > 0);
}

export function PapersPage({ o }: { o: Record<string, OptionValue> }) {
  const [active, setActive] = React.useState<Set<string>>(new Set());
  const [panelOpen, setPanelOpen] = React.useState(true);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<string>(PAPERS[0].id);
  const paneRef = React.useRef<HTMLElement>(null);
  const { open } = usePreview();

  const toggle = (id: string | null) =>
    setActive((prev) => {
      if (id === null) return new Set();
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const filtered = PAPERS.filter((p) => active.size === 0 || active.has(p.theme));
  const groups = groupPapers(filtered, o.groupBy as string);
  const layout = o.layout as string;
  const filters = o.filters as string;
  const reader = layout === "reader";
  const current = filtered.find((p) => p.id === selected) ?? filtered[0];

  const filterButton =
    filters === "chips" ? null : (
      <button
        type="button"
        className="lx-btn lx-btn-line"
        aria-expanded={filters === "panel" ? panelOpen : drawerOpen}
        onClick={() => (filters === "panel" ? setPanelOpen((v) => !v) : setDrawerOpen(true))}
      >
        <SlidersHorizontal size={14} aria-hidden="true" />
        Filters{active.size ? ` · ${active.size}` : ""}
        {filters === "panel" ? (
          <ChevronDown size={14} aria-hidden="true" className="lx-caret" data-open={panelOpen || undefined} />
        ) : null}
      </button>
    );

  return (
    <div className="lx-papers">
      <PageHead
        title="Papers"
        lede={
          <>
            Ranked within each of the lab&apos;s four themes. <strong>12 new</strong> since yesterday.
          </>
        }
      >
        {filterButton}
      </PageHead>

      {filters === "chips" ? <ThemeFilter active={active} toggle={toggle} /> : null}
      {filters === "panel" ? (
        <div className="lx-collapse" data-open={panelOpen || undefined}>
          <div className="lx-collapse-inner">
            <div className="lx-filter-panel">
              <ThemeFilter active={active} toggle={toggle} asChecks />
              <fieldset className="lx-checkset">
                <legend>Found</legend>
                <label><input type="radio" name="lx-found" defaultChecked /> Any time</label>
                <label><input type="radio" name="lx-found" /> Today</label>
                <label><input type="radio" name="lx-found" /> This week</label>
              </fieldset>
            </div>
          </div>
        </div>
      ) : null}

      <div className="lx-feed-wrap" data-reader={reader || undefined}>
        <div className="lx-feed" data-layout={layout}>
          {groups.map((g) => (
            <section key={g.key} className="lx-feed-group" aria-label={g.label || "Papers"}>
              {g.label ? <h2 className="lx-group-label">{g.label}</h2> : null}
              <div className="lx-feed-items">
                {g.items.map((p) =>
                  reader ? (
                    <PaperItem
                      key={p.id}
                      paper={p}
                      summary="brief"
                      caveat={false}
                      selected={current?.id === p.id}
                      compactTitle
                      onOpen={() => {
                        setSelected(p.id);
                        // Below the reader breakpoint the pane is not drawn;
                        // fall back to the normal way of opening an item.
                        if (!paneRef.current || paneRef.current.offsetParent === null) {
                          open({ kind: "paper", item: p });
                        }
                      }}
                    />
                  ) : (
                    <PaperItem key={p.id} paper={p} summary={o.summary as string} caveat={Boolean(o.caveat)} />
                  ),
                )}
              </div>
            </section>
          ))}
          {filtered.length === 0 ? <p className="lx-empty">No papers in these themes yet.</p> : null}
        </div>
        {reader && current ? (
          <aside ref={paneRef} className="lx-reading-pane lx-panel-box" aria-label="Selected paper">
            <DetailBody detail={{ kind: "paper", item: current }} />
          </aside>
        ) : null}
      </div>

      {filters === "drawer" ? (
        <div className="lx-sheet-layer" data-open={drawerOpen || undefined}>
          <button type="button" className="lx-scrim" aria-label="Close filters" tabIndex={drawerOpen ? 0 : -1} onClick={() => setDrawerOpen(false)} />
          <div className="lx-sheet" role="dialog" aria-label="Filters" aria-hidden={!drawerOpen}>
            <div className="lx-sheet-head">
              <h2 className="lx-h lx-panel-title">Filters</h2>
              <button type="button" className="lx-icon-btn" aria-label="Close filters" tabIndex={drawerOpen ? 0 : -1} onClick={() => setDrawerOpen(false)}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <ThemeFilter active={active} toggle={toggle} asChecks />
          </div>
        </div>
      ) : null}
    </div>
  );
}
