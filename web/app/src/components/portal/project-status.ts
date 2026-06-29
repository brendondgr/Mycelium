import type { PillTone } from "@/components/portal/primitives/pill";

/**
 * Map a project's free-form status string (read from `goals`) onto the shared
 * visual vocabulary. Status is optional, so a missing value reads as a neutral
 * "Active" rather than inventing progress.
 */
export function displayStatus(status: string | null): string {
  return status && status.trim() ? status : "Active";
}

export function statusPillTone(status: string | null): PillTone {
  const value = (status ?? "").toLowerCase();
  if (value.includes("review")) {
    return "review";
  }
  if (value.includes("plan")) {
    return "neutral";
  }
  return "primary";
}

export function statusDotColor(status: string | null): string {
  const value = (status ?? "").toLowerCase();
  if (value.includes("review")) {
    return "var(--accent)";
  }
  if (value.includes("plan")) {
    return "var(--text-muted)";
  }
  if (value.trim()) {
    return "var(--primary)";
  }
  return "var(--brand-secondary)";
}
