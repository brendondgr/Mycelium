"use client";

import Image from "next/image";

import { GlobalSearch } from "@/components/portal/global-search";
import { LabSwitcher } from "@/components/portal/lab-switcher";
import { NotificationBell } from "@/components/portal/notification-bell";
import { ThemeToggle } from "@/components/portal/theme-toggle";
import { UserMenu } from "@/components/portal/user-menu";

/** The sticky top bar: brand, workspace switcher, search, and account actions. */
export function PortalHeader() {
  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-[var(--divider)] bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] px-4 py-3 backdrop-blur-md sm:px-6">
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

      <LabSwitcher />

      <div className="hidden flex-1 md:flex">
        <GlobalSearch />
      </div>
      <div className="flex-1 md:hidden" />

      <div className="flex shrink-0 items-center gap-2.5">
        <NotificationBell />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
