"use client";

import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "mycelium-theme";
const THEME_EVENT = "mycelium-theme-change";

function currentTheme(): Theme {
  if (typeof document === "undefined") {
    return "dark";
  }
  // Night Forest is the default; only an explicit light choice turns it off.
  return document.documentElement.getAttribute("data-theme") === "light"
    ? "light"
    : "dark";
}

function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage may be unavailable (private mode); the attribute still applies.
  }
  window.dispatchEvent(new CustomEvent(THEME_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(THEME_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(THEME_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/**
 * Read/toggle the light/dark theme. The value is read straight off <html>, which
 * the pre-paint `ThemeScript` already set from storage — so there is no flash and
 * no hydration mismatch. `useSyncExternalStore` keeps every toggle instance in
 * sync without a cascading effect.
 */
export function useTheme() {
  const theme = useSyncExternalStore<Theme>(
    subscribe,
    currentTheme,
    () => "dark",
  );

  const setTheme = useCallback((next: Theme) => applyTheme(next), []);
  const toggleTheme = useCallback(
    () => applyTheme(currentTheme() === "dark" ? "light" : "dark"),
    [],
  );

  return { theme, setTheme, toggleTheme };
}
