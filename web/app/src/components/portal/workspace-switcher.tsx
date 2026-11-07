"use client";

import { Check, ChevronDown, Plus } from "lucide-react";

import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { useDismissable } from "@/lib/portal/use-dismissable";
import { KIND_LABEL, scopeForWorkspace, type Workspace } from "@/lib/portal/workspace";

/**
 * The header's workspace dropdown (desktop): the active workspace's mark and
 * name, opening onto every workspace you belong to — personal, then labs, then
 * departments — and a way to browse or create one.
 *
 * It replaces the left workspace rail. The rail cost a whole column for a
 * choice made a few times a day, and could not spell a name; the dropdown says
 * where you are in words and switching is still two clicks. Phones use
 * `WorkspaceSheet`, which carries the same list; ⌘K (`WorkspacePalette`)
 * reaches it from anywhere.
 */
export function WorkspaceSwitcher() {
  const { workspaces, workspacesLoading, currentWorkspace, setScope, goToSection } = usePortal();
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  if (workspacesLoading) {
    return <div className="ws-scope-skel hidden lg:block" aria-hidden />;
  }

  const groups: [Workspace["kind"], string][] = [
    ["personal", "Personal"],
    ["lab", "Labs"],
    ["department", "Departments"],
  ];

  return (
    <div ref={ref} className="ws-scope hidden lg:block">
      <button
        type="button"
        className="ws-scope-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Workspace: ${currentWorkspace.name}. Switch workspace`}
        onClick={() => setOpen((v) => !v)}
      >
        <WorkspaceMark workspace={currentWorkspace} size={26} radius={currentWorkspace.kind === "personal" ? 13 : 8} />
        <span className="ws-scope-name">{currentWorkspace.name}</span>
        <ChevronDown size={14} aria-hidden="true" className="ws-caret" data-open={open || undefined} />
      </button>
      {open ? (
        <div className="ws-menu" role="menu" aria-label="Switch workspace">
          {groups.map(([kind, label]) => {
            const list = workspaces.filter((w) => w.kind === kind);
            if (list.length === 0) return null;
            return (
              <div key={kind} role="group" aria-label={label}>
                <p className="ws-menu-label">{label}</p>
                {list.map((w) => {
                  const active = w.key === currentWorkspace.key;
                  return (
                    <button
                      key={w.key}
                      type="button"
                      role="menuitemradio"
                      aria-checked={active}
                      className="ws-menu-item"
                      onClick={() => {
                        setScope(scopeForWorkspace(w));
                        setOpen(false);
                      }}
                    >
                      <WorkspaceMark workspace={w} size={26} radius={w.kind === "personal" ? 13 : 8} />
                      <span className="min-w-0">
                        <span className="ws-menu-name">{w.name}</span>
                        <span className="ws-menu-hint">{KIND_LABEL[w.kind]} workspace</span>
                      </span>
                      {active ? <Check size={14} aria-hidden="true" className="ws-menu-check" /> : null}
                    </button>
                  );
                })}
              </div>
            );
          })}
          <div className="ws-menu-sep" />
          <button
            type="button"
            role="menuitem"
            className="ws-menu-item"
            onClick={() => {
              setOpen(false);
              goToSection("labs");
            }}
          >
            <span className="ws-menu-plus" aria-hidden="true">
              <Plus size={14} />
            </span>
            <span className="ws-menu-name">Browse &amp; create workspaces</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
