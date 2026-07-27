"use client";

import * as React from "react";

import {
  BankIcon,
  ConferenceIcon,
  DocumentIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import type { WindowCounts, WindowCountsMap } from "@/lib/portal/types";

const EMPTY_WINDOW: WindowCounts = { today: 0, week: 0, month: 0, year: 0 };

/** The area rows in the "what Mylo found" recency matrix, in display order. */
const STAT_AREAS: {
  key: keyof WindowCountsMap;
  label: string;
  icon: React.ReactNode;
}[] = [
  { key: "papers", label: "Articles", icon: <DocumentIcon size={15} /> },
  { key: "grants", label: "Grants", icon: <BankIcon size={15} /> },
  { key: "conferences", label: "Conferences", icon: <ConferenceIcon size={15} /> },
  { key: "fellowships", label: "Fellowships", icon: <SparkleIcon size={15} /> },
];

/**
 * The recency matrix of what Mylo found (today / this week / month / year, per
 * area) — shared by the lab overview and the personal overview so both read
 * identically.
 */
export function MyloFoundCard({
  windowCounts,
  isLoading,
  title = "What Mylo found",
}: {
  windowCounts: WindowCountsMap | undefined;
  isLoading: boolean;
  title?: string;
}) {
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {title}
      </h2>
      <table className="w-full border-collapse text-[13px]">
        <caption className="sr-only">Items Mylo found by recency window</caption>
        <thead>
          <tr className="text-[10px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
            <th scope="col" className="pb-2 text-left font-semibold">
              Area
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Today
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Week
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Month
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Year
            </th>
          </tr>
        </thead>
        <tbody>
          {STAT_AREAS.map((area) => {
            const c = windowCounts?.[area.key] ?? EMPTY_WINDOW;
            const cell = (value: number) =>
              isLoading ? "—" : value.toLocaleString();
            return (
              <tr key={area.key} className="border-t border-[var(--divider)]">
                <th
                  scope="row"
                  className="py-2 text-left font-medium text-[var(--text-primary)]"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-primary">{area.icon}</span>
                    {area.label}
                  </span>
                </th>
                <td className="py-2 text-right font-semibold tabular-nums text-[var(--text-primary)]">
                  {cell(c.today)}
                </td>
                <td className="py-2 text-right tabular-nums text-[var(--text-secondary)]">
                  {cell(c.week)}
                </td>
                <td className="py-2 text-right tabular-nums text-[var(--text-secondary)]">
                  {cell(c.month)}
                </td>
                <td className="py-2 text-right tabular-nums text-[var(--text-secondary)]">
                  {cell(c.year)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
