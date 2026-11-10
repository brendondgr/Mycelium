"use client";

import { useAppRouter, useDemo } from "@/components/demo/demo-context";
import { useState } from "react";

import { LogOut, Moon, Palette } from "lucide-react";

import { ChevronDownIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { useSettingsEntries, type SettingsEntry } from "@/components/portal/settings-shell";
import { Avatar } from "@/components/portal/primitives/avatar";
import { logout } from "@/lib/auth-client";
import { useDismissable } from "@/lib/portal/use-dismissable";

/**
 * The avatar's menu — the one obvious door to every settings page, from any
 * page, at any width: who you are, your own settings, this workspace's
 * settings, the theme, and sign-out.
 */
export function UserMenu() {
  const { user, scope, goToSection, theme, toggleTheme } = usePortal();
  const router = useAppRouter();
  const demo = useDemo();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const [signingOut, setSigningOut] = useState(false);

  async function signOut() {
    if (demo) {
      // Nobody is signed in to the demo: leaving it is going back to the site.
      window.location.assign("/");
      return;
    }
    setSigningOut(true);
    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch {
      setSigningOut(false);
    }
  }

  const settings = useSettingsEntries();
  const you = settings.filter((e) => e.group === "You");
  const workspace = settings.filter((e) => e.group !== "You");

  const entry = (e: SettingsEntry) => {
    const Icon = e.icon;
    return (
    <button
      key={e.key + e.label}
      type="button"
      role="menuitem"
      onClick={() => {
        setOpen(false);
        goToSection(e.key);
      }}
      className="flex w-full items-center gap-2.5 rounded-[9px] px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="text-[var(--text-muted)]">
        <Icon size={15} aria-hidden />
      </span>
      {e.label}
    </button>
    );
  };

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
        <ChevronDownIcon size={14} className="text-[var(--text-secondary)]" />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-12 z-40 min-w-[250px] rounded-2xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          <div className="px-3 pb-2 pt-2">
            <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {user.name}
            </p>
            <p className="truncate text-xs text-[var(--text-secondary)]">
              {user.email || user.username}
            </p>
          </div>
          <div className="my-1 h-px bg-[var(--divider)]" />
          <p className="px-3 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
            You
          </p>
          {you.map(entry)}
          {workspace.length ? (
            <>
              <p className="px-3 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                {scope.kind === "department" ? "Department" : "Lab"}
              </p>
              {workspace.map(entry)}
            </>
          ) : null}
          <div className="my-1 h-px bg-[var(--divider)]" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              router.push("/app/account#appearance");
            }}
            className="flex w-full items-center gap-2.5 rounded-[9px] px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Palette size={15} aria-hidden className="text-[var(--text-muted)]" />
            Appearance: theme, density, motion
          </button>
          <div className="flex items-center justify-between gap-3 px-3 py-1.5 text-sm font-medium text-foreground">
            <span className="flex items-center gap-2.5">
              <Moon size={15} aria-hidden className="text-[var(--text-muted)]" />
              Night Forest
            </span>
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={theme === "dark"}
              aria-label="Night Forest theme"
              onClick={toggleTheme}
              className="ws-switch"
            >
              <span aria-hidden />
            </button>
          </div>
          <div className="my-1 h-px bg-[var(--divider)]" />
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            disabled={signingOut}
            className="w-full rounded-[9px] px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
          >
            <span className="flex items-center gap-2.5">
              <LogOut size={15} aria-hidden className="text-[var(--text-muted)]" />
              {demo ? "Leave the demo" : signingOut ? "Signing out…" : "Sign out"}
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
