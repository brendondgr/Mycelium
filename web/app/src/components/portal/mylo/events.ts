"use client";

import type { AgentAnchor } from "@/lib/portal/agent/types";

/**
 * How the rest of the app reaches Mylo's panel without knowing about it: a
 * window event, like the collaborator search. `AskMyloButton` sends it with
 * the thing it sits on; the host (mounted once in the workspace shell) opens
 * the one panel.
 */
export const ASK_MYLO_EVENT = "mycelium:ask-mylo";

export type AskMyloRequest = {
  anchor: AgentAnchor;
  /** The thing's title, for the panel's "About" line before Mylo resolves it. */
  title: string;
  /** Where the thing was asked about from, to open it again from the panel. */
  href?: string;
};

export function askMylo(request: AskMyloRequest) {
  window.dispatchEvent(new CustomEvent(ASK_MYLO_EVENT, { detail: request }));
}

/**
 * Open an item in the reader of the page that shows it. A feed's reader
 * listens and sets `handled` when the item is in its list, or when it is not
 * but is of the feed's kind (the reader then fetches it); when nobody does,
 * the caller navigates to the feed for the item's kind instead.
 */
export const OPEN_ITEM_EVENT = "mycelium:open-item";

export type OpenItemRequest = { id: string; kind?: string; handled: boolean };

export function openItemInReader(id: string, kind?: string): boolean {
  const detail: OpenItemRequest = { id, kind, handled: false };
  window.dispatchEvent(new CustomEvent(OPEN_ITEM_EVENT, { detail }));
  return detail.handled;
}
