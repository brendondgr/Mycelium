"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether the left section rail is collapsed to icons.
 *
 * Collapsed is the default — the workspace look chosen in `/labs` gives the
 * page the width and keeps the rail one click away. The header's toggle and
 * the rail itself both read this, so it lives outside React state, in
 * `localStorage`, with a same-tab event so every reader updates together.
 */

const KEY = "mycelium-rail-collapsed";
const EVENT = "mycelium-rail-change";

function read(): boolean {
  try {
    return localStorage.getItem(KEY) !== "0";
  } catch {
    return true;
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useRailCollapsed() {
  const collapsed = useSyncExternalStore(subscribe, read, () => true);
  const toggle = useCallback(() => {
    try {
      localStorage.setItem(KEY, read() ? "0" : "1");
    } catch {
      // Without storage the toggle cannot persist; nothing else to do.
    }
    window.dispatchEvent(new CustomEvent(EVENT));
  }, []);
  return { collapsed, toggle };
}
