/**
 * The Settings area: which context it is configuring, which pages that context
 * offers the reader, and how each page reads in the URL.
 *
 * The context lives in the path — `/app/settings/you/<page>`,
 * `/app/settings/lab/<slug>/<page>`, `/app/settings/department/<id>/<page>` —
 * never in `?ws=`. The workspace a person works in and the org they are
 * configuring are different things: a link to a settings page has to mean the
 * same thing for everyone who opens it, and managing a department must not
 * depend on which workspace the reader was last in. Nothing in Settings reads
 * `?ws=`.
 *
 * Which pages a context lists is decided from the caller's capabilities, read
 * from the server (`can(org, …)`), never from the role. A page the reader may
 * not open is not listed; a page they may read but not change is listed with
 * the reason it is read-only.
 *
 * Pure functions: the server-side redirects from the old routes use them too.
 */

import { CAPABILITY, can, type Capability, type HasCapabilities } from "@/lib/portal/capabilities";
import { PERSONAL_SLUG } from "@/lib/portal/types";
import type { WorkspaceScope } from "@/lib/portal/workspace";

export const SETTINGS_BASE = "/app/settings";

export type SettingsContext =
  | { kind: "you" }
  | { kind: "lab"; slug: string }
  | { kind: "department"; id: string };

export const YOU_CONTEXT: SettingsContext = { kind: "you" };

export type YouPageKey =
  | "account"
  | "profile"
  | "mylo"
  | "collaboration"
  | "delivery"
  | "appearance"
  | "subscription";

export type OrgPageKey =
  | "general"
  | "labs"
  | "people"
  | "projects"
  | "servers"
  | "announcements"
  | "plan"
  | "membership"
  | "transfer";

export type SettingsPageKey = YouPageKey | OrgPageKey;

/** What it takes to see a page: any membership, or any one of the listed rights. */
type Need = "member" | Capability[];

type OrgPageDef = {
  key: OrgPageKey;
  label: string;
  need: Need;
  /** The right that makes the page editable; without it, the page is read-only. */
  edit?: Capability;
  /** Shown on a read-only page: who can change it. */
  reason?: string;
  /** Hidden when the instance runs without billing (`billing.mode = "off"`). */
  billing?: boolean;
};

export type SettingsPage = {
  key: SettingsPageKey;
  label: string;
  /** The reader can see this page but not change it. */
  readOnly: boolean;
  /** Why it is read-only, in the reader's terms. Null when it is editable. */
  reason: string | null;
};

const YOU_PAGES: { key: YouPageKey; label: string }[] = [
  { key: "account", label: "Account" },
  { key: "profile", label: "Profile & themes" },
  { key: "mylo", label: "Mylo & you" },
  { key: "collaboration", label: "Collaboration" },
  { key: "delivery", label: "Delivery" },
  { key: "appearance", label: "Appearance" },
  { key: "subscription", label: "Subscription" },
];

const LAB_MANAGERS = "the lab's PI, owners and admins";
const DEPT_MANAGERS = "the department head and its admins";

const LAB_PAGES: OrgPageDef[] = [
  {
    key: "general",
    label: "General",
    need: "member",
    edit: CAPABILITY.PROFILE_EDIT,
    reason: `Only ${LAB_MANAGERS} can change the lab's profile.`,
  },
  {
    key: "people",
    label: "People",
    need: [CAPABILITY.PEOPLE_VIEW],
    edit: CAPABILITY.PEOPLE_MANAGE,
    reason: `Only ${LAB_MANAGERS} can change roles, invite or remove people.`,
  },
  { key: "projects", label: "Projects", need: [CAPABILITY.PROJECTS_POLICY] },
  {
    key: "servers",
    label: "Mylo & servers",
    need: [CAPABILITY.SERVERS_MANAGE, CAPABILITY.MYLO_POLICY],
  },
  { key: "announcements", label: "Announcements", need: [CAPABILITY.ANNOUNCEMENTS_MANAGE] },
  {
    key: "plan",
    label: "Plan",
    need: "member",
    edit: CAPABILITY.BILLING_MANAGE,
    reason: `Only ${LAB_MANAGERS} can change the lab's plan.`,
    billing: true,
  },
  { key: "membership", label: "Your membership", need: "member" },
  { key: "transfer", label: "Transfer & close", need: [CAPABILITY.TRANSFER] },
];

