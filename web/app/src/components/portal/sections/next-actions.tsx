"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  ChevronRightIcon,
  FolderIcon,
  MembersIcon,
  ReportIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";

type ActionRow = {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  sub: string;
  onClick: () => void;
};

/**
 * A prioritised list of next actions derived entirely from real app state —
 * no fake tasks, no fabricated scores.
 */
export function NextActions() {
  const { goToSection, projects } = usePortal();
  const profileQuery = useProfile();
  const watchQuery = useWatch();

  const completeness = computeCompleteness(profileQuery.data);
  const watch = watchQuery.data;

  const tintClass =
    "bg-[color-mix(in_srgb,var(--primary)_15%,transparent)]";

  const rows: ActionRow[] = [];

  // 1. Profile incomplete
  if (!profileQuery.isLoading && completeness.percent < 100) {
    rows.push({
      icon: <TargetIcon size={15} />,
      iconBg: tintClass,
      title: "Finish your research profile",
      sub: `${completeness.doneCount}/${completeness.total} sections done`,
      onClick: () => goToSection("profile" as SectionKey),
    });
  }

  // 2. No watch topics set
  if (
    !watchQuery.isLoading &&
    (!watch || watch.topics.length === 0)
  ) {
    rows.push({
      icon: <SparkleIcon size={15} />,
      iconBg: tintClass,
      title: "Tell Mylo what to watch",
      sub: "Add topics so Mylo can monitor literature for you",
      onClick: () => goToSection("profile" as SectionKey),
    });
  }

  // 3. No projects yet
  if (projects.length === 0) {
    rows.push({
      icon: <FolderIcon size={15} />,
      iconBg: tintClass,
      title: "Start your first project",
      sub: "Organise your work and track progress",
      onClick: () => goToSection("projects" as SectionKey),
    });
  }

  // Always: browse workspace
  const allDone =
    !profileQuery.isLoading &&
    !watchQuery.isLoading &&
    completeness.percent === 100 &&
    watch &&
    watch.topics.length > 0 &&
    projects.length > 0;

  if (allDone) {
    rows.push({
      icon: <MembersIcon size={15} />,
      iconBg: tintClass,
      title: "You're all set — Mylo is monitoring your topics.",
      sub: "Check your daily digest for new matches",
      onClick: () => goToSection("daily" as SectionKey),
    });
  } else {
    rows.push({
      icon: <ReportIcon size={15} />,
      iconBg: tintClass,
      title: "Browse your workspace",
      sub: "View your daily digest and reports",
      onClick: () => goToSection("daily" as SectionKey),
    });
  }

  return (
    <Card className="p-[22px]">
      <h2 className="text-base font-semibold text-[var(--text-primary)] mb-1">
        Next actions
      </h2>
      <p className="text-[12.5px] text-[var(--text-muted)] mb-4">
        What needs your attention, in order.
      </p>

      <div className="flex flex-col">
        {rows.map((row, i) => {
          const isLast = i === rows.length - 1;
          return (
            <button
              key={row.title}
              type="button"
              onClick={row.onClick}
              className={[
                "flex items-center gap-[13px] py-3 px-[6px]",
                "border-none bg-transparent cursor-pointer font-sans text-left w-full",
                "hover:bg-surface-alt rounded-lg",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                !isLast ? "border-b border-[var(--divider)]" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {/* Icon square */}
              <span
                className={[
                  "w-[30px] h-[30px] rounded-lg flex items-center justify-center shrink-0 text-primary",
                  row.iconBg,
                ].join(" ")}
              >
                {row.icon}
              </span>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p className="m-0 text-[13.5px] font-medium text-[var(--text-primary)] truncate">
                  {row.title}
                </p>
                <p className="m-0 text-[11.5px] text-[var(--text-muted)]">
                  {row.sub}
                </p>
              </div>

              {/* Chevron */}
              <ChevronRightIcon
                size={16}
                className="shrink-0 text-[var(--text-muted)]"
              />
            </button>
          );
        })}
      </div>
    </Card>
  );
}
