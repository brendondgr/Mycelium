"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * The reader's density and motion choices — the two appearance settings that
 * sit beside the theme (`lib/portal/theme.ts`).
 *
 * Both live as attributes on <html>, written before first paint by
 * `ThemeScript` and kept in `localStorage`. CSS keys off them: density re-points
 * the `--d-*` spacing and type variables in `globals.css`, and
 * `data-motion="none"` stops every animation and transition in the workspace
 * (as `prefers-reduced-motion` already does).
 */

export type Density = "compact" | "comfortable" | "open";
export type Motion = "full" | "subtle" | "none";

const KEYS = { density: "mycelium-density", motion: "mycelium-motion" } as const;
const DEFAULTS = { density: "comfortable", motion: "full" } as const;
const EVENT = "mycelium-appearance-change";

type Setting = keyof typeof KEYS;

function read<S extends Setting>(setting: S): (typeof DEFAULTS)[S] | string {
  if (typeof document === "undefined") return DEFAULTS[setting];
  return document.documentElement.getAttribute(`data-${setting}`) ?? DEFAULTS[setting];
}

function write(setting: Setting, value: string): void {
  document.documentElement.setAttribute(`data-${setting}`, value);
  try {
    localStorage.setItem(KEYS[setting], value);
  } catch {
    // Storage may be unavailable (private mode); the attribute still applies.
  }
  window.dispatchEvent(new CustomEvent(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useAppearance() {
  const density = useSyncExternalStore(
    subscribe,
    () => read("density"),
    () => DEFAULTS.density,
  ) as Density;
  const motion = useSyncExternalStore(
    subscribe,
    () => read("motion"),
    () => DEFAULTS.motion,
  ) as Motion;

  const setDensity = useCallback((v: Density) => write("density", v), []);
  const setMotion = useCallback((v: Motion) => write("motion", v), []);

  return { density, motion, setDensity, setMotion };
}
