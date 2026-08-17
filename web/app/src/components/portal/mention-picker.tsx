"use client";

import * as React from "react";

import { CheckIcon, CloseIcon } from "@/components/portal/icons";
import { useLabMentionTargets } from "@/lib/portal/hooks";
import type { MentionTarget } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

type Tab = "roles" | "everyone" | "people";

const TABS: { id: Tab; label: string }[] = [
  { id: "roles", label: "Roles" },
  { id: "everyone", label: "Everyone" },
  { id: "people", label: "People" },
];

/** Stable identity for a chosen target, so selection survives a re-render and
 * the same person can't be added twice. */
function targetKey(target: MentionTarget): string {
  if (target.kind === "everyone") return "everyone";
  if ("username" in target) return `user:@${target.username}`;
  return `${target.kind}:${target.id}`;
}

function targetLabel(target: MentionTarget): string {
  return target.kind === "everyone" ? "@everyone" : target.name;
}

/**
 * Who a lab alert tags, chosen one category at a time.
 *
 * A guild's roles and its members are two long lists with nothing in common
 * except that both end in a ping, and `@everyone` is a single switch that
 * behaves unlike either. Stacked into one panel they drown each other — a
 * twenty-role server buries the person you were looking for, and the one
 * control with real blast radius sits in the middle of a scroll. Tabs keep each
 * category to its own space and make `@everyone` a place you go on purpose.
 *
 * Chosen targets show as removable chips **above** the tabs, so what the alert
 * will actually do stays visible no matter which list you are browsing.
 */
export function MentionPicker({
  labSlug,
  value,
  onChange,
}: {
  labSlug: string;
  value: MentionTarget[];
  onChange: (next: MentionTarget[]) => void;
}) {
  const [tab, setTab] = React.useState<Tab>("roles");
  const [query, setQuery] = React.useState("");
  const targets = useLabMentionTargets(labSlug || undefined);

  const chosen = React.useMemo(() => new Set(value.map(targetKey)), [value]);

  const add = (target: MentionTarget) => {
    if (chosen.has(targetKey(target))) return;
    onChange([...value, target]);
  };
  const remove = (key: string) =>
    onChange(value.filter((t) => targetKey(t) !== key));

  const roles = targets.data?.roles ?? [];
  const members = targets.data?.members ?? [];
  const everyoneChosen = chosen.has("everyone");

  const needle = query.trim().toLowerCase();
  const shownRoles = needle
    ? roles.filter((r) => r.name.toLowerCase().includes(needle))
    : roles;
  const shownMembers = needle
    ? members.filter((m) => m.name.toLowerCase().includes(needle))
    : members;

  return (
    <div>
      {value.length > 0 ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {value.map((target) => {
            const key = targetKey(target);
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => remove(key)}
                  aria-label={`Don't tag ${targetLabel(target)}`}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    target.kind === "everyone"
                      ? "border-[color-mix(in_srgb,var(--warning)_50%,var(--border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--surface))] text-[var(--text-primary)]"
                      : "border-border bg-surface-alt text-[var(--text-primary)]",
                  )}
                >
                  {targetLabel(target)}
                  <CloseIcon size={11} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      <div
        role="tablist"
        aria-label="What to tag"
        className="flex gap-1 rounded-full border border-border bg-surface p-0.5"
      >
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            onClick={() => {
              setTab(entry.id);
              setQuery("");
            }}
            className={cn(
              "flex-1 rounded-full px-2.5 py-1 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              tab === entry.id
                ? "bg-primary text-[#fffdf8]"
                : "text-[var(--text-secondary)] hover:bg-surface-alt",
            )}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="mt-2">
        {targets.isLoading ? (
          <p className="text-[12.5px] text-[var(--text-secondary)]">
            Loading who you can tag…
          </p>
        ) : tab === "everyone" ? (
          <EveryonePanel
            chosen={everyoneChosen}
            onToggle={() =>
              everyoneChosen ? remove("everyone") : add({ kind: "everyone" })
            }
          />
        ) : (
          <>
            {(tab === "roles" ? roles : members).length > 8 ? (
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={
                  tab === "roles" ? "Find a role…" : "Find a person…"
                }
                aria-label={tab === "roles" ? "Find a role" : "Find a person"}
                className="mb-1.5 w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[13px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            ) : null}
            <OptionList
              // A bounded, scrolling list rather than the whole guild inline:
              // the composer is a dialog, and a 200-name roster would push the
              // Set-alert button off the bottom of it.
              options={
                tab === "roles"
                  ? shownRoles.map((r) => ({
                      key: `role:${r.id}`,
                      label: r.name,
                      target: { kind: "role" as const, id: r.id, name: r.name },
                    }))
                  : shownMembers.map((m) => ({
                      key: `user:${m.id}`,
                      label: m.name,
                      target: { kind: "user" as const, id: m.id, name: m.name },
                    }))
              }
              chosen={chosen}
              onAdd={add}
              onRemove={remove}
              empty={
                targets.data?.detail ||
                (tab === "roles"
                  ? "This server has no roles to tag."
                  : "Nobody found in this server.")
              }
            />
          </>
        )}
      </div>
    </div>
  );
}

/** `@everyone` gets its own tab and its own plain warning, because it is the
 * one option here whose reach is the entire server rather than a chosen few. */
function EveryonePanel({
  chosen,
  onToggle,
}: {
  chosen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface-alt p-3">
      <button
        type="button"
        role="switch"
        aria-checked={chosen}
        onClick={onToggle}
        className="flex w-full items-center gap-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
            chosen
              ? "border-accent bg-accent text-[#fffdf8]"
              : "border-border text-transparent",
          )}
        >
          <CheckIcon size={12} aria-hidden="true" />
        </span>
        <span className="text-[13px] font-semibold text-[var(--text-primary)]">
          Tag @everyone
        </span>
      </button>
      <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">
        Notifies every member of this Discord server each time the alert fires,
        not only the people who care about this deadline. Mylo needs the
        &ldquo;Mention Everyone&rdquo; permission in the server; without it the
        alert still posts, just without the ping.
      </p>
    </div>
  );
}

function OptionList({
  options,
  chosen,
  onAdd,
  onRemove,
  empty,
}: {
  options: { key: string; label: string; target: MentionTarget }[];
  chosen: Set<string>;
  onAdd: (target: MentionTarget) => void;
  onRemove: (key: string) => void;
  empty: string;
}) {
  if (options.length === 0) {
    return (
      <p className="text-[12.5px] text-[var(--text-secondary)]">{empty}</p>
    );
  }
  return (
    <ul className="max-h-44 overflow-y-auto rounded-xl border border-border bg-surface p-1">
      {options.map((option) => {
        const isChosen = chosen.has(option.key);
        return (
          <li key={option.key}>
            <button
              type="button"
              role="checkbox"
              aria-checked={isChosen}
              onClick={() =>
                isChosen ? onRemove(option.key) : onAdd(option.target)
              }
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isChosen && "bg-surface-alt",
              )}
            >
              <span
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                  isChosen
                    ? "border-accent bg-accent text-[#fffdf8]"
                    : "border-border text-transparent",
                )}
              >
                <CheckIcon size={10} aria-hidden="true" />
              </span>
              <span className="min-w-0 truncate text-[var(--text-primary)]">
                {option.label}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
