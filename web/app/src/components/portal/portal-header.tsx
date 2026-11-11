"use client";

import Image from "next/image";
import * as React from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { GlobalSearch } from "@/components/portal/global-search";
import { NotificationBell } from "@/components/portal/notification-bell";
import { ThemeToggle } from "@/components/portal/theme-toggle";
import { UserMenu } from "@/components/portal/user-menu";
import { WorkspaceSheet } from "@/components/portal/workspace-sheet";
import { WorkspaceSwitcher } from "@/components/portal/workspace-switcher";
import { useRailCollapsed } from "@/lib/portal/use-rail";

/**
 * The sticky top bar: the rail toggle, brand, workspace dropdown, search, and
 * account actions — night glass over the ground, as on the front page.
 */
export function PortalHeader() {
  const { collapsed, toggle } = useRailCollapsed();
  const ref = React.useRef<HTMLElement>(null);

  // The pinned reading pane fills exactly the height below this bar, so the
  // bar publishes its own height (it changes with density and wrapping).
  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const write = () =>
      document.documentElement.style.setProperty("--ws-chrome-h", `${el.offsetHeight}px`);
    write();
    const ro = new ResizeObserver(write);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <header ref={ref} className="sticky top-0 z-30 flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--header-glass)] px-3 py-2.5 backdrop-blur-md sm:gap-4 sm:px-6">
      <button
        type="button"
        onClick={toggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        className="hidden h-9 w-9 shrink-0 place-items-center rounded-[10px] text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:grid"
      >
        {collapsed ? <PanelLeftOpen size={18} aria-hidden /> : <PanelLeftClose size={18} aria-hidden />}
      </button>
      <div className="flex shrink-0 items-center gap-2.5">
        <Image
          src="/logo-colored.svg"
          alt="Mycelium logo"
          width={34}
          height={34}
          unoptimized
          className="h-[34px] w-[34px] shrink-0"
        />
        <span className="hidden font-serif text-[19px] font-semibold tracking-[-0.01em] text-[var(--text-primary)] sm:inline">
          Mycelium
        </span>
      </div>

      {/* Desktop: a dropdown names and switches the workspace. Mobile: the
          sheet is the entire navigation. */}
      <WorkspaceSwitcher />
      <WorkspaceSheet />

      <div className="hidden flex-1 md:flex">
        <GlobalSearch />
      </div>

      <div className="flex shrink-0 items-center gap-1.5 sm:gap-2.5">
        <NotificationBell />
        {/* On a phone the theme lives in the avatar menu, so the workspace
            name gets the width instead. */}
        <span className="hidden sm:inline-flex">
          <ThemeToggle />
        </span>
        <UserMenu />
      </div>
    </header>
  );
}
