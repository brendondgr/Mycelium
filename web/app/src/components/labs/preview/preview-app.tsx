"use client";

import * as React from "react";
import {
  Award,
  Bell,
  Bookmark,
  Check,
  ChevronDown,
  FileText,
  FolderKanban,
  Landmark,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Presentation,
  LogOut,
  ScrollText,
  Search,
  Settings,
  Sparkles,
  UserRound,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";

import type { LabsState, OptionValue, PageKey } from "@/components/labs/schema";
import { SCOPES, type Scope } from "@/components/labs/preview/fixtures";
import { Ground } from "@/components/labs/preview/ground";
import { ItemDetail, PreviewContext, useDismiss, type Detail } from "@/components/labs/preview/parts";
import { FeedPage } from "@/components/labs/preview/pages/feed";
import { OverviewPage } from "@/components/labs/preview/pages/overview";
import { SearchPage } from "@/components/labs/preview/pages/search";
import { SettingsPage } from "@/components/labs/preview/pages/settings";
import { PageSkeleton } from "@/components/labs/preview/skeleton";

type NavEntry = { key: string; label: string; icon: LucideIcon; page?: PageKey; section?: string };

const NAV: { label: string; items: NavEntry[] }[] = [
  {
    label: "Today",
    items: [
      { key: "overview", label: "Overview", icon: LayoutDashboard, page: "overview" },
      { key: "search", label: "Search", icon: Search, page: "search" },
    ],
  },
  {
    label: "Feeds",
    items: [
      { key: "papers", label: "Papers", icon: FileText, page: "papers" },
      { key: "grants", label: "Grants", icon: Landmark, page: "grants" },
      { key: "fellowships", label: "Fellowships", icon: Award, page: "fellowships" },
      { key: "conferences", label: "Conferences", icon: Presentation, page: "conferences" },
    ],
  },
  {
    label: "Lab",
    items: [
      { key: "projects", label: "Projects", icon: FolderKanban },
      { key: "members", label: "Members", icon: Users, page: "settings", section: "members" },
      { key: "saves", label: "Saves", icon: Bookmark },
      { key: "reports", label: "Reports", icon: ScrollText },
    ],
  },
  {
    label: "Settings",
    items: [{ key: "settings", label: "Settings", icon: Settings, page: "settings", section: "account" }],
  },
];

const ALL_NAV = NAV.flatMap((g) => g.items);
const MOBILE_TABS = ["overview", "papers", "grants", "fellowships", "search"];

function ScopeMenu({ scope, setScope }: { scope: Scope; setScope: (s: Scope) => void }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const close = React.useCallback(() => setOpen(false), []);
  useDismiss(open, close, ref);

  const groups: [Scope["kind"], string][] = [
    ["personal", "Personal"],
    ["lab", "Labs"],
    ["department", "Departments"],
  ];

  return (
    <div className="lx-scope" ref={ref}>
      <button
        type="button"
        className="lx-scope-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="lx-scope-mark" data-kind={scope.kind} aria-hidden="true">
          {scope.short}
        </span>
        <span className="lx-scope-name">{scope.name}</span>
        <ChevronDown size={14} aria-hidden="true" className="lx-caret" data-open={open || undefined} />
      </button>
      {open ? (
        <div className="lx-menu" role="menu" aria-label="Switch workspace">
          {groups.map(([kind, label]) => (
            <div key={kind} role="group" aria-label={label}>
              <p className="lx-menu-label">{label}</p>
              {SCOPES.filter((s) => s.kind === kind).map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={s.id === scope.id}
                  className="lx-menu-item"
                  onClick={() => {
                    setScope(s);
                    setOpen(false);
                  }}
                >
                  <span className="lx-scope-mark" data-kind={s.kind} aria-hidden="true">
                    {s.short}
                  </span>
                  <span>
                    <span className="lx-menu-name">{s.name}</span>
                    <span className="lx-menu-hint">{s.hint}</span>
                  </span>
                  {s.id === scope.id ? <Check size={14} aria-hidden="true" className="lx-menu-check" /> : null}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function NavList({
  current,
  go,
  collapsed = false,
}: {
  current: string;
  go: (key: string) => void;
  collapsed?: boolean;
}) {
  return (
    <nav aria-label="Workspace sections" className="lx-navlist">
      {NAV.map((group) => (
        <div key={group.label} className="lx-nav-group">
          <p className="lx-nav-label">{group.label}</p>
          {group.items.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                type="button"
                className="lx-nav-item"
                aria-current={current === item.key ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                onClick={() => go(item.key)}
              >
                <Icon size={17} aria-hidden="true" />
                <span className="lx-nav-text">{item.label}</span>
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

/**
 * The avatar opens the account menu: the one obvious door to settings, from
 * any page, at any width.
 */
function AccountMenu({
  theme,
  setTheme,
  goSettings,
}: {
  theme: string;
  setTheme: (v: string) => void;
  goSettings: (section: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const close = React.useCallback(() => setOpen(false), []);
  useDismiss(open, close, ref);
  const item = (section: string, label: string, Icon: LucideIcon) => (
    <button
      type="button"
      role="menuitem"
      className="lx-menu-item"
      onClick={() => {
        setOpen(false);
        goSettings(section);
      }}
    >
      <Icon size={15} aria-hidden="true" className="lx-menu-icon" />
      <span className="lx-menu-name">{label}</span>
    </button>
  );
  return (
    <div className="lx-account" ref={ref}>
      <button
        type="button"
        className="lx-me"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu for Ama Owusu"
        onClick={() => setOpen((v) => !v)}
      >
        AO
      </button>
      {open ? (
        <div className="lx-menu lx-menu-right" role="menu" aria-label="Account">
          <div className="lx-menu-who">
            <span className="lx-menu-name">Ama Owusu</span>
            <span className="lx-menu-hint">ama.owusu@university.edu</span>
          </div>
          {item("account", "Account", UserRound)}
          {item("notifications", "Notifications", Bell)}
          {item("mylo", "Mylo & you", Sparkles)}
          <div className="lx-menu-sep" role="separator" />
          <p className="lx-menu-label">Pulse Lab</p>
          {item("lab", "Lab settings", Settings)}
          {item("members", "Members", Users)}
          <div className="lx-menu-sep" role="separator" />
          <div className="lx-menu-theme">
            <span className="lx-menu-hint">Theme</span>
            <span className="lx-seg" role="radiogroup" aria-label="Theme">
              {[
                ["night", "Night"],
                ["day", "Day"],
              ].map(([v, l]) => (
                <button key={v} type="button" role="radio" aria-checked={theme === v} onClick={() => setTheme(v)}>
                  {l}
                </button>
              ))}
            </span>
          </div>
          <button type="button" role="menuitem" className="lx-menu-item" onClick={() => setOpen(false)}>
            <LogOut size={15} aria-hidden="true" className="lx-menu-icon" />
            <span className="lx-menu-name">Sign out</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <div className="lx-placeholder lx-rise">
      <h1 className="lx-h lx-page-title">{label}</h1>
      <p className="lx-lede">
        Not in Labs yet. The global options still apply here — describe what you want this page to do in the notes,
        and it can be added as its own preview.
      </p>
    </div>
  );
}

export function PreviewApp({
  state,
  setPage,
  setGlobal,
}: {
  state: LabsState;
  setPage: (page: PageKey) => void;
  /** Lets the preview's own settings page change a Labs option. */
  setGlobal: (id: string, value: OptionValue) => void;
}) {
  const g = state.global;
  const [scope, setScope] = React.useState<Scope>(SCOPES[1]);
  const [railCollapsed, setRailCollapsed] = React.useState(Boolean(g.railCollapsed));
  const [navOpen, setNavOpen] = React.useState(false);
  const [other, setOther] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<Detail | null>(null);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [section, setSection] = React.useState("account");
  const mainRef = React.useRef<HTMLDivElement>(null);
  const detailRef = React.useRef<HTMLDivElement>(null);

  // Reset local UI when the options that own it change — during render, the
  // pattern React recommends over an effect: the rail follows its option, a
  // new way of opening items drops a stale drawer or expansion, and the
  // panel's page switcher leaves any placeholder page.
  const [seen, setSeen] = React.useState({ rail: g.railCollapsed, detail: g.detail, page: state.page });
  if (seen.rail !== g.railCollapsed || seen.detail !== g.detail || seen.page !== state.page) {
    if (seen.rail !== g.railCollapsed) setRailCollapsed(Boolean(g.railCollapsed));
    if (seen.detail !== g.detail) {
      setDetail(null);
      setExpanded(null);
    }
    if (seen.page !== state.page) setOther(null);
    setSeen({ rail: g.railCollapsed, detail: g.detail, page: state.page });
  }

  const current = other ?? state.page;
  // Members is a section of Settings; light whichever one the reader chose.
  const navCurrent = current === "settings" && section === "members" ? "members" : current;

  // A page "loads" whenever the page or the workspace changes: placeholders
  // first, then the content fades in where they stood.
  const delay = g.loading === "skeleton" ? Number(g.loadDelay) : 0;
  const loadKey = `${current}|${section}|${scope.id}`;
  const [loaded, setLoaded] = React.useState<{ key: string; done: boolean }>({ key: "", done: false });
  if (loaded.key !== loadKey) setLoaded({ key: loadKey, done: delay === 0 });
  const loading = !loaded.done && delay > 0;
  React.useEffect(() => {
    if (loaded.done) return;
    const t = window.setTimeout(() => setLoaded((l) => (l.key === loadKey ? { ...l, done: true } : l)), delay);
    return () => window.clearTimeout(t);
  }, [loaded, loadKey, delay]);

  const go = (key: string, sectionOverride?: string) => {
    const entry = ALL_NAV.find((n) => n.key === key);
    setNavOpen(false);
    setDetail(null);
    if (entry?.page) {
      setOther(null);
      if (entry.page === "settings") setSection(sectionOverride ?? entry.section ?? "account");
      setPage(entry.page);
    } else {
      setOther(key);
    }
    mainRef.current?.scrollTo({ top: 0 });
  };

  const ctx = React.useMemo(
    () => ({
      g,
      open: (item: Detail["item"]) => {
        if (g.detail === "inline") setExpanded((cur) => (cur === item.id ? null : item.id));
        else setDetail({ item });
      },
      isExpanded: (id: string) => g.detail === "inline" && expanded === id,
    }),
    [g, expanded],
  );

  React.useEffect(() => {
    if (!detail) return;
    // preventScroll: the drawer is still off-canvas when this runs, and a
    // plain focus() would scroll the whole preview sideways to reveal it.
    detailRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDetail(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [detail]);

  const pageOptions = state.pages;
  const page =
    other !== null ? (
      <Placeholder label={ALL_NAV.find((n) => n.key === other)?.label ?? other} />
    ) : state.page === "overview" ? (
      <OverviewPage o={pageOptions.overview} scope={scope} deadline={pageOptions.grants.deadline as string} go={go} />
    ) : state.page === "settings" ? (
      <SettingsPage key={section} o={pageOptions.settings} g={g} setGlobal={setGlobal} initial={section} />
    ) : state.page === "search" ? (
      <SearchPage o={pageOptions.search} />
    ) : (
      <FeedPage key={state.page} feed={state.page} o={pageOptions[state.page]} />
    );
  const skeletonKind =
    other !== null
      ? "page"
      : state.page === "overview" || state.page === "search" || state.page === "settings"
        ? state.page
        : "feed";
  const readerSkeleton =
    skeletonKind === "feed" && state.page !== "overview" && state.page !== "search" && state.page !== "settings"
      ? pageOptions[state.page].layout === "reader"
      : false;

  const style = {
    "--lx-bg-strength": Number(g.backgroundStrength) / 100,
  } as React.CSSProperties;

  return (
    <PreviewContext.Provider value={ctx}>
      <div
        className="lx-app"
        data-mode={g.theme as string}
        data-density={g.density as string}
        data-nav={g.nav as string}
        data-scope-switcher={g.scopeSwitcher as string}
        data-surfaces={g.surfaces as string}
        data-radius={g.radius as string}
        data-headings={g.headings as string}
        data-width={g.width as string}
        data-motion={g.motion as string}
        data-rail={railCollapsed ? "collapsed" : "expanded"}
        style={style}
      >
        <Ground variant={g.background as string} />

        <header className="lx-header">
          <button
            type="button"
            className="lx-icon-btn lx-menu-btn"
            aria-label="Open navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            <Menu size={18} aria-hidden="true" />
          </button>
          {g.nav === "rail" ? (
            <button
              type="button"
              className="lx-icon-btn lx-rail-toggle"
              aria-label={railCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setRailCollapsed((v) => !v)}
            >
              {railCollapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
            </button>
          ) : null}
          <span className="lx-wordmark">Mycelium</span>
          <span className="lx-scope-slot">
            <ScopeMenu scope={scope} setScope={setScope} />
          </span>
          {g.nav === "tabs" ? (
            <nav className="lx-tabs" aria-label="Workspace sections">
              {ALL_NAV.slice(0, 6).map((n) => (
                <button key={n.key} type="button" aria-current={current === n.key ? "page" : undefined} onClick={() => go(n.key)}>
                  {n.label}
                </button>
              ))}
            </nav>
          ) : null}
          <span className="lx-header-spacer" />
          <button type="button" className="lx-icon-btn" aria-label="Search" onClick={() => go("search")}>
            <Search size={17} aria-hidden="true" />
          </button>
          <button type="button" className="lx-icon-btn lx-bell" aria-label="Notifications, 3 unread">
            <Bell size={17} aria-hidden="true" />
            <span className="lx-bell-dot" aria-hidden="true" />
          </button>
          {pageOptions.settings.accountMenu ? (
            <AccountMenu
              theme={g.theme as string}
              setTheme={(v) => setGlobal("theme", v)}
              goSettings={(sec) => go("settings", sec)}
            />
          ) : (
            <button type="button" className="lx-me" aria-label="Settings" onClick={() => go("settings")}>
              AO
            </button>
          )}
        </header>

        <div className="lx-body">
          {g.scopeSwitcher === "rail" ? (
            <div className="lx-wsrail" aria-label="Workspaces">
              {SCOPES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="lx-scope-mark lx-wsrail-item"
                  data-kind={s.kind}
                  aria-pressed={s.id === scope.id}
                  title={s.name}
                  aria-label={s.name}
                  onClick={() => setScope(s)}
                >
                  {s.short}
                </button>
              ))}
            </div>
          ) : null}
          {g.nav === "rail" ? (
            <aside className="lx-rail">
              <NavList current={navCurrent} go={go} collapsed={railCollapsed} />
            </aside>
          ) : null}
          <div className="lx-main" ref={mainRef}>
            <div className="lx-content" key={loading ? `skeleton-${loadKey}` : loadKey} aria-busy={loading}>
              {loading ? <PageSkeleton kind={skeletonKind} reader={readerSkeleton} /> : page}
            </div>
          </div>
        </div>

        {g.nav !== "drawer" ? (
          <nav className="lx-bottomtabs" aria-label="Sections">
            {MOBILE_TABS.map((key) => {
              const n = ALL_NAV.find((x) => x.key === key)!;
              const Icon = n.icon;
              return (
                <button key={key} type="button" aria-current={current === key ? "page" : undefined} onClick={() => go(key)}>
                  <Icon size={18} aria-hidden="true" />
                  <span>{n.label}</span>
                </button>
              );
            })}
          </nav>
        ) : null}

        {/* Navigation drawer: phones, or "Menu only" at any width. */}
        <div className="lx-sheet-layer lx-sheet-left" data-open={navOpen || undefined}>
          <button type="button" className="lx-scrim" aria-label="Close navigation" tabIndex={navOpen ? 0 : -1} onClick={() => setNavOpen(false)} />
          <div className="lx-sheet" role="dialog" aria-label="Navigation" aria-hidden={!navOpen}>
            <div className="lx-sheet-head">
              <span className="lx-wordmark">Mycelium</span>
              <button type="button" className="lx-icon-btn" aria-label="Close navigation" tabIndex={navOpen ? 0 : -1} onClick={() => setNavOpen(false)}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <NavList current={navCurrent} go={go} />
          </div>
        </div>

        {/* Detail: a right drawer or a centred dialog, per "Opening an item". */}
        <div className="lx-detail-layer" data-open={detail ? true : undefined} data-kind={g.detail as string}>
          <button type="button" className="lx-scrim" aria-label="Close" tabIndex={detail ? 0 : -1} onClick={() => setDetail(null)} />
          <div
            className="lx-detail"
            role="dialog"
            aria-modal="true"
            aria-label={detail?.item.title ?? "Details"}
            aria-hidden={!detail}
            tabIndex={-1}
            ref={detailRef}
          >
            <button type="button" className="lx-icon-btn lx-detail-close" aria-label="Close" tabIndex={detail ? 0 : -1} onClick={() => setDetail(null)}>
              <X size={16} aria-hidden="true" />
            </button>
            {detail ? <ItemDetail key={detail.item.id} item={detail.item} /> : null}
          </div>
        </div>
      </div>
    </PreviewContext.Provider>
  );
}
