"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { OPEN_ITEM_EVENT, type OpenItemRequest } from "@/components/portal/mylo/events";

/**
 * List + opened item, the layout every feed uses (chosen in `/labs`).
 *
 * The page scrolls as a whole through the cards. On a wide screen (≥ 980 px)
 * the opened item is pinned beside them at the visible height and scrolls on
 * its own; below that the pane is not drawn and opening an item slides in a
 * drawer instead. The selection is kept in the URL as `?item=<id>`, so a link
 * to a feed can open the same item — written with `history.replaceState`, so
 * picking cards never adds history entries or refetches the page.
 */

const ITEM_PARAM = "item";

/**
 * Overlays render at the end of <body>: the page's fade-in makes its wrapper a
 * stacking context, which would otherwise trap a drawer beneath the header.
 */
export function Portal({ children }: { children: React.ReactNode }) {
  const mounted = React.useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  return mounted ? createPortal(children, document.body) : null;
}

function readItemParam(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(ITEM_PARAM);
}

function writeItemParam(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(ITEM_PARAM, id);
  else url.searchParams.delete(ITEM_PARAM);
  window.history.replaceState(window.history.state, "", url);
}

/** Whether the pinned pane is on screen, i.e. the wide layout is active. */
function paneVisible(pane: HTMLElement | null): boolean {
  return Boolean(pane && pane.offsetParent !== null);
}

export function useReader<T>(
  items: T[],
  getId: (item: T) => string,
  first: T | undefined,
) {
  const [selected, setSelected] = React.useState<string | null>(() =>
    readItemParam(),
  );
  const [drawerId, setDrawerId] = React.useState<string | null>(null);
  const paneRef = React.useRef<HTMLElement | null>(null);

  // Nothing picked (or the pick was filtered away): the first card shown.
  const current = items.find((i) => getId(i) === selected) ?? first;
  const drawerItem = drawerId
    ? items.find((i) => getId(i) === drawerId)
    : undefined;

  const open = React.useCallback(
    (item: T) => {
      const id = getId(item);
      setSelected(id);
      writeItemParam(id);
      if (!paneVisible(paneRef.current)) setDrawerId(id);
    },
    [getId],
  );

  const closeDrawer = React.useCallback(() => setDrawerId(null), []);

  // Mylo's panel asks to open an item (a citation, a conversation's "About"
  // line): open it here when this feed has it.
  React.useEffect(() => {
    const onOpenItem = (event: Event) => {
      const request = (event as CustomEvent<OpenItemRequest>).detail;
      const item = items.find((i) => getId(i) === request.id);
      if (!item) return;
      request.handled = true;
      open(item);
    };
    window.addEventListener(OPEN_ITEM_EVENT, onOpenItem);
    return () => window.removeEventListener(OPEN_ITEM_EVENT, onOpenItem);
  }, [items, getId, open]);

  return {
    current,
    open,
    paneRef,
    drawerItem,
    closeDrawer,
    isSelected: (item: T) => current === item,
  };
}

export type Reader<T> = ReturnType<typeof useReader<T>>;

export type FeedGroup<T> = { key: string; label: string; items: T[] };

/**
 * Group rows by the theme they were matched to, keeping the order they arrive
 * in — grouping never re-sorts the feed. Rows with no theme go last.
 */
export function groupByTheme<T>(
  items: T[],
  theme: (item: T) => { id: string; label: string } | null | undefined,
  otherLabel = "Other matches",
): FeedGroup<T>[] {
  const groups = new Map<string, FeedGroup<T>>();
  for (const item of items) {
    const t = theme(item);
    const key = t?.id ?? "__none";
    if (!groups.has(key))
      groups.set(key, { key, label: t?.label ?? otherLabel, items: [] });
    groups.get(key)!.items.push(item);
  }
  const list = [...groups.values()];
  const none = list.findIndex((g) => g.key === "__none");
  if (none >= 0) list.push(list.splice(none, 1)[0]);
  // A single group is no grouping at all: drop the heading.
  if (list.length === 1) list[0] = { ...list[0], label: "" };
  return list;
}

export function ReaderLayout<T>({
  reader,
  groups,
  renderCard,
  renderDetail,
  getId,
  after,
  empty,
  label,
}: {
  reader: Reader<T>;
  groups: FeedGroup<T>[];
  renderCard: (
    item: T,
    state: { selected: boolean; onOpen: () => void },
  ) => React.ReactNode;
  renderDetail: (item: T) => React.ReactNode;
  getId: (item: T) => string;
  /** Under the list: the load-more sentinel, the held-back tail. */
  after?: React.ReactNode;
  /** Shown instead of the list when nothing matches. */
  empty?: React.ReactNode;
  label: string;
}) {
  const { current, open, paneRef, drawerItem, closeDrawer, isSelected } =
    reader;
  const drawerRef = React.useRef<HTMLDivElement>(null);
  const returnFocus = React.useRef<HTMLElement | null>(null);
  const drawerOpen = Boolean(drawerItem);

  // The drawer: remember what opened it, take focus, close on Escape, give
  // focus back. `preventScroll` because focusing an off-canvas panel would
  // otherwise scroll the page sideways.
  React.useEffect(() => {
    if (!drawerOpen) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    drawerRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeDrawer();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      returnFocus.current?.focus({ preventScroll: true });
    };
  }, [drawerOpen, closeDrawer]);

  const empty_ = groups.every((g) => g.items.length === 0);

  return (
    <>
      <div className="ws-feed-wrap" data-reader>
        <div className="ws-feed" data-layout="reader">
          {empty_
            ? empty
            : groups.map((g) =>
                g.items.length ? (
                  <section
                    key={g.key}
                    className="ws-feed-group"
                    aria-label={g.label || label}
                  >
                    {g.label ? (
                      <h2 className="ws-group-label">
                        {g.label}{" "}
                        <span className="ws-count">{g.items.length}</span>
                      </h2>
                    ) : null}
                    <div className="ws-feed-items">
                      {g.items.map((item) => (
                        <React.Fragment key={getId(item)}>
                          {renderCard(item, {
                            selected: isSelected(item),
                            onOpen: () => open(item),
                          })}
                        </React.Fragment>
                      ))}
                    </div>
                  </section>
                ) : null,
              )}
          {after}
        </div>
        {current && !empty_ ? (
          <aside
            ref={paneRef}
            className="ws-reading-pane ws-panel-box"
            aria-label={`Opened: ${label}`}
            aria-live="polite"
          >
            <div key={getId(current)}>{renderDetail(current)}</div>
          </aside>
        ) : null}
      </div>

      <Portal>
        <div
          className="ws-detail-layer"
          data-kind="drawer"
          data-open={drawerOpen || undefined}
        >
          <button
            type="button"
            className="ws-scrim"
            aria-label="Close"
            tabIndex={drawerOpen ? 0 : -1}
            onClick={closeDrawer}
          />
          <div
            ref={drawerRef}
            className="ws-detail"
            role="dialog"
            aria-modal="true"
            aria-label={drawerItem ? "Opened item" : undefined}
            aria-hidden={!drawerOpen}
            tabIndex={-1}
          >
            <button
              type="button"
              className="ws-icon-btn ws-detail-close"
              aria-label="Close"
              onClick={closeDrawer}
            >
              <X size={16} aria-hidden="true" />
            </button>
            {drawerItem ? renderDetail(drawerItem) : null}
          </div>
        </div>
      </Portal>
    </>
  );
}
