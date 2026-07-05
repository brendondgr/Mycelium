"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

/** Shared input primitives for the onboarding + lab-onboarding step forms. */

export const inputClass =
  "min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60";

/** Trim, drop blanks, and case-fold-dedupe a list of tokens. */
export function dedupe(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const key = item.trim().toLowerCase();
    if (key && !seen.has(key)) {
      seen.add(key);
      out.push(item.trim());
    }
  }
  return out;
}

/** A pill toggle used for single- and multi-select choices. */
export function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "rounded-full border px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-[var(--text-secondary)] hover:border-brand-secondary",
      )}
    >
      {children}
    </button>
  );
}

/** A tag/token entry field: type + Enter (or blur) to add, × to remove. */
export function TokenField({
  label,
  items,
  onChange,
  placeholder,
}: {
  label: string;
  items: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  function add(raw?: string) {
    const value = (raw ?? draft).trim();
    if (!value) {
      return;
    }
    if (!items.some((item) => item.toLowerCase() === value.toLowerCase())) {
      onChange([...items, value]);
    }
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-[var(--text-primary)]">{label}</p>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-input bg-card p-2">
        {items.map((item) => (
          <span
            key={item}
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground"
          >
            {item}
            <button
              type="button"
              aria-label={`Remove ${item}`}
              onClick={() => onChange(items.filter((value) => value !== item))}
              className="text-[var(--text-muted)] hover:text-foreground"
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          onBlur={() => add()}
          placeholder={placeholder}
          className="min-w-40 flex-1 bg-transparent px-1 py-1 text-sm text-foreground outline-none"
        />
      </div>
    </div>
  );
}
