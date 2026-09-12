"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CheckIcon, SearchIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { Modal } from "@/components/portal/primitives/modal";
import {
  scopeForWorkspace,
  scopeKey,
  type Workspace,
} from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

/** How many recently-used workspaces to surface above the full list. */
const MAX_RECENTS = 4;
const RECENTS_KEY = "mycelium_workspace_recents";

/**
 * Jump to any workspace with ⌘K / Ctrl+K.
 *
 * The rail is the fastest switch while every workspace fits on screen; this is
 * what keeps switching constant-time when they don't. It is deliberately **not
 * advertised** anywhere in the chrome — no `⌘K` badge on the caption or in the
 * sheet — because a keyboard hint printed next to a control it does not belong
 * to reads as clutter. People who use palettes try ⌘K.
 *
 * `global-search.tsx` binds no keyboard shortcut, so there is nothing to collide
 * with.
 */
export function WorkspacePalette() {
  const { workspaces, scope, setScope } = usePortal();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(RECENTS_KEY);
    if (stored) {
      try {
        const parsed: unknown = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setRecents(parsed.filter((v): v is string => typeof v === "string"));
        }
      } catch {
        // A corrupt entry is not worth surfacing — recents are a convenience.
      }
    }
  }, []);

  // The global shortcut. Suppressed while the caller is typing somewhere else,
  // so ⌘K in a feed's search box stays whatever the browser does with it.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") {
        return;
      }
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable;
      if (typing && !open) {
        return;
      }
      event.preventDefault();
      setOpen((value) => !value);
      setQuery("");
      setCursor(0);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const activeKey = scopeKey(scope);

  /** Rows in display order — recents first, then grouped by kind. */
  const sections = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (w: Workspace) => !q || w.name.toLowerCase().includes(q);
    const all = workspaces.filter(match);

    const out: { label: string; items: Workspace[] }[] = [];
    if (!q) {
      const recent = recents
        .map((key) => all.find((w) => w.key === key))
        .filter((w): w is Workspace => Boolean(w) && w!.key !== activeKey)
        .slice(0, MAX_RECENTS);
      if (recent.length > 0) {
        out.push({ label: "Recent", items: recent });
      }
    }
    const personal = all.filter((w) => w.kind === "personal");
    const depts = all.filter((w) => w.kind === "department");
    const labs = all.filter((w) => w.kind === "lab");
    if (personal.length) out.push({ label: "Personal", items: personal });
    if (depts.length) out.push({ label: "Departments", items: depts });
    if (labs.length) out.push({ label: "Labs", items: labs });
    return out;
  }, [workspaces, query, recents, activeKey]);

  const flat = useMemo(
    () => sections.flatMap((section) => section.items),
    [sections],
  );

  if (!open) {
    return null;
  }

  const choose = (workspace: Workspace) => {
    const next = [
      workspace.key,
      ...recents.filter((key) => key !== workspace.key),
    ].slice(0, MAX_RECENTS + 1);
    setRecents(next);
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    setScope(scopeForWorkspace(workspace));
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (flat.length === 0) {
        return;
      }
      setCursor((current) => {
        const delta = event.key === "ArrowDown" ? 1 : flat.length - 1;
        return (current + delta) % flat.length;
      });
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const target = flat[cursor];
      if (target) {
        choose(target);
      }
    }
  };

  let index = -1;
  return (
    <Modal onClose={() => setOpen(false)} label="Switch workspace" width="md">
      <div onKeyDown={onKeyDown}>
        <div className="flex items-center gap-2.5 border-b border-[var(--divider)] px-4 py-3">
          <SearchIcon size={17} className="shrink-0 text-[var(--text-muted)]" />
          <input
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            placeholder="Jump to a workspace…"
            aria-label="Jump to a workspace"
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-[14.5px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
          />
        </div>

        <div
          className="max-h-[320px] overflow-y-auto p-1.5"
          role="listbox"
          aria-label="Workspaces"
        >
          {sections.map((section) => (
            <div key={section.label}>
              <p className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                {section.label}
              </p>
              {section.items.map((workspace) => {
                index += 1;
                const at = index;
                const active = workspace.key === activeKey;
                return (
                  <button
                    key={`${section.label}-${workspace.key}`}
                    type="button"
                    role="option"
                    aria-selected={at === cursor}
                    onMouseEnter={() => setCursor(at)}
                    onClick={() => choose(workspace)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[13.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      at === cursor && "bg-surface-alt",
                    )}
                  >
                    <WorkspaceMark workspace={workspace} size={24} />
                    <span className="flex-1 truncate">
                      {workspace.name}
                      <span className="text-[11.5px] text-[var(--text-muted)]">
                        {" "}
                        · {workspace.sub}
                      </span>
                    </span>
                    <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">
                      {workspace.role}
                    </span>
                    {active ? (
                      <CheckIcon size={15} className="shrink-0 text-primary" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          ))}

          {flat.length === 0 ? (
            <p className="px-3 py-5 text-center text-[13px] text-[var(--text-muted)]">
              No workspace matches “{query}”.
            </p>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
