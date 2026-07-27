"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { MyloMark } from "@/components/brand/mylo-mark";
import { runOnboardingMatch } from "@/lib/auth-client";
import type {
  OnboardingMatchArea,
  OnboardingMatchSample,
} from "@/lib/auth-types";
import { cn } from "@/lib/utils";

/** Per-area copy: the plural label and the present-tense narration line. */
const AREA_META: Record<
  OnboardingMatchArea,
  { label: string; narrating: string }
> = {
  papers: {
    label: "Research papers",
    narrating: "Reading through research papers",
  },
  grants: { label: "Grants", narrating: "Reading through grants" },
  fellowships: {
    label: "Fellowships",
    narrating: "Reading through fellowships",
  },
  conferences: {
    label: "Conferences",
    narrating: "Reading through conferences",
  },
};

type RowStatus = "pending" | "running" | "done" | "error";

type Row = {
  area: OnboardingMatchArea;
  status: RowStatus;
  matched: number;
  top: OnboardingMatchSample | null;
  /** Papers only: a background scan is fetching fresh articles for the user. */
  scanning: boolean;
};

type OnboardingMatchProps = {
  /** The areas the user opted into, in the order they should be matched. */
  areas: OnboardingMatchArea[];
  /** Called when the user chooses to enter the workspace. */
  onDone: () => void;
};

/**
 * The live post-onboarding match window. Runs each opted-in area in turn against
 * the already-scraped corpus, narrating what Mylo is doing and filling a results
 * table row-by-row, then lets the user enter the workspace. Corpus-only: it
 * surfaces what today's scan holds rather than triggering a fresh scrape.
 */
