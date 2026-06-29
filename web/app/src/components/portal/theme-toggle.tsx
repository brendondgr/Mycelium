"use client";

import { MoonIcon, SunIcon } from "@/components/portal/icons";
import { IconButton } from "@/components/portal/primitives/icon-button";
import { usePortal } from "@/components/portal/portal-context";

/** Header light/dark toggle: shows the sun in dark mode, the moon in light. */
export function ThemeToggle() {
  const { theme, toggleTheme } = usePortal();
  const isDark = theme === "dark";
  return (
    <IconButton
      label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      aria-pressed={isDark}
      onClick={toggleTheme}
    >
      {isDark ? <SunIcon size={18} /> : <MoonIcon size={18} />}
    </IconButton>
  );
}
