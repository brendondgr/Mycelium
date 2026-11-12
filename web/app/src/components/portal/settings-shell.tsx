"use client";

import { useAppHref } from "@/components/demo/demo-context";
import * as React from "react";
import Link from "next/link";
import { Building2, IdCard, Palette, Sparkles, UserRound, Users, type LucideIcon } from "lucide-react";

import { usePortal } from "@/components/portal/portal-context";
import { useAppearance, type Density, type Motion } from "@/lib/portal/appearance";
import { CAPABILITY, can } from "@/lib/portal/capabilities";
import { SECTION_ROUTES, routeWithScope, type SectionKey } from "@/lib/portal/routes";
import { scopeKey } from "@/lib/portal/workspace";

/**
 * Settings, findable: one navigation shared by every settings page — your own
 * (Account, Profile & themes, Mylo & you) and the workspace's (lab or
 * department settings, members) — so reaching one means seeing all of them.
 * The pages keep their own routes; this only frames them. The avatar menu
 * (`user-menu.tsx`) lists the same entries from `useSettingsEntries`.
 */

export type SettingsEntry = { key: SectionKey; label: string; group: "You" | "Lab" | "Department"; icon: LucideIcon };

export function useSettingsEntries(): SettingsEntry[] {
  const { scope, currentLab, currentDepartment } = usePortal();
  const entries: SettingsEntry[] = [{ key: "account", label: "Account", group: "You", icon: UserRound }];
  if (scope.kind === "personal") {
    entries.push(
      { key: "profile", label: "Profile & themes", group: "You", icon: IdCard },
      { key: "mylo", label: "Mylo & you", group: "You", icon: Sparkles },
    );
    return entries;
  }
  const group = scope.kind === "department" ? "Department" : "Lab";
  const manage =
    (scope.kind === "lab" && can(currentLab, CAPABILITY.PROFILE_EDIT)) ||
    (scope.kind === "department" && can(currentDepartment, CAPABILITY.PROFILE_EDIT));
  if (manage) {
    entries.push({
      key: "profile",
      label: scope.kind === "department" ? "Department settings" : "Lab settings",
      group,
      icon: Building2,
    });
  }
  entries.push({ key: "members", label: "Members", group, icon: Users });
  return entries;
}

function Seg<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="ws-form-row">
      <span className="ws-form-label">{label}</span>
      <span className="ws-chips" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            className="ws-chip"
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </span>
    </div>
  );
}

/** Theme, density and motion — applied across the whole workspace at once. */
export function AppearanceCard() {
  const { theme, toggleTheme } = usePortal();
  const { density, motion, setDensity, setMotion } = useAppearance();
  return (
    <section id="appearance" className="ws-panel-box ws-settings-section" aria-label="Appearance">
      <h2 className="ws-h ws-panel-title">
        <Palette size={16} aria-hidden="true" className="mr-2 inline-block align-[-2px]" />
        Appearance
      </h2>
      <p className="ws-meta-text">Applies to every page, on this device.</p>
      <Seg
        label="Theme"
        value={theme}
        onChange={(v) => v !== theme && toggleTheme()}
        options={[
          { value: "dark", label: "Night Forest" },
          { value: "light", label: "Daylight" },
        ]}
      />
      <Seg<Density>
        label="Density"
        value={density}
        onChange={setDensity}
        options={[
          { value: "compact", label: "Compact" },
          { value: "comfortable", label: "Comfortable" },
          { value: "open", label: "Open" },
        ]}
      />
      <Seg<Motion>
        label="Motion"
        value={motion}
        onChange={setMotion}
        options={[
          { value: "full", label: "Full" },
          { value: "subtle", label: "Subtle" },
          { value: "none", label: "None" },
        ]}
      />
    </section>
  );
}

export function SettingsShell({ current, children }: { current: SectionKey; children: React.ReactNode }) {
  const { scope } = usePortal();
  const appHref = useAppHref();
  const entries = useSettingsEntries();
  const key = scopeKey(scope);
  const groups = Array.from(new Set(entries.map((e) => e.group)));

  return (
    <div className="ws-settings-shell">
      <nav className="ws-settings-nav" aria-label="Settings">
        <p className="ws-kicker">Settings</p>
        {groups.map((g) => (
          <div key={g} className="ws-settings-group">
            <p className="ws-settings-group-label">{g}</p>
            {entries
              .filter((e) => e.group === g)
              .map((e) => {
                const Icon = e.icon;
                return (
                  <Link
                    key={e.key}
                    href={appHref(routeWithScope(SECTION_ROUTES[e.key], key))}
                    className="ws-settings-link"
                    aria-current={current === e.key ? "page" : undefined}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {e.label}
                  </Link>
                );
              })}
          </div>
        ))}
        <div className="ws-settings-group">
          <p className="ws-settings-group-label">This device</p>
          <Link
            href={appHref(`${routeWithScope(SECTION_ROUTES.account, key)}#appearance`)}
            className="ws-settings-link"
          >
            <Palette size={16} aria-hidden="true" />
            Appearance
          </Link>
        </div>
      </nav>
      <div className="ws-settings-body">
        {children}
        {current === "account" ? <AppearanceCard /> : null}
      </div>
    </div>
  );
}