const DEPT_PAGES: OrgPageDef[] = [
  {
    key: "general",
    label: "General",
    need: "member",
    edit: CAPABILITY.PROFILE_EDIT,
    reason: `Only ${DEPT_MANAGERS} can change the department's profile.`,
  },
  {
    key: "labs",
    label: "Labs",
    need: "member",
    edit: CAPABILITY.PEOPLE_MANAGE,
    reason: `Only ${DEPT_MANAGERS} can add or remove labs.`,
  },
  {
    key: "people",
    label: "People",
    need: [CAPABILITY.PEOPLE_VIEW],
    edit: CAPABILITY.PEOPLE_MANAGE,
    reason: `Only ${DEPT_MANAGERS} can change roles, invite or remove people.`,
  },
  { key: "projects", label: "Projects", need: [CAPABILITY.PROJECTS_POLICY] },
  {
    key: "servers",
    label: "Mylo & servers",
    need: [CAPABILITY.SERVERS_MANAGE, CAPABILITY.MYLO_POLICY],
  },
  { key: "announcements", label: "Announcements", need: [CAPABILITY.ANNOUNCEMENTS_MANAGE] },
  {
    key: "plan",
    label: "Plan",
    need: "member",
    edit: CAPABILITY.BILLING_MANAGE,
    reason: `Only ${DEPT_MANAGERS} can change the department's plan.`,
    billing: true,
  },
  { key: "membership", label: "Your membership", need: "member" },
  { key: "transfer", label: "Transfer & close", need: [CAPABILITY.TRANSFER] },
];

/** Whether the caller belongs to the org at all: every preset holds a capability. */
export function isMember(org: HasCapabilities | null | undefined): boolean {
  return Boolean(org?.capabilities && org.capabilities.length > 0);
}

function meets(org: HasCapabilities | null | undefined, need: Need): boolean {
  if (need === "member") return isMember(org);
  return need.some((capability) => can(org, capability));
}

export type PagesOptions = {
  /** False when the instance runs with `billing.mode = "off"`. */
  billingOn: boolean;
};

/**
 * The pages a context offers this reader, in tab order. `org` is the caller's
 * lab or department row (`MyLab` / `MyDepartment`) for an org context, and is
 * ignored for "you". A stranger to the org gets no pages at all.
 */
export function settingsPagesFor(
  context: SettingsContext,
  org: HasCapabilities | null | undefined,
  options: PagesOptions,
): SettingsPage[] {
  if (context.kind === "you") {
    return YOU_PAGES.map((page) => ({ ...page, readOnly: false, reason: null }));
  }
  const defs = context.kind === "lab" ? LAB_PAGES : DEPT_PAGES;
  return defs
    .filter((def) => meets(org, def.need))
    .filter((def) => !def.billing || options.billingOn)
    .map((def) => {
      const readOnly = def.edit ? !can(org, def.edit) : false;
      return {
        key: def.key,
        label: def.label,
        readOnly,
        reason: readOnly ? (def.reason ?? null) : null,
      };
    });
}

/** The first page a context opens on. Every member can read General. */
export function defaultPageFor(context: SettingsContext): SettingsPageKey {
  return context.kind === "you" ? "account" : "general";
}

/** The URL of a settings page. No page → the context's default page. */
export function settingsPath(context: SettingsContext, page?: SettingsPageKey): string {
  const target = page ?? defaultPageFor(context);
  switch (context.kind) {
    case "lab":
      return `${SETTINGS_BASE}/lab/${encodeURIComponent(context.slug)}/${target}`;
    case "department":
      return `${SETTINGS_BASE}/department/${encodeURIComponent(context.id)}/${target}`;
    default:
      return `${SETTINGS_BASE}/you/${target}`;
  }
}

