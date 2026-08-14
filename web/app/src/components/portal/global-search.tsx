"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { SearchIcon } from "@/components/portal/icons";
import { LeafVine } from "@/components/portal/leaf-vine";
import { SECTION_ROUTES } from "@/lib/portal/routes";

/**
 * The header search field: a global entry point to the search page. Submitting
 * (Enter) navigates to `/app/search?q=…`; the dedicated page owns the
 * URL-synced query, filters, and results.
 *
 * Focusing the field grows the sidebar's vine around it — the same component,
 * re-parameterised to the pill's radius, with fewer leaves and no breeze so it
 * never competes with the caret. Nav and search are then one idea ("Mylo is
 * listening") rather than two unrelated flourishes, and the focus ring still
 * carries the state on its own for anyone the vine never renders for.
 */
export function GlobalSearch() {
  const router = useRouter();
  const [value, setValue] = React.useState("");
  const [focused, setFocused] = React.useState(false);

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
        className="relative flex w-full max-w-[420px] items-center gap-2.5 rounded-full border border-border bg-surface-alt px-3.5 py-2 focus-within:ring-2 focus-within:ring-ring"
      >
        {/* `radius` is clamped to half the shorter side, so any large number
            traces a true pill rather than the sidebar row's 10px corners. */}
        <LeafVine grown={focused} active={false} leafCount={3} radius={999} />
        <SearchIcon
          size={16}
          className="relative z-[2] text-[var(--text-secondary)]"
        />
        <input
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          aria-label="Search the full database"
          placeholder="Search the full database here."
          className="relative z-[2] min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-[var(--text-muted)]"
        />
      </form>
    </div>
  );
}
