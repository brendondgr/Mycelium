"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { SearchIcon } from "@/components/portal/icons";
import { SECTION_ROUTES } from "@/lib/portal/routes";

/**
 * The header search field: a global entry point to the search page. Submitting
 * (Enter) navigates to `/app/search?q=…`; the dedicated page owns the
 * URL-synced query, filters, and results.
 */
export function GlobalSearch() {
  const router = useRouter();
  const [value, setValue] = React.useState("");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const query = value.trim();
    const target = query
      ? `${SECTION_ROUTES.search}?q=${encodeURIComponent(query)}`
      : SECTION_ROUTES.search;
    router.push(target);
  };

  return (
    <div className="flex min-w-0 flex-1 justify-center">
      <form
        role="search"
        onSubmit={submit}
        className="flex w-full max-w-[420px] items-center gap-2.5 rounded-full border border-border bg-surface-alt px-3.5 py-2 focus-within:ring-2 focus-within:ring-ring"
      >
        <SearchIcon size={16} className="text-[var(--text-secondary)]" />
        <input
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="Search papers, grants, fellowships, conferences"
          placeholder="Search papers, grants, fellowships…"
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-[var(--text-muted)]"
        />
      </form>
    </div>
  );
}
