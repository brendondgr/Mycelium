"use client";

import { MoonIcon, SunIcon } from "@/components/portal/icons";
import { IconButton } from "@/components/portal/primitives/icon-button";
import { usePortal } from "@/components/portal/portal-context";

/**
 * The header's one-click theme switch: the sun in Night Forest (switch to
 * Daylight), the moon in Daylight (switch back). The same choice is in the
 * avatar menu and Settings → Appearance; all three share `useTheme`, so they
 * never disagree.
 */
export function ThemeToggle() {
  const { theme, toggleTheme } = usePortal();
  const isDark = theme === "dark";
  const label = isDark ? "Switch to Daylight" : "Switch to Night Forest";
  return (
    <IconButton label={label} title={label} onClick={toggleTheme}>
      {isDark ? <SunIcon size={18} /> : <MoonIcon size={18} />}
    </IconButton>
  );
}
