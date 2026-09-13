"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { PlusIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { WorkspaceMark } from "@/components/portal/workspace-mark";
import { KIND_LABEL, scopeForWorkspace } from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

/** What the hover label is currently describing, and where to draw it. */
type TipState = { label: string; kind: string; x: number; y: number } | null;

/**
 * The rail's hover label.
 *
 * Two reasons this is hand-built rather than a native `title`. First, `title` is
 * styled by the browser, delayed by about a second, and never shown on keyboard
 * focus — so the users who most need a 34px mark explained are exactly the ones
 * who never get it. Second, and decisively: the rail scrolls, and a scroll
 * container clips on **both** axes, so a label drawn inside it would be cut off
 * at the rail's 60px edge. It is therefore portalled to `document.body` and
 * positioned from the tile's measured rect, which no ancestor can clip.
 *
 * `aria-hidden` is deliberate — each tile already carries this text as its
 * accessible name, and announcing it twice is worse than not announcing it.
 */
function RailTooltip({ tip }: { tip: TipState }) {
  // `tip` is only ever set from a pointer or focus event, so by the time there
  // is something to draw we are unambiguously on the client. Checking for the
  // document directly is the honest guard — a mounted flag in state would be a
  // render just to learn something already known.
  if (!tip || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <span
      aria-hidden
      style={{
        left: tip.x,
        top: tip.y,
        // Set inline, with a literal fallback, rather than as a utility class.
        // The label floats over page content, so a background that fails to
        // resolve for any reason leaves text sitting directly on whatever is
        // underneath — unreadable, and the one failure mode worth spending an
        // inline style to rule out entirely.
        backgroundColor: "var(--brand-panel, #2f3b24)",
        color: "var(--brand-panel-foreground, #f2ebdd)",
      }}
      className="pointer-events-none fixed z-[60] -translate-y-1/2 whitespace-nowrap rounded-lg border border-[var(--divider)] px-2.5 py-1.5 text-[12px] font-medium leading-tight shadow-[var(--shadow)]"
    >
      {/* A small notch, so the label reads as attached to its tile. */}
      <span
        style={{ backgroundColor: "var(--brand-panel, #2f3b24)" }}
        className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 border-b border-l border-[var(--divider)]"
      />
      <span className="relative">
        {tip.label}
        {/* The personal space is named after its own kind, so qualifying it
            would read "Personal Personal". */}
        {tip.kind && tip.kind !== tip.label ? (
          <span className="ml-1.5 opacity-60">{tip.kind}</span>
        ) : null}
      </span>
    </span>,
    document.body,
  );
}

/**
 * The desktop workspace rail — a narrow always-visible column at the far left,
 * before the section sidebar: the personal space, then departments, then labs,
 * then a way to create or join one.
 *
 * It replaces a two-position slider whose right half changed meaning depending
 * on how many labs you were in (a button with one, a dropdown with several).
 * A rail has no such ambiguity: every workspace is its own target, always in the
 * same place, and switching costs one click with nothing to open first.
 *
 * Hidden below `lg`. A rail is a desktop idea — shrunk to phone width the marks
 * stop being recognisable — so mobile drops it entirely and uses
 * `WorkspaceSheet` instead.
 */
