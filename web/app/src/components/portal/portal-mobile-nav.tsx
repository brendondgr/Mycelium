"use client";

import {
  BankIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  FolderIcon,
  GridIcon,
  MembersIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import {
  usePortal,
  type SectionKey,
} from "@/components/portal/portal-context";
import type { MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

type Item = { key: SectionKey; label: string; icon: React.ReactNode };

/** Owner/admin/PI may reach the lab configuration. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * The compact horizontal navigation shown below the header on small screens (the
 * left sidebar is hidden under `lg`). Mirrors the sidebar: lab-scoped destinations
 * when a lab is active (with a manager-only Lab settings entry), personal ones
 * otherwise. The standalone Daily tab is gone — it now lives on the overview.
 */
export function PortalMobileNav() {
  const { section, goToSection, currentLab } = usePortal();
  const inLab = Boolean(currentLab);
  const manageLab = currentLab ? canManageLab(currentLab) : false;

  const items: Item[] = inLab
    ? [
        { key: "overview", label: "Overview", icon: <GridIcon size={15} /> },
        { key: "members", label: "Members", icon: <MembersIcon size={15} /> },
        ...(manageLab
          ? [{ key: "profile" as SectionKey, label: "Lab settings", icon: <TargetIcon size={15} /> }]
          : []),
        { key: "saves", label: "Saves", icon: <BookmarkIcon size={15} /> },
        { key: "papers", label: "Papers", icon: <DocumentIcon size={15} /> },
        { key: "opportunities", label: "Grants", icon: <BankIcon size={15} /> },
        { key: "fellowships", label: "Fellowships", icon: <SparkleIcon size={15} /> },
        { key: "conferences", label: "Conferences", icon: <ConferenceIcon size={15} /> },
        { key: "projects", label: "Projects", icon: <FolderIcon size={15} /> },
      ]
    : [
        { key: "overview", label: "Overview", icon: <GridIcon size={15} /> },
        { key: "profile", label: "Profile", icon: <TargetIcon size={15} /> },
        { key: "saves", label: "Saves", icon: <BookmarkIcon size={15} /> },
        { key: "papers", label: "Papers", icon: <DocumentIcon size={15} /> },
        { key: "opportunities", label: "Grants", icon: <BankIcon size={15} /> },
        { key: "fellowships", label: "Fellowships", icon: <SparkleIcon size={15} /> },
        { key: "conferences", label: "Conferences", icon: <ConferenceIcon size={15} /> },
        { key: "projects", label: "Projects", icon: <FolderIcon size={15} /> },
      ];

  return (
    <nav
      aria-label="Sections"
      className="sticky top-[57px] z-20 flex gap-2 overflow-x-auto border-b border-[var(--divider)] bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] px-4 py-2.5 backdrop-blur-md lg:hidden"
    >
      {items.map((item) => {
        const active = section === item.key;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => goToSection(item.key)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "border-primary bg-primary text-[#fffdf8]"
                : "border-border bg-surface-alt text-[var(--text-secondary)] hover:bg-surface",
            )}
          >
            {item.icon}
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
