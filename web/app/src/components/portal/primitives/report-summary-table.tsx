"use client";

import * as React from "react";

import type { BriefingCategory, BriefingProjectRow } from "@/lib/portal/types";

/**
 * The report's opening table: a row per part (the reader's own, then each project
 * they are on) against a column per category, every cell a count of what is new
 * today and cleared the relevance bar — the same set the report's sections below
 * write up. It is a map of the document, not a second set of numbers to reconcile
 * against it, which is why it does not show feed totals.
 *
 * Rendered only when there is at least one project: with nobody's projects to
 * compare, a single "Personal" row says less than the prose under it already does.
 *
 * The table scrolls horizontally inside its own box on a narrow screen, so a
 * reader on four categories never pushes the page sideways.
 */

/** Fixed display order and headers, independent of the order the watch config
 * happens to store the categories in. */
const COLUMNS: { key: BriefingCategory; label: string }[] = [
  { key: "papers", label: "Papers" },
  { key: "grants", label: "Grants" },
  { key: "fellowships", label: "Fellowships" },
  { key: "conferences", label: "Conferences" },
];

export function ReportSummaryTable({
  rows,
  categories,
  className,
}: {
  rows: BriefingProjectRow[] | undefined;
  categories: BriefingCategory[];
  className?: string;
}) {
  const columns = React.useMemo(
    () => COLUMNS.filter((c) => categories.includes(c.key)),
    [categories],
  );
  const hasProject = (rows ?? []).some((row) => row.kind === "project");
  if (!rows?.length || !columns.length || !hasProject) return null;

  return (
    <div className={className}>
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full min-w-[22rem] border-collapse text-[13px]">
          <caption className="sr-only">
            New items found today for you and for each of your projects, by area
          </caption>
          <thead>
            <tr className="bg-surface-alt text-[10px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
              <th scope="col" className="px-3 py-2 text-left font-semibold">
                New today
              </th>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="px-3 py-2 text-right font-semibold"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.key}
                className="border-t border-[var(--divider)] first:border-t-0"
              >
                <th
                  scope="row"
                  className={`px-3 py-2 text-left ${
                    row.kind === "personal"
                      ? "font-semibold text-[var(--text-primary)]"
                      : "font-medium text-[var(--text-primary)]"
                  }`}
                >
                  {row.label}
                </th>
                {columns.map((column) => {
                  const count = row.counts?.[column.key] ?? 0;
                  return (
                    <td
                      key={column.key}
                      className={`px-3 py-2 text-right tabular-nums ${
                        count
                          ? "font-semibold text-[var(--text-primary)]"
                          : "text-[var(--text-muted)]"
                      }`}
                    >
                      {count}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