export function WorkspaceRail() {
  const { workspaces, workspacesLoading, scope, setScope, goToSection } =
    usePortal();
  const [tip, setTip] = useState<TipState>(null);

  /** Measure the tile so the portalled label can sit beside it. */
  const showTip = useCallback(
    (element: HTMLElement, label: string, kind: string) => {
      const rect = element.getBoundingClientRect();
      setTip({
        label,
        kind,
        x: Math.round(rect.right + 10),
        y: Math.round(rect.top + rect.height / 2),
      });
    },
    [],
  );
  const hideTip = useCallback(() => setTip(null), []);

  // A label measured against the viewport goes stale the moment anything moves.
  useEffect(() => {
    if (!tip) {
      return;
    }
    window.addEventListener("scroll", hideTip, true);
    window.addEventListener("resize", hideTip);
    return () => {
      window.removeEventListener("scroll", hideTip, true);
      window.removeEventListener("resize", hideTip);
    };
  }, [tip, hideTip]);

  if (workspacesLoading) {
    return (
      <div
        className="hidden w-[60px] shrink-0 flex-col items-center gap-2 border-r border-[var(--divider)] py-3 lg:flex"
        aria-hidden
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-[34px] w-[34px] animate-pulse rounded-[11px] bg-surface-alt"
          />
        ))}
      </div>
    );
  }

  const personal = workspaces.filter((w) => w.kind === "personal");
  const orgs = workspaces.filter((w) => w.kind !== "personal");
  const activeKey =
    scope.kind === "lab"
      ? scope.slug
      : scope.kind === "department"
        ? scope.id
        : personal[0]?.key;

  /** Hover and focus both raise the label, and both take it away again. */
  const tipHandlers = (label: string, kind: string) => ({
    onMouseEnter: (event: React.MouseEvent<HTMLElement>) =>
      showTip(event.currentTarget, label, kind),
    onFocus: (event: React.FocusEvent<HTMLElement>) =>
      showTip(event.currentTarget, label, kind),
    onMouseLeave: hideTip,
    onBlur: hideTip,
  });

  return (
    <>
      <nav
        aria-label="Workspaces"
        className="hidden w-[60px] shrink-0 flex-col items-center gap-1.5 overflow-y-auto border-r border-[var(--divider)] bg-[color-mix(in_srgb,var(--surface-alt)_55%,var(--background))] py-3 lg:flex"
      >
        {[personal, orgs].map((group, groupIndex) =>
          group.length === 0 ? null : (
            <div
              key={groupIndex}
              className="flex w-full flex-col items-center gap-1.5"
            >
              {groupIndex === 1 ? (
                <span
                  className="my-1 h-px w-6 shrink-0 bg-[var(--divider)]"
                  aria-hidden
                />
              ) : null}
              {group.map((workspace) => {
                const active = workspace.key === activeKey;
                const kind = KIND_LABEL[workspace.kind];
                return (
                  <button
                    key={workspace.key}
                    type="button"
                    onClick={() => {
                      hideTip();
                      setScope(scopeForWorkspace(workspace));
                    }}
                    aria-current={active ? "true" : undefined}
                    aria-label={`${workspace.name} · ${kind}`}
                    {...tipHandlers(workspace.name, kind)}
                    className={cn(
                      "relative grid h-[38px] w-[38px] shrink-0 place-items-center rounded-xl transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "opacity-100" : "opacity-70 hover:opacity-100",
                    )}
                  >
                    {/*
                      The active workspace is marked twice over: a green edge bar
                      and a ring. Neither is colour alone — `aria-current` carries
                      it for anyone who can't see either.
                    */}
                    {active ? (
                      <span
                        aria-hidden
                        className="absolute -left-[11px] top-1/2 h-[22px] w-[3px] -translate-y-1/2 rounded-r-[3px] bg-primary"
                      />
                    ) : null}
                    <WorkspaceMark
                      workspace={workspace}
                      size={34}
                      radius={active ? 9 : 11}
                      className={cn(
                        "transition-[border-radius]",
                        active &&
                          "ring-2 ring-primary ring-offset-2 ring-offset-[var(--background)]",
                      )}
                    />
                  </button>
                );
              })}
            </div>
          ),
        )}

        <span
          className="my-1 h-px w-6 shrink-0 bg-[var(--divider)]"
          aria-hidden
        />
        <button
          type="button"
          onClick={() => {
            hideTip();
            goToSection("labs");
          }}
          aria-label="Browse and create workspaces"
          {...tipHandlers("Browse & create", "")}
          className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[11px] border border-dashed border-border text-[var(--text-muted)] transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <PlusIcon size={16} />
        </button>
      </nav>

      <RailTooltip tip={tip} />
    </>
  );
}
