"use client";

import { SearchIcon } from "@/components/portal/icons";

/**
 * The header search field. There is no search backend yet, so the input is a
 * faithful, accessible placeholder (labeled, focusable) that does not pretend to
 * return results — submitting is a no-op until search lands.
 */
export function GlobalSearch() {
  return (
    <div className="flex min-w-0 flex-1 justify-center">
      <form
        role="search"
        onSubmit={(event) => event.preventDefault()}
        className="flex w-full max-w-[420px] items-center gap-2.5 rounded-full border border-border bg-surface-alt px-3.5 py-2 focus-within:ring-2 focus-within:ring-ring"
      >
        <SearchIcon size={16} className="text-[var(--text-muted)]" />
        <input
          type="search"
          aria-label="Search papers, people, projects, grants"
          placeholder="Search papers, people, projects, grants…"
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-[var(--text-muted)]"
        />
      </form>
    </div>
  );
}
