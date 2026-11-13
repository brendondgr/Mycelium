"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Lock } from "lucide-react";

import { useAppHref, useAppRouter } from "@/components/demo/demo-context";
import { usePortal } from "@/components/portal/portal-context";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { ContextPicker } from "@/components/portal/settings/context-picker";
import { MembershipPage, TransferPage } from "@/components/portal/settings/membership-pages";
import {
  DeptPage,
  LabPage,
  PAGE_DESCRIPTIONS,
  YouPage,
} from "@/components/portal/settings/settings-pages";
import { canonicalPath } from "@/lib/demo";
import { useEntitlements } from "@/lib/portal/hooks";
import {
  contextKey,
  parseSettingsPath,
  settingsHomeFor,
  settingsPagesFor,
  settingsPath,
  YOU_CONTEXT,
  type OrgPageKey,
  type SettingsContext,
  type SettingsPage,
  type YouPageKey,
} from "@/lib/portal/settings";

/**
 * The Settings area: a top bar (what you are configuring, then that context's
 * pages as a row of tabs) over one column of stacked cards.
 *
 * Everything it needs comes from the path — never from `?ws=`, which names the
 * workspace the reader came from, not the org being configured. Which pages are
 * listed comes from the caller's capabilities for that org; a page they cannot
 * open is not listed, and a deep link to one lands on the context's first page.
 */
export function SettingsArea() {
  const pathname = canonicalPath(usePathname());
  const router = useAppRouter();
  const { scope, labs, departments, workspacesLoading } = usePortal();
  const { data: entitlements } = useEntitlements();
  const billingOn = entitlements?.billing_mode !== "off";

  const parsed = parseSettingsPath(pathname);
  const context: SettingsContext = parsed?.context ?? YOU_CONTEXT;
  const lab = context.kind === "lab" ? (labs.find((l) => l.slug === context.slug) ?? null) : null;
  const dept =
    context.kind === "department" ? (departments.find((d) => d.id === context.id) ?? null) : null;
  const org = lab ?? dept;
  const pages = settingsPagesFor(context, org, { billingOn });
  const page = pages.find((p) => p.key === parsed?.page) ?? null;
  const resolving = context.kind !== "you" && workspacesLoading;
  const stranger = context.kind !== "you" && !resolving && !org;

  // A bare `/app/settings` opens the workspace the reader came from; an
  // unknown or unavailable page opens the context's first page. `replace`, so
  // Back does not bounce through the redirect.
  const target = !parsed
    ? workspacesLoading
      ? null
      : settingsHomeFor(scope)
    : !resolving && !stranger && !page && pages.length
      ? settingsPath(context, pages[0].key)
      : null;
  React.useEffect(() => {
    if (target) router.replace(target);
  }, [target, router]);

  return (
    <div className="ws-settings-area">
      <header className="ws-settings-topbar">
        <p className="ws-kicker m-0">Settings</p>
        <ContextPicker current={context} />
        {pages.length && !stranger ? (
          <SettingsTabs context={context} pages={pages} current={page?.key ?? null} />
        ) : null}
      </header>

      {stranger ? (
        <NotAMember context={context} />
      ) : resolving || !page ? (
        <div className="ws-settings-stack" aria-busy="true">
          <div className="h-24 animate-pulse rounded-2xl bg-surface-alt" />
          <div className="h-40 animate-pulse rounded-2xl bg-surface-alt" />
        </div>
      ) : (
        <SettingsPageFrame
          context={context}
          page={page}
          body={
            context.kind === "you" ? (
              <YouPage page={page.key as YouPageKey} />
            ) : page.key === "membership" || page.key === "transfer" ? (
              (() => {
                const which = lab
                  ? ({ kind: "lab", lab } as const)
                  : ({ kind: "department", dept: dept! } as const);
                return page.key === "membership" ? (
                  <MembershipPage org={which} />
                ) : (
                  <TransferPage org={which} />
                );
              })()
            ) : lab ? (
              <LabPage lab={lab} page={page.key as OrgPageKey} />
            ) : (
              <DeptPage dept={dept!} page={page.key as OrgPageKey} />
            )
          }
        />
      )}
    </div>
  );
}

/**
 * The context's pages, as links. A row that scrolls sideways on a phone rather
 * than wrapping into a block of chips; the current tab is scrolled into view so
 * a deep link to the last page does not open with it off-screen.
 */
function SettingsTabs({
  context,
  pages,
  current,
}: {
  context: SettingsContext;
  pages: SettingsPage[];
  current: string | null;
}) {
  const appHref = useAppHref();
  const listRef = React.useRef<HTMLUListElement>(null);

  React.useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    const list = listRef.current;
    if (!active || !list) return;
    // Scroll the strip only, never the page.
    const left = active.offsetLeft - (list.clientWidth - active.offsetWidth) / 2;
    list.scrollTo({ left: Math.max(0, left) });
  }, [current, context]);

  return (
    <nav aria-label="Settings pages">
      <ul ref={listRef} className="ws-settings-tabs">
        {pages.map((p) => (
          <li key={p.key}>
            <Link
              href={appHref(settingsPath(context, p.key))}
              aria-current={p.key === current ? "page" : undefined}
              className="ws-settings-tab"
            >
              {p.label}
              {p.readOnly ? (
                <>
                  <Lock size={12} aria-hidden="true" className="opacity-70" />
                  <span className="sr-only"> (read only)</span>
                </>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** One page: its title, whose settings these are, why it is read-only, then the cards. */
function SettingsPageFrame({
  context,
  page,
  body,
}: {
  context: SettingsContext;
  page: SettingsPage;
  body: React.ReactNode;
}) {
  const description = PAGE_DESCRIPTIONS[`${context.kind}:${page.key}`];
  return (
    <section className="ws-settings-page" aria-labelledby="settings-page-title" key={contextKey(context)}>
      <div>
        <h1
          id="settings-page-title"
          className="font-serif text-[26px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]"
        >
          {page.label}
        </h1>
        {description ? (
          <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
        ) : null}
      </div>
      {page.readOnly && page.reason ? (
        <p role="note" className="ws-settings-readonly">
          <Lock size={14} aria-hidden="true" className="mt-[3px] shrink-0" />
          <span>
            <span className="font-semibold">Read only.</span> {page.reason}
          </span>
        </p>
      ) : null}
      <div className="ws-settings-stack">{body}</div>
    </section>
  );
}

function NotAMember({ context }: { context: SettingsContext }) {
  const appHref = useAppHref();
  const noun = context.kind === "department" ? "department" : "lab";
  return (
    <EmptyState
      title={`You are not a member of this ${noun}`}
      description={`Settings for a ${noun} are open to its members. If you were in it, you may have left, or the link may be mistyped.`}
      action={
        <Link
          href={appHref(settingsPath(YOU_CONTEXT))}
          className="inline-flex rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Open your own settings
        </Link>
      }
    />
  );
}
