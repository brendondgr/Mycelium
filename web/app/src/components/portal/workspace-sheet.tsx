"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  CheckIcon,
  ChevronDownIcon,
  PlusIcon,
  SearchIcon,
} from "@/components/portal/icons";
import { NavIconFor } from "@/components/portal/nav-icon";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { useEntitlements } from "@/lib/portal/hooks";
import { navGroupsFor } from "@/lib/portal/nav";
import {
  KIND_LABEL,
  scopeForWorkspace,
  scopeKey,
  type Workspace,
} from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

/** Above this many workspaces the list gets a filter field. */
const FILTER_THRESHOLD = 5;

/**
 * The whole of the mobile navigation: one control in the header that opens one
 * sheet holding the workspace switcher *and* every section.
 *
 * It replaces two things that used to compete at phone width — the workspace
 * rail (a desktop idea; shrunk to a strip its marks stop being recognisable) and
 * the horizontal tab strip, which hid half its entries off the right edge and
 * gave no hint they were there.
 *
 * The workspace list is **collapsed by default**. With nine workspaces an
 * always-open list pushes "Overview" below the fold, which makes the common
 * action (change section) pay for the rare one (change workspace). Expanding
 * swaps the sections for the list; choosing a workspace switches and collapses.
 */
export function WorkspaceSheet() {
  const {
    workspaces,
    workspacesLoading,
    currentWorkspace,
    scope,
    setScope,
    section,
    goToSection,
    currentLab,
    currentDepartment,
    user,
  } = usePortal();
  const { data: entitlements } = useEntitlements();

  const [open, setOpen] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [query, setQuery] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);

  /**
   * Closing resets the sheet, so it always reopens on the sections rather than
   * on a workspace list left expanded from last time. Done here rather than in
   * an effect watching `open`: the reset is part of the close, not a reaction
   * to it, and an effect would cost a cascading render.
   */
  const close = useCallback(() => {
    setOpen(false);
    setListOpen(false);
    setQuery("");
  }, []);

  // Escape closes; focus returns to the control that opened it.
  useEffect(() => {
    if (!open) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  const has = (feature: string) =>
    !entitlements || entitlements.features.includes(feature);

  const groups = useMemo(
    () =>
      navGroupsFor({
        scope,
        currentLab,
        currentDepartment,
        isAdmin: isPlatformAdmin(user),
        hasFeature: has,
      }),
    // `has` is derived from `entitlements`; listing that is the honest dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scope, currentLab, currentDepartment, user, entitlements],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return workspaces;
    }
    return workspaces.filter((w) => w.name.toLowerCase().includes(q));
  }, [workspaces, query]);

  if (workspacesLoading) {
    return (
      <div
        className="h-9 flex-1 animate-pulse rounded-full bg-surface-alt lg:hidden"
        aria-hidden
      />
    );
  }

  const activeKey = scopeKey(scope);

  const pick = (workspace: Workspace) => {
    setScope(scopeForWorkspace(workspace));
    close();
  };

  const groupOf = (kind: Workspace["kind"], label: string) => {
    const items = filtered.filter((w) => w.kind === kind);
    if (items.length === 0) {
      return null;
    }
    return (
      <div key={kind}>
        <p className="px-2.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {label}
        </p>
        {items.map((workspace) => {
          const active = workspace.key === activeKey;
          return (
            <button
              key={workspace.key}
              type="button"
              role="menuitemradio"
              aria-checked={active}
              onClick={() => pick(workspace)}
              className={cn(
                "flex min-h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[14px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active && "bg-surface-alt font-semibold",
              )}
            >
              <WorkspaceMark workspace={workspace} size={26} />
              <span className="flex-1 truncate">{workspace.name}</span>
              <span className="shrink-0 text-[11.5px] font-normal text-[var(--text-secondary)]">
                {workspace.role}
              </span>
              {active ? (
                <CheckIcon size={16} className="shrink-0 text-primary" />
              ) : null}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex min-w-0 flex-1 lg:hidden">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-[18px] border border-border bg-surface py-1.5 pl-1.5 pr-2.5 text-left shadow-[var(--shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <WorkspaceMark workspace={currentWorkspace} size={28} />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block text-[9.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
            {KIND_LABEL[currentWorkspace.kind]}
          </span>
          <span className="line-clamp-2 break-words text-[13px] font-semibold">
            {currentWorkspace.name}
          </span>
        </span>
        <ChevronDownIcon
          size={16}
          className="shrink-0 text-[var(--text-secondary)]"
        />
      </button>

      {open ? (
        <>
          <div
            className="fixed inset-0 z-40 bg-[rgba(22,27,20,0.42)]"
            onClick={close}
            aria-hidden
          />
          <div

            role="menu"
            aria-label="Workspace and sections"
            className="fixed inset-x-2 top-[62px] z-50 max-h-[calc(100dvh-74px)] overflow-y-auto rounded-[18px] border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
          >
            {/* The workspace block — the same expand-in-place interaction the
                desktop sidebar uses, so the two surfaces feel like one product. */}
            <button
              type="button"
              onClick={() => setListOpen((value) => !value)}
              aria-expanded={listOpen}
              className="mb-2 flex min-h-11 w-full items-center gap-2.5 rounded-[13px] border border-border bg-surface px-2.5 py-2 text-left shadow-[var(--shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <WorkspaceMark workspace={currentWorkspace} size={34} />
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block break-words text-[14px] font-semibold">
                  {currentWorkspace.name}
                </span>
                <span className="block text-[11px] text-[var(--text-secondary)]">
                  {KIND_LABEL[currentWorkspace.kind]}
                  {currentWorkspace.kind === "personal"
                    ? ""
                    : ` · ${currentWorkspace.role}`}
                </span>
              </span>
              <ChevronDownIcon
                size={16}
                className={cn(
                  "shrink-0 text-[var(--text-secondary)] transition-transform",
                  listOpen && "rotate-180",
                )}
              />
            </button>

            {listOpen ? (
              <div>
                {workspaces.length > FILTER_THRESHOLD ? (
                  <div className="mx-0.5 mb-1.5 flex items-center gap-2 rounded-[10px] border border-border bg-surface-alt px-2.5 py-2">
                    <SearchIcon
                      size={15}
                      className="shrink-0 text-[var(--text-muted)]"
                    />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Filter workspaces…"
                      aria-label="Filter workspaces"
                      autoComplete="off"
                      className="min-w-0 flex-1 bg-transparent text-[14px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                    />
                  </div>
                ) : null}

                {groupOf("personal", "Personal")}
                {groupOf("department", "Departments")}
                {groupOf("lab", "Labs")}

                {filtered.length === 0 ? (
                  <p className="px-3 py-4 text-center text-[13px] text-[var(--text-muted)]">
                    No workspace matches “{query}”.
                  </p>
                ) : null}

                <div className="my-1.5 border-t border-[var(--divider)]" />
                <button
                  type="button"
                  onClick={() => {
                    goToSection("labs");
                    close();
                  }}
                  className="flex min-h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[14px] text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-[8px] bg-surface-alt">
                    <PlusIcon size={14} />
                  </span>
                  Browse &amp; create
                </button>
              </div>
            ) : (
              <div>
                {groups.map((group) => (
                  <div key={group.label}>
                    <p className="px-2.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                      {group.label}
                    </p>
                    {group.items.map((item) => {
                      const active = section === item.key;
                      return (
                        <button
                          key={`${group.label}-${item.key}`}
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            goToSection(item.key);
                            close();
                          }}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex min-h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[14px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            active
                              ? "bg-surface-alt font-semibold text-[var(--text-primary)]"
                              : "text-[var(--text-secondary)]",
                          )}
                        >
                          <NavIconFor icon={item.icon} size={18} />
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                ))}

                {scope.kind === "department" ? (
                  <p className="px-3 pb-2 pt-1 text-center text-[11.5px] leading-relaxed text-[var(--text-muted)] [text-wrap:pretty]">
                    Research feeds are matched to a lab or to you. A department&apos;s
                    Opportunities lists the calls only a department can take on.
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
