"use client";

import { useQuery } from "@tanstack/react-query";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";

type Health = "checking" | "healthy" | "unreachable";

async function fetchHealth(): Promise<boolean> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "health"), {
    cache: "no-store",
  });
  return response.ok;
}

/**
 * A slim status bar. Rather than fabricate scraper/sync states that have no
 * backend yet, it shows one real signal — a live API health check — plus the
 * build label.
 */
export function PortalFooter() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["portal", "health"],
    queryFn: fetchHealth,
    refetchInterval: 60_000,
    retry: false,
  });

  const status: Health = isLoading
    ? "checking"
    : isError || data === false
      ? "unreachable"
      : "healthy";

  const dot =
    status === "healthy"
      ? "bg-primary portal-pulse-dot"
      : status === "unreachable"
        ? "bg-clay"
        : "bg-[var(--text-muted)]";

  const label =
    status === "healthy"
      ? "API healthy"
      : status === "unreachable"
        ? "API unreachable"
        : "Checking API…";

  return (
    <footer className="border-t border-[var(--divider)] bg-surface-alt">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3.5 sm:px-6">
        <span className="inline-flex items-center gap-2 text-[12.5px] font-semibold text-[var(--text-primary)]">
          <span className={`h-2 w-2 rounded-full ${dot}`} />
          {label}
        </span>
        <span className="text-xs text-[var(--text-secondary)]">
          Live research pipeline coming online — scans, scoring, and digests are
          on the roadmap.
        </span>
        <span className="ml-auto text-[11.5px] text-[var(--text-muted)]">
          Mycelium · preview
        </span>
      </div>
    </footer>
  );
}
