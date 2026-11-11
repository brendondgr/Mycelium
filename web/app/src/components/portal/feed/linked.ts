"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { FEED_FOR_KIND } from "@/components/portal/mylo/open-ref";
import { fetchItemCard } from "@/lib/portal/client";
import type { ItemCard } from "@/lib/portal/types";

export type FeedKind = ItemCard["area"];

/**
 * The `fetchItem` a feed gives its reader: the item a link names, as this
 * feed's card. An item of another kind (Mylo filed a conference under
 * "[grant]") is sent to its own feed instead, keeping the workspace.
 */
export function useLinkedItemFetch<T>(kind: FeedKind) {
  const router = useRouter();
  return React.useCallback(
    async (id: string): Promise<T | null> => {
      const found = await fetchItemCard(id);
      if (found.area === kind) return found.card as T;
      const feed = FEED_FOR_KIND[found.area];
      if (feed) {
        const url = new URL(window.location.href);
        url.pathname = feed;
        url.searchParams.set("item", id);
        router.replace(`${url.pathname}${url.search}`);
      }
      return null;
    },
    [kind, router],
  );
}