export function OnboardingMatch({ areas, onDone }: OnboardingMatchProps) {
  const [rows, setRows] = useState<Row[]>(() =>
    areas.map((area) => ({
      area,
      status: "pending",
      matched: 0,
      top: null,
      scanning: false,
    })),
  );
  const [activeArea, setActiveArea] = useState<OnboardingMatchArea | null>(null);
  const [finished, setFinished] = useState(areas.length === 0);
  const started = useRef(false);

  useEffect(() => {
    // Run the sequential walk exactly once. The `started` ref survives React
    // StrictMode's dev-mode double-invoke (setup → cleanup → setup on the same
    // instance), so the loop is kicked off once and — crucially — is *not*
    // cancelled by the cleanup. Cancelling on cleanup would abort the only run
    // that StrictMode lets proceed, leaving the table stuck on the first area.
    // A stray state update after a real unmount is a harmless no-op in React 18+.
    if (started.current || areas.length === 0) {
      return;
    }
    started.current = true;

    (async () => {
      for (const area of areas) {
        setActiveArea(area);
        setRows((prev) =>
          prev.map((row) =>
            row.area === area ? { ...row, status: "running" } : row,
          ),
        );
        try {
          const result = await runOnboardingMatch(area);
          setRows((prev) =>
            prev.map((row) =>
              row.area === area
                ? {
                    ...row,
                    status: "done",
                    matched: result.matched,
                    top: result.sample[0] ?? null,
                    scanning: result.scanning,
                  }
                : row,
            ),
          );
        } catch {
          setRows((prev) =>
            prev.map((row) =>
              row.area === area ? { ...row, status: "error" } : row,
            ),
          );
        }
      }
      setActiveArea(null);
      setFinished(true);
    })();
  }, [areas]);

  const totalMatched = rows.reduce((sum, row) => sum + row.matched, 0);

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-6 flex items-center gap-4">
        <MyloMark
          className={cn("h-14 w-14 flex-none", !finished && "mylo-float")}
        />
        <div>
          <h1 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            {finished
              ? "Here's what Mylo found for you"
              : "Matching you to your research…"}
          </h1>
          <p
            aria-live="polite"
            className="mt-1 min-h-5 text-sm text-[var(--text-secondary)]"
          >
            {activeArea
              ? `${AREA_META[activeArea].narrating}…`
              : finished
                ? areas.length === 0
                  ? "You didn't ask Mylo to watch anything yet — you can turn signals on in Settings."
                  : `Matched you with ${totalMatched} ${totalMatched === 1 ? "opportunity" : "opportunities"} across ${rows.length} ${rows.length === 1 ? "area" : "areas"}.`
                : "Reading your interests and searching today's finds."}
          </p>
        </div>
      </div>

      {rows.length > 0 ? (
        <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_12px_34px_-22px_rgba(70,80,50,0.45)]">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Match results by opportunity area
            </caption>
            <thead>
              <tr className="border-b border-[var(--divider)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th scope="col" className="px-5 py-3 font-semibold">
                  Area
                </th>
                <th scope="col" className="px-5 py-3 font-semibold">
                  Matches
                </th>
                <th scope="col" className="px-5 py-3 font-semibold">
                  Top match
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.area}
                  className="border-b border-[var(--divider)] last:border-0"
                >
                  <th
                    scope="row"
                    className="px-5 py-4 font-medium text-[var(--text-primary)]"
                  >
                    <span className="flex items-center gap-2">
                      <StatusDot status={row.status} />
                      {AREA_META[row.area].label}
                    </span>
                  </th>
                  <td className="px-5 py-4 text-[var(--text-primary)]">
                    <MatchesCell row={row} />
                  </td>
                  <td className="px-5 py-4 text-[var(--text-secondary)]">
                    {row.status === "done" ? (
                      row.scanning ? (
                        <span
                          aria-live="polite"
                          className="flex items-center gap-2 text-brand-secondary"
                        >
                          <span className="h-2 w-2 flex-none rounded-full bg-brand-secondary motion-safe:animate-pulse" />
                          Scanning new articles for you…
                        </span>
                      ) : row.top ? (
                        <span className="line-clamp-2">
                          {row.top.title}
                          {row.top.match_percent != null ? (
                            <span className="ml-1 text-xs font-medium text-brand-secondary">
                              {row.top.match_percent}%
                            </span>
                          ) : null}
                        </span>
                      ) : (
                        <span className="text-[var(--text-muted)]">
                          Nothing today
                        </span>
                      )
                    ) : (
                      <span className="text-[var(--text-muted)]" aria-hidden="true">
                        —
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-6 flex items-center justify-between gap-4">
        {finished ? (
          <span />
        ) : (
          <button
            type="button"
            onClick={onDone}
            className="text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Skip and enter Mycelium
          </button>
        )}
        <Button className="rounded-full" disabled={!finished} onClick={onDone}>
          {finished ? "Enter Mycelium" : "Matching…"}
        </Button>
      </div>

      <p className="mt-4 text-center text-xs text-[var(--text-muted)]">
        Mylo keeps refreshing these as new papers and opportunities arrive.
      </p>
    </div>
  );
}

function StatusDot({ status }: { status: RowStatus }) {
  if (status === "done") {
    return (
      <span
        aria-label="Done"
        className="flex h-4 w-4 flex-none items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground"
      >
        ✓
      </span>
    );
  }
  if (status === "error") {
    return (
      <span
        aria-label="Could not match"
        className="flex h-4 w-4 flex-none items-center justify-center rounded-full bg-destructive/15 text-[10px] font-bold text-destructive"
      >
        !
      </span>
    );
  }
  if (status === "running") {
    return (
      <span
        aria-label="Matching"
        className="h-3.5 w-3.5 flex-none rounded-full bg-brand-secondary motion-safe:animate-pulse"
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="h-3.5 w-3.5 flex-none rounded-full border border-border"
    />
  );
}

function MatchesCell({ row }: { row: Row }) {
  if (row.status === "done") {
    return <span className="font-semibold">{row.matched}</span>;
  }
  if (row.status === "error") {
    return <span className="text-destructive">Couldn&rsquo;t match</span>;
  }
  if (row.status === "running") {
    return <span className="text-[var(--text-muted)]">Searching…</span>;
  }
  return (
    <span className="text-[var(--text-muted)]" aria-hidden="true">
      —
    </span>
  );
}
