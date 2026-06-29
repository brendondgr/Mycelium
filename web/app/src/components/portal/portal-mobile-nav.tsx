"use client";

import {
  CalendarIcon,
  DocumentIcon,
  FolderIcon,
  GridIcon,
  MembersIcon,
  ReportIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import {
  usePortal,
  type SectionKey,
} from "@/components/portal/portal-context";
import { cn } from "@/lib/utils";

const ITEMS: { key: SectionKey; label: string; icon: React.ReactNode }[] = [
  { key: "overview", label: "Overview", icon: <GridIcon size={15} /> },
  { key: "daily", label: "Daily", icon: <ReportIcon size={15} /> },
  { key: "opportunities", label: "Opportunities", icon: <SparkleIcon size={15} /> },
  { key: "deadlines", label: "Deadlines", icon: <CalendarIcon size={15} /> },
  { key: "projects", label: "Projects", icon: <FolderIcon size={15} /> },
  { key: "goals", label: "Goals", icon: <TargetIcon size={15} /> },
  { key: "members", label: "Members", icon: <MembersIcon size={15} /> },
  { key: "reports", label: "Reports", icon: <DocumentIcon size={15} /> },
];

/**
 * The compact horizontal navigation shown below the header on small screens
 * (the left sidebar is hidden under `lg`). A scrollable strip of section pills.
 */
export function PortalMobileNav() {
  const { section, goToSection } = usePortal();

  return (
    <nav
      aria-label="Sections"
      className="sticky top-[57px] z-20 flex gap-2 overflow-x-auto border-b border-[var(--divider)] bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] px-4 py-2.5 backdrop-blur-md lg:hidden"
    >
      {ITEMS.map((item) => {
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
