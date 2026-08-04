"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CalendarIcon, MyloGlyph, ReportIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import {
  MyloReportCard,
  formatBriefingDay,
} from "@/components/portal/sections/mylo-report-card";
import { ApiError } from "@/lib/api-error";
import {
  useBriefing,
  useBriefings,
  useEntitlements,
  useLabBriefing,
  useLabBriefings,
} from "@/lib/portal/hooks";
import {
  FEATURE,
  PERSONAL_SLUG,
  type BriefingCategory,
  type DailyBriefingSummary,
} from "@/lib/portal/types";

/** Category order in the per-day count line — the same order the Daily page uses. */
const CATEGORY_ORDER: BriefingCategory[] = [
  "papers",
  "grants",
  "fellowships",
  "conferences",
];

/** "Today" / "Yesterday" for the two most recent days, else the plain date. */
function relativeDayLabel(day: string, today: string, yesterday: string): string {
  if (day === today) return "Today";
  if (day === yesterday) return "Yesterday";
  return formatBriefingDay(day) || day;
}

/** `YYYY-MM-DD` for a local date — matches how the backend stamps `generated_on`. */
function localDay(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() - offsetDays);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

/** The day's headline numbers, e.g. "12 papers · 3 grants". Text, never color. */
function countLine(row: DailyBriefingSummary): string {
  const parts = CATEGORY_ORDER.filter((c) => (row.counts?.[c] ?? 0) > 0).map(
    (c) => `${row.counts?.[c]} ${c}`,
  );
  return parts.length ? parts.join(" · ") : "Nothing matched";
}

function DayButton({
  row,
  selected,
  label,
  onSelect,
}: {
  row: DailyBriefingSummary;
  selected: boolean;
  label: string;
  onSelect: (day: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(row.generated_on)}
        aria-current={selected ? "true" : undefined}
        className={`w-full rounded-xl border px-3.5 py-3 text-left transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
          selected
            ? "border-primary bg-surface-alt"
            : "border-border bg-surface hover:bg-surface-alt"
        }`}
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {label}
          </span>
          {selected ? (
            <span className="text-[10.5px] font-semibold uppercase tracking-[.08em] text-primary">
              Showing
            </span>
          ) : null}
        </span>
        <span className="mt-1 block text-xs text-[var(--text-secondary)]">
          {countLine(row)}
        </span>
        {row.origin === "fallback" ? (
          <span className="mt-1 block text-[11px] text-[var(--text-muted)]">
            Written from counts
          </span>
        ) : null}
      </button>
    </li>
  );
}

function SkeletonHistory() {
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Card className="animate-pulse p-4 motion-reduce:animate-none lg:col-span-2">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="mb-2 block h-14 rounded-xl bg-surface-alt" />
        ))}
      </Card>
      <Card className="animate-pulse p-6 motion-reduce:animate-none lg:col-span-3">
        <span className="block h-3 w-28 rounded bg-surface-alt" />
        <span className="mt-4 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-2/3 rounded bg-surface-alt" />
      </Card>
    </div>
  );
}

/**
 * Reports: every retained daily briefing, readable after the day it was written.
 *
 * The daily run keeps one report per target per day (90 days of them); this is
 * where they are read back. The left column is the date list, the right renders
 * the chosen day through the same `MyloReportCard` the Daily page uses, so an
 * archived report reads identically to the live one. Follows the workspace scope
 * switcher: personal scope shows the caller's own history, a lab scope the lab's.
 *
 * States: loading, error, permission denied (a lab the caller cannot read),
 * populated, and two distinct empty states — an entitled account whose first run
 * has not landed yet, and a free account that will never accrue reports at all.
 */
export function ReportsSection() {
  const { labScope, currentLab } = usePortal();
  const isLab = labScope !== PERSONAL_SLUG && Boolean(currentLab);
  const labSlug = isLab ? labScope : undefined;

  const personalHistory = useBriefings();
  const labHistory = useLabBriefings(labSlug);
  const history = isLab ? labHistory : personalHistory;

  const [picked, setPicked] = React.useState<string | null>(null);
  // The picked day only sticks while it is still in the history being shown:
  // switching scope (or a prune dropping the tail) falls back to the newest day.
  const days = React.useMemo(() => history.data ?? [], [history.data]);
  const selected =
    picked && days.some((row) => row.generated_on === picked)
      ? picked
      : (days[0]?.generated_on ?? undefined);

  const personalDetail = useBriefing(isLab ? undefined : selected);
  const labDetail = useLabBriefing(labSlug, selected);
  const detail = isLab ? labDetail : personalDetail;

  const { data: entitlements } = useEntitlements();
  // A lab is on its own paid plan, so a lab scope is never the free-tier case.
  const neverEntitled =
    !isLab &&
    entitlements !== undefined &&
    !entitlements.features.includes(FEATURE.SCHEDULED_REPORTS);

  const forbidden =
    history.error instanceof ApiError && history.error.status === 403;

  const today = localDay();
  const yesterday = localDay(1);
  const owner = isLab && currentLab ? currentLab.name : "you";

  const subtitle = history.isLoading
    ? "Gathering the report history…"
    : days.length
      ? `Every daily report Mylo has written for ${owner} in the last 90 days.`
      : `Mylo's daily reports for ${owner}, kept for 90 days and readable here.`;

  return (
    <div>
      <SectionHeader eyebrow="From Mylo" title="Reports" subtitle={subtitle} />

      {history.isLoading ? (
        <SkeletonHistory />
      ) : forbidden ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          title="You don't have access to this lab's reports"
          description="Ask a lab manager to add you to the lab, then switch back to this workspace."
        />
      ) : history.isError ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          title="Couldn't load the report history"
          description="Something went wrong fetching past reports. Please try again in a moment."
        />
      ) : neverEntitled ? (
        <EmptyState
          icon={<MyloGlyph size={30} />}
          badge="Spore and up"
          title="Daily reports come with a paid plan"
          description="Mylo writes a report each morning — what matched, what's new, and what's worth reading — for accounts with scheduled reports. On the free plan there is no report history to keep."
        />
      ) : !days.length ? (
        <EmptyState
          icon={<CalendarIcon size={28} />}
          title="No reports yet"
          description={
            isLab
              ? "Once the nightly run writes this lab's first report it will appear here, and stay readable for 90 days."
              : "Your first morning report will appear here once the nightly run finishes. Every report stays readable for 90 days."
          }
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-5">
          <Card className="p-4 lg:col-span-2">
            <h2 className="mb-3 text-[10.5px] font-semibold uppercase tracking-[.09em] text-[var(--text-secondary)]">
              {days.length} {days.length === 1 ? "report" : "reports"}
            </h2>
            <ul
              className="flex max-h-[560px] flex-col gap-2 overflow-y-auto pr-1"
              aria-label="Report dates, newest first"
            >
              {days.map((row) => (
                <DayButton
                  key={row.generated_on}
                  row={row}
                  selected={row.generated_on === selected}
                  label={relativeDayLabel(row.generated_on, today, yesterday)}
                  onSelect={setPicked}
                />
              ))}
            </ul>
          </Card>

          <div className="lg:col-span-3" aria-live="polite">
            {detail.isError ? (
              <EmptyState
                icon={<ReportIcon size={28} />}
                title="Couldn't load that report"
                description="The report for this date could not be fetched. Pick another date, or try again shortly."
              />
            ) : (
              <MyloReportCard
                data={detail.data}
                isLoading={detail.isLoading}
                title="Report"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
