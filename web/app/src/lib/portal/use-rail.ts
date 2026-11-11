"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether the left section rail is collapsed to icons.
 *
 * Open is the default: the rail stays expanded until the reader closes it
 * with the header's toggle, and that choice is remembered. The header's toggle and
 * the rail itself both read this, so it lives outside React state, in
 * `localStorage` and on <html> as `data-rail` (written before first paint by
 * `ThemeScript`, so the rail's width never jumps on load), with a same-tab
 * event so every reader updates together.
 */

const KEY = "mycelium-rail-collapsed";
const EVENT = "mycelium-rail-change";

function read(): boolean {
  if (typeof document !== "undefined") {
    const attr = document.documentElement.getAttribute("data-rail");
    if (attr) return attr !== "expanded";
  }
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
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
  const collapsed = useSyncExternalStore(subscribe, read, () => false);
  const toggle = useCallback(() => {
    const next = read() ? "expanded" : "collapsed";
    document.documentElement.setAttribute("data-rail", next);
    try {
      localStorage.setItem(KEY, next === "expanded" ? "0" : "1");
    } catch {
      // Without storage the toggle cannot persist; nothing else to do.
    }
    window.dispatchEvent(new CustomEvent(EVENT));
  }, []);
  return { collapsed, toggle };
}
