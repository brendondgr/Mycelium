"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChevronDownIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { Avatar } from "@/components/portal/primitives/avatar";
import { logout } from "@/lib/auth-client";
import { useDismissable } from "@/lib/portal/use-dismissable";

/** Account button with a small menu: who you are, plus a working sign-out. */
export function UserMenu() {
  const { user } = usePortal();
  const router = useRouter();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const [signingOut, setSigningOut] = useState(false);

  async function signOut() {
    setSigningOut(true);
    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch {
      setSigningOut(false);
    }
  }

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex items-center gap-2 rounded-full border border-border bg-surface-alt p-1 pr-1.5 transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Avatar initials={user.initials} seed={user.username} size={30} />
        <ChevronDownIcon size={14} className="text-[var(--text-muted)]" />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-12 z-40 min-w-[220px] rounded-2xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          <div className="px-3 pb-2 pt-2">
            <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {user.name}
            </p>
            <p className="truncate text-xs text-[var(--text-muted)]">
              {user.email || user.username}
            </p>
          </div>
          <div className="my-1 h-px bg-[var(--divider)]" />
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            disabled={signingOut}
            className="w-full rounded-[9px] px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