export type ParsedSettingsPath = {
  context: SettingsContext;
  /** The page segment as written, or null when the URL names only the context. */
  page: string | null;
};

/**
 * Read the context and page out of a settings pathname. Returns null for a
 * path outside Settings or one that names no context (`/app/settings`).
 */
export function parseSettingsPath(pathname: string): ParsedSettingsPath | null {
  if (pathname !== SETTINGS_BASE && !pathname.startsWith(`${SETTINGS_BASE}/`)) {
    return null;
  }
  const parts = pathname
    .slice(SETTINGS_BASE.length)
    .split("/")
    .filter(Boolean)
    .map((part) => decodeURIComponent(part));
  const [kind, ...rest] = parts;
  if (kind === "you") {
    return { context: YOU_CONTEXT, page: rest[0] ?? null };
  }
  if ((kind === "lab" || kind === "department") && rest[0]) {
    const context: SettingsContext =
      kind === "lab" ? { kind: "lab", slug: rest[0] } : { kind: "department", id: rest[0] };
    return { context, page: rest[1] ?? null };
  }
  return null;
}

/** The settings context a workspace opens: entering Settings from it lands there. */
export function contextForScope(scope: WorkspaceScope): SettingsContext {
  switch (scope.kind) {
    case "lab":
      return { kind: "lab", slug: scope.slug };
    case "department":
      return { kind: "department", id: scope.id };
    default:
      return YOU_CONTEXT;
  }
}

/** Where the sidebar's one Settings entry goes from a workspace. */
export function settingsHomeFor(scope: WorkspaceScope): string {
  return settingsPath(contextForScope(scope));
}

/** A stable key for a context, for comparing and for list keys. */
export function contextKey(context: SettingsContext): string {
  switch (context.kind) {
    case "lab":
      return `lab:${context.slug}`;
    case "department":
      return `department:${context.id}`;
    default:
      return "you";
  }
}

/* -------------------------------------------------------------------------- */
/* The old routes                                                              */
/* -------------------------------------------------------------------------- */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The org an old `?ws=` key named. Department ids are UUIDs and lab slugs never
 * are, so the redirect can tell them apart without a request; the settings page
 * then checks the reader actually belongs to it.
 */
function contextFromWorkspaceKey(ws: string | null | undefined): SettingsContext {
  if (!ws || ws === PERSONAL_SLUG) return YOU_CONTEXT;
  return UUID.test(ws) ? { kind: "department", id: ws } : { kind: "lab", slug: ws };
}

export type LegacySettingsRoute = "account" | "profile" | "mylo" | "billing" | "department";

/**
 * Where an old settings route sends a reader. The old pages took their org from
 * `?ws=`, so that parameter picks the context here once, and is then dropped.
 */
export function legacySettingsPath(
  route: LegacySettingsRoute,
  params: {
    ws?: string | null;
    id?: string | null;
    /** `?discord=` / `?slack=` from an OAuth return that still names the old page. */
    returned?: { discord?: string | null; slack?: string | null };
  } = {},
): string {
  switch (route) {
    case "profile": {
      const context = contextFromWorkspaceKey(params.ws);
      // A Discord or Slack link attempt used to land on the old Profile page;
      // its outcome is read by the card that now lives on Delivery.
      const outcome = Object.entries(params.returned ?? {}).filter(
        (entry): entry is [string, string] => Boolean(entry[1]),
      );
      if (context.kind === "you" && outcome.length) {
        const query = outcome
          .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
          .join("&");
        return `${settingsPath(YOU_CONTEXT, "delivery")}?${query}`;
      }
      return settingsPath(context, context.kind === "you" ? "profile" : "general");
    }
    case "billing": {
      const context = contextFromWorkspaceKey(params.ws);
      return settingsPath(context, context.kind === "you" ? "subscription" : "plan");
    }
    case "department":
      return params.id
        ? settingsPath({ kind: "department", id: params.id }, "general")
        : settingsPath(YOU_CONTEXT);
    case "mylo":
      return settingsPath(YOU_CONTEXT, "mylo");
    default:
      return settingsPath(YOU_CONTEXT, "account");
  }
}
