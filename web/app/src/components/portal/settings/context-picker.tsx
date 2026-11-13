"use client";

import * as React from "react";
import Link from "next/link";
import { Check, ChevronsUpDown, Search, UserRound } from "lucide-react";

import { useAppHref } from "@/components/demo/demo-context";
import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import {
  contextKey,
  settingsPath,
  type SettingsContext,
} from "@/lib/portal/settings";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type { Workspace } from "@/lib/portal/workspace";

/** "You are an admin", in the reader's words, from a workspace row's role. */
export function roleSentence(w: Workspace): string {
  const role = w.role.toLowerCase();
  if (role === "pi") return "You are the PI";
  if (role === "owner") return w.kind === "department" ? "You run this department" : "You own this lab";
  return `You are ${/^[aeiou]/.test(role) ? "an" : "a"} ${role}`;
}

/** The settings context a workspace row opens. */
function contextOf(workspace: Workspace): SettingsContext {
  if (workspace.kind === "lab") return { kind: "lab", slug: workspace.key };
  if (workspace.kind === "department") return { kind: "department", id: workspace.key };
  return { kind: "you" };
}

/**
 * Which thing Settings is configuring: you, one of your labs, or one of your
 * departments, each with your role beside it.
 *
 * Grouped and searchable from the start, because a person in many orgs is the
 * case this has to survive — a flat list of thirty names is not a picker. Every
 * row is a link to that context's first page, so it works without script and
 * opens in a new tab like any other link.
 */
export function ContextPicker({ current }: { current: SettingsContext }) {
  const { workspaces } = usePortal();
  const appHref = useAppHref();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const [query, setQuery] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const panelId = React.useId();

  React.useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const currentKey = contextKey(current);
  const active = workspaces.find((w) => contextKey(contextOf(w)) === currentKey);
  const needle = query.trim().toLowerCase();
  // Every word typed must appear somewhere in the name or its second line, so
  // "soil lab" finds "Soil Ecology Lab".
  const words = needle.split(/\s+/).filter(Boolean);
  const matches = (w: Workspace) => {
    const hay = `${w.name} ${w.sub}`.toLowerCase();
    return words.every((word) => hay.includes(word));
  };
  const labs = workspaces.filter((w) => w.kind === "lab" && matches(w));
  const departments = workspaces.filter((w) => w.kind === "department" && matches(w));
  const showYou = words.every((word) => "you personal".includes(word));
  const nothing = !showYou && labs.length === 0 && departments.length === 0;

  const close = () => {
    setOpen(false);
    setQuery("");
  };

  const row = (w: Workspace) => {
    const context = contextOf(w);
    const selected = contextKey(context) === currentKey;
    return (
      <li key={contextKey(context)}>
        <Link
          href={appHref(settingsPath(context))}
          onClick={close}
          aria-current={selected ? "true" : undefined}
          className="ws-settings-picker-row"
        >
          {w.kind === "personal" ? (
            <UserRound size={18} aria-hidden="true" className="shrink-0 text-[var(--text-muted)]" />
          ) : (
            <WorkspaceMark workspace={w} size={22} />
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-[var(--text-primary)]">
              {w.kind === "personal" ? "You" : w.name}
            </span>
            <span className="block truncate text-xs text-[var(--text-muted)]">
              {w.kind === "personal" ? "Your account and your own settings" : w.sub}
            </span>
          </span>
          {w.kind === "personal" ? null : (
            <span className="shrink-0 text-xs text-[var(--text-secondary)]">{w.role}</span>
          )}
          {selected ? (
            <Check size={15} aria-hidden="true" className="shrink-0 text-primary" />
          ) : null}
        </Link>
      </li>
    );
  };

  const group = (id: string, label: string, rows: Workspace[]) =>
    rows.length ? (
      <div>
        <p id={`${panelId}-${id}`} className="ws-settings-picker-group">
          {label}
        </p>
        <ul aria-labelledby={`${panelId}-${id}`} className="m-0 list-none p-0">
          {rows.map(row)}
        </ul>
      </div>
    ) : null;

  const personal = workspaces.find((w) => w.kind === "personal");
  const name = current.kind === "you" ? "You" : (active?.name ?? "…");
  const role = current.kind === "you" ? "Your own settings" : active ? roleSentence(active) : "";

  return (
    <div ref={ref} className="relative min-w-0">
      <button
        type="button"
        ref={buttonRef}
        onClick={() => {
          if (open) {
            close();
          } else {
            setQuery("");
            setOpen(true);
          }
        }}
        aria-expanded={open}
        aria-controls={panelId}
        className="ws-settings-picker-button"
      >
        {current.kind === "you" || !active ? (
          <UserRound size={20} aria-hidden="true" className="shrink-0 text-[var(--text-muted)]" />
        ) : (
          <WorkspaceMark workspace={active} size={26} />
        )}
        <span className="min-w-0 flex-1 text-left">
          <span className="sr-only">Settings for </span>
          <span className="block truncate font-serif text-[17px] font-semibold text-[var(--text-primary)]">
            {name}
          </span>
          <span className="block truncate text-xs text-[var(--text-secondary)]">{role}</span>
        </span>
        <ChevronsUpDown size={16} aria-hidden="true" className="shrink-0 text-[var(--text-muted)]" />
        <span className="sr-only">, change what you are configuring</span>
      </button>

      {open ? (
        <div
          id={panelId}
          className="ws-settings-picker-panel"
          onKeyDown={(event) => {
            // Escape closes and hands focus back to the button that opened it.
            if (event.key === "Escape") {
              event.stopPropagation();
              close();
              buttonRef.current?.focus();
            }
          }}
        >
          <label className="ws-settings-picker-search">
            <Search size={15} aria-hidden="true" className="shrink-0 text-[var(--text-muted)]" />
            <span className="sr-only">Find a lab or department</span>
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a lab or department"
              className="min-w-0 flex-1 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
            />
          </label>
          <div className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
            {showYou && personal ? group("you", "You", [personal]) : null}
            {group("labs", "Labs", labs)}
            {group("departments", "Departments", departments)}
            {nothing ? (
              <p role="status" className="px-3 py-4 text-sm text-[var(--text-secondary)]">
                No lab or department matches “{query.trim()}”.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
