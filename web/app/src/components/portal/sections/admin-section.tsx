"use client";

import * as React from "react";

import { ShieldIcon } from "@/components/portal/icons";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill, type PillTone } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { Button } from "@/components/ui/button";
import {
  useAdminLab,
  useAdminLabs,
  useAdminUser,
  useAdminUsers,
  useEntitlements,
  useUpdateAdminLab,
  useUpdateAdminUser,
} from "@/lib/portal/hooks";
import type {
  AdminLabDetail,
  AdminLabRow,
  AdminLabTier,
  AdminLabUpdate,
  AdminPersonalTier,
  AdminOrgStatus,
  AdminSubscriptionStatus,
  AdminTier,
  AdminUserDetail,
  AdminUserRow,
  AdminUserUpdate,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const INPUT_CLASS =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * A tier names who it covers, so each scope is offered only what it is sold. Free and
 * Spore cover one researcher; Mycelium Lab and Canopy are priced per member and are
 * granted on the lab or department that has the roster. The API narrows its choices the
 * same way, so this is a convenience, not the gate.
 */
const PERSONAL_TIERS: { value: AdminPersonalTier; label: string }[] = [
  { value: "free", label: "Free" },
  { value: "spore", label: "Spore" },
];

const LAB_TIERS: { value: AdminLabTier; label: string }[] = [
  { value: "lab", label: "Mycelium Lab" },
  { value: "canopy", label: "Canopy" },
];

const STATUSES: { value: AdminSubscriptionStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "past_due", label: "Past due" },
  { value: "canceled", label: "Canceled" },
];

/** Org plans additionally carry the created-but-not-granting `inactive` state. */
const ORG_STATUSES: { value: AdminOrgStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive (granted nothing yet)" },
  { value: "past_due", label: "Past due" },
  { value: "canceled", label: "Canceled" },
];

/** Duration presets; "" = leave the current expiry untouched. */
const DURATIONS: { value: string; label: string }[] = [
  { value: "", label: "Keep current expiry" },
  { value: "none", label: "No expiry (open-ended)" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "180", label: "180 days" },
  { value: "365", label: "1 year" },
];

/**
 * How a lab's plan ends. "Never" is the free case: no end date and comped, which is
 * what the lab's plan page renders as a struck-through price. Everything else lapses
 * on a date, after which the read path stops granting and the lab falls back to Free —
 * nothing is ever deleted.
 */
const LAB_ENDINGS: { value: string; label: string }[] = [
  { value: "", label: "Keep as is" },
  { value: "never", label: "Never — free / complimentary" },
  { value: "30", label: "Ends in 30 days" },
  { value: "90", label: "Ends in 90 days" },
  { value: "180", label: "Ends in 180 days" },
  { value: "365", label: "Ends in 1 year" },
  { value: "custom", label: "Ends on a specific date…" },
];

/** Highest watch-topic override the API accepts (mirrors the server ceiling). */
const WATCH_LIMIT_MAX = 200;

const TIER_LABEL: Record<AdminTier, string> = {
  free: "Free",
  spore: "Spore",
  lab: "Lab",
  canopy: "Canopy",
};

function tierTone(tier: AdminTier): PillTone {
  if (tier === "canopy") return "accent";
  if (tier === "free") return "neutral";
  return "primary";
}

function statusTone(status: AdminSubscriptionStatus | AdminOrgStatus): PillTone {
  if (status === "active") return "primary";
  if (status === "past_due") return "review";
  if (status === "inactive") return "dashed";
  return "clay";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function usd(cents: number): string {
  return (cents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

/** An `<input type="date">` value for a datetime the API returned, or "". */
function dateInputValue(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

type Context = "users" | "labs";

/**
 * The admin dashboard (Research → Personal Workspace → Admin). Two management
 * contexts behind one switch: **Users** (a person's personal plan + watch quota) and
 * **Labs** (a lab's subscription — tier, status, how it ends, whether it is
 * complimentary, whether Mylo is included). The backend is the real gate (every
 * endpoint requires staff/superuser); this client guard just avoids rendering the
 * surface for others.
 */
export function AdminSection() {
  const { user } = usePortal();
  const [context, setContext] = React.useState<Context>("users");
  const { data: entitlements } = useEntitlements();
  const billingOff = entitlements?.billing_mode === "off";

  if (!isPlatformAdmin(user)) {
    return (
      <div>
        <SectionHeader eyebrow="Platform" title="Admin" />
        <EmptyState
          icon={<ShieldIcon size={26} />}
          badge="Restricted"
          title="Administrator access only"
          description="This area is limited to platform staff. If you reached it by mistake, head back to your overview."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        title="Admin"
        subtitle={
          context === "users"
            ? "Manage users, their subscription plan and duration, and how many subjects Mylo watches for them."
            : "Manage each lab's subscription — tier, how the plan ends, and whether Mylo is part of it."
        }
      />

      {billingOff ? (
        <p
          role="note"
          className="mb-4 rounded-xl border border-dashed border-border bg-[var(--surface-alt)] px-4 py-3 text-[12.5px] leading-relaxed text-[var(--text-secondary)]"
        >
          Billing is off on this instance (<code>billing.mode</code> in{" "}
          <code>mycelium.toml</code>), so plans and tiers below decide nothing:
          limits come from the instance configuration. A person&apos;s watch
          limit set here still applies.
        </p>
      ) : null}

      <ContextSwitch value={context} onChange={setContext} />

      {context === "users" ? <UsersPanel /> : <LabsPanel />}
    </div>
  );
}

/** The Users ⇄ Labs selector — a labelled radio group, not two lookalike buttons. */
function ContextSwitch({
  value,
  onChange,
}: {
  value: Context;
  onChange: (next: Context) => void;
}) {
  const options: { value: Context; label: string }[] = [
    { value: "users", label: "Users" },
    { value: "labs", label: "Labs" },
  ];
  return (
    <div
      role="radiogroup"
      aria-label="What to manage"
      className="mb-4 inline-flex gap-1 rounded-full border border-border bg-surface-alt p-1"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-full px-4 py-1.5 text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "bg-primary text-[#fffdf8]"
                : "text-[var(--text-secondary)] hover:bg-surface",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

// -- shared chrome -------------------------------------------------------------

/** Search box + result count, shared by both contexts. */
function SearchBar({
  value,
  onChange,
  total,
  noun,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  total: number;
  noun: [string, string];
  placeholder: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <label className="relative flex-1 min-w-[220px]">
        <span className="sr-only">{placeholder}</span>
        <input
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className={INPUT_CLASS}
        />
      </label>
      <p aria-live="polite" className="text-sm text-[var(--text-secondary)]">
        {total} {total === 1 ? noun[0] : noun[1]}
      </p>
    </div>
  );
}

function TablePager({
  page,
  showing,
  total,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: {
  page: number;
  showing: number;
  total: number;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (total === 0) return null;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-[var(--divider)] px-4 py-3 text-sm text-[var(--text-secondary)]">
      <span>
        Showing {showing} of {total} · page {page}
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" onClick={onPrev} disabled={!hasPrev}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" onClick={onNext} disabled={!hasNext}>
          Next
        </Button>
      </div>
    </div>
  );
}

/**
 * Loading / error / empty states shared by both tables; **null when there are rows**,
 * which is what lets a caller do `const state = tableState(...); if (state) return state`.
 *
 * Deliberately a plain function, not a component: as `<TableState … />` the caller's
 * truthiness check tests a React *element*, which is always truthy, so the guard fired
 * on every render and the table body was never reached — a silently blank table with no
 * error and no spinner. Lowercase name so the call site reads as a call.
 */
function tableState({
  loading,
  error,
  empty,
  errorText,
  emptyText,
}: {
  loading: boolean;
  error: boolean;
  empty: boolean;
  errorText: string;
  emptyText: string;
}): React.ReactNode | null {
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-12 animate-pulse rounded-lg bg-surface-alt" />
        ))}
      </div>
    );
  }
  if (error) {
    return <p className="px-5 py-10 text-center text-sm text-clay">{errorText}</p>;
  }
  if (empty) {
    return (
      <p className="px-5 py-10 text-center text-sm text-[var(--text-secondary)]">
        {emptyText}
      </p>
    );
  }
  return null;
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
      >
        {label}
      </label>
      {children}
      {hint ? (
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{hint}</p>
      ) : null}
    </div>
  );
}

/** The editor shell: a titled card with a Close control and load/error handling. */
function EditorCard({
  eyebrow,
  title,
  subtitle,
  loading,
  error,
  onClose,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  loading: boolean;
  error: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-[22px]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            {eyebrow}
          </p>
          <h2 className="truncate font-serif text-lg font-semibold text-[var(--text-primary)]">
            {title}
          </h2>
          {subtitle ? (
            <p className="truncate text-xs text-[var(--text-secondary)]">{subtitle}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-full px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-secondary)]"
        >
          Close
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded-lg bg-surface-alt" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-clay">Could not load this record.</p>
      ) : (
        children
      )}
    </Card>
  );
}

/** The two-column table + editor layout both contexts use. */
function ManagePanel({
  table,
  editor,
}: {
  table: React.ReactNode;
  editor: React.ReactNode;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
      <Card className="overflow-hidden">{table}</Card>
      <div>{editor}</div>
    </div>
  );
}

// ==============================================================================
// Users
// ==============================================================================

function UsersPanel() {
  const [rawQuery, setRawQuery] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);

  // Defer the query so typing stays responsive without firing a request per key.
  const query = React.useDeferredValue(rawQuery).trim();
  const { data, isLoading, isError, isPlaceholderData } = useAdminUsers({
    q: query || undefined,
    page,
  });

  const rows = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <>
      <SearchBar
        value={rawQuery}
        onChange={(value) => {
          setRawQuery(value);
          setPage(1);
        }}
        total={total}
        noun={["user", "users"]}
        placeholder="Search by name, username, or email…"
      />
      <ManagePanel
        table={
          <>
            <UsersTable
              rows={rows}
              loading={isLoading}
              error={isError}
              fetching={isPlaceholderData}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            <TablePager
              page={page}
              showing={rows.length}
              total={total}
              hasPrev={Boolean(data?.previous) && page > 1}
              hasNext={Boolean(data?.next)}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => p + 1)}
            />
          </>
        }
        editor={
          selectedId != null ? (
            <UserEditor
              key={selectedId}
              id={selectedId}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <EmptyState
              icon={<ShieldIcon size={24} />}
              title="Select a user"
              description="Choose a user from the list to change their subscription or watch limit."
              className="h-full"
            />
          )
        }
      />
    </>
  );
}

function UsersTable({
  rows,
  loading,
  error,
  fetching,
  selectedId,
  onSelect,
}: {
  rows: AdminUserRow[];
  loading: boolean;
  error: boolean;
  fetching: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const state = tableState({
    loading,
    error,
    empty: rows.length === 0,
    errorText: "Could not load the user list. Refresh to try again.",
    emptyText: "No users match your search.",
  });
  if (state) return state;

  return (
    <div
      className="overflow-x-auto"
      aria-busy={fetching}
      style={{ opacity: fetching ? 0.6 : 1 }}
    >
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--divider)] text-left text-[11px] uppercase tracking-[0.06em] text-[var(--text-secondary)]">
            <th scope="col" className="px-4 py-2.5 font-semibold">
              User
            </th>
            <th scope="col" className="px-3 py-2.5 font-semibold">
              Plan
            </th>
            <th scope="col" className="px-3 py-2.5 font-semibold">
              Watch
            </th>
            <th scope="col" className="px-4 py-2.5 font-semibold text-right">
              <span className="sr-only">Manage</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <UserRow
              key={row.id}
              row={row}
              selected={row.id === selectedId}
              onSelect={() => onSelect(row.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UserRow({
  row,
  selected,
  onSelect,
}: {
  row: AdminUserRow;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <tr
      className={
        selected
          ? "border-b border-[var(--divider)] bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]"
          : "border-b border-[var(--divider)] hover:bg-surface-alt"
      }
    >
      <td className="px-4 py-3 align-top">
        <div className="font-semibold text-[var(--text-primary)]">
          {row.name}
          {row.is_superuser ? (
            <Pill tone="accent" className="ml-2 align-middle text-[10px]">
              Superuser
            </Pill>
          ) : row.is_staff ? (
            <Pill tone="primary" className="ml-2 align-middle text-[10px]">
              Staff
            </Pill>
          ) : null}
        </div>
        <div className="text-xs text-[var(--text-secondary)]">
          @{row.username}
          {row.email ? ` · ${row.email}` : ""}
        </div>
      </td>
      <td className="px-3 py-3 align-top">
        <div className="flex flex-wrap items-center gap-1">
          <Pill tone={tierTone(row.effective_tier)}>
            {TIER_LABEL[row.effective_tier]}
          </Pill>
          {row.subscription && row.subscription.status !== "active" ? (
            <Pill tone={statusTone(row.subscription.status)} className="text-[10px]">
              {row.subscription.status.replace("_", " ")}
            </Pill>
          ) : null}
        </div>
        {row.subscription?.expires_at ? (
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
            until {formatDate(row.subscription.expires_at)}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-3 align-top text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">
          {row.watch_topics_used}
        </span>
        {" / "}
        {row.watch_topic_cap}
        {row.watch_topic_limit != null ? (
          <div className="text-[11px] text-brand-secondary">custom limit</div>
        ) : null}
      </td>
      <td className="px-4 py-3 align-top text-right">
        <Button
          variant={selected ? "default" : "secondary"}
          size="sm"
          onClick={onSelect}
          aria-pressed={selected}
        >
          Manage
        </Button>
      </td>
    </tr>
  );
}

function UserEditor({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: detail, isLoading, isError } = useAdminUser(id);

  return (
    <EditorCard
      eyebrow="Manage user"
      title={detail?.name ?? "Loading…"}
      subtitle={
        detail
          ? `@${detail.username}${detail.email ? ` · ${detail.email}` : ""}`
          : undefined
      }
      loading={isLoading}
      error={isError || !detail}
      onClose={onClose}
    >
      {detail ? <UserEditorForm detail={detail} /> : null}
    </EditorCard>
  );
}

function UserEditorForm({ detail }: { detail: AdminUserDetail }) {
  const update = useUpdateAdminUser();

  // A stored plan can only be a personal tier now, but historical rows may hold a
  // team tier; fall back to Free rather than offering a value the picker can't show.
  const stored = detail.subscription?.tier;
  const currentTier: AdminPersonalTier =
    stored === "spore" || stored === "free" ? stored : "free";
  const currentStatus = detail.subscription?.status ?? "active";
  const hasOverride = detail.watch_topic_limit != null;

  const [tier, setTier] = React.useState<AdminPersonalTier>(currentTier);
  const [status, setStatus] = React.useState<AdminSubscriptionStatus>(currentStatus);
  const [duration, setDuration] = React.useState("");
  const [customLimit, setCustomLimit] = React.useState(hasOverride);
  const [limitValue, setLimitValue] = React.useState(
    hasOverride ? String(detail.watch_topic_limit) : "",
  );
  const [saved, setSaved] = React.useState(false);

  const buildPatch = (): AdminUserUpdate => {
    const patch: AdminUserUpdate = {
      tier,
      subscription_status: status,
    };
    if (duration === "none") {
      patch.duration_days = null;
    } else if (duration !== "") {
      patch.duration_days = Number(duration);
    }
    // Watch limit: send the resolved intent (custom number, or null to clear).
    patch.watch_topic_limit = customLimit ? Number(limitValue || "0") : null;
    return patch;
  };

  const limitInvalid =
    customLimit &&
    (limitValue === "" ||
      Number(limitValue) < 0 ||
      Number(limitValue) > WATCH_LIMIT_MAX ||
      !Number.isInteger(Number(limitValue)));

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (limitInvalid) return;
    setSaved(false);
    update.mutate(
      { id: detail.id, patch: buildPatch() },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <UserMeta detail={detail} />

      <Field
        label="Subscription tier"
        htmlFor="admin-tier"
        hint="Mycelium Lab and Canopy are team plans — grant them on the Labs tab, where the roster sets the price."
      >
        <select
          id="admin-tier"
          className={INPUT_CLASS}
          value={tier}
          onChange={(event) => setTier(event.target.value as AdminPersonalTier)}
        >
          {PERSONAL_TIERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="Duration"
        htmlFor="admin-duration"
        hint={
          detail.subscription?.expires_at
            ? `Currently expires ${formatDate(detail.subscription.expires_at)}.`
            : "Currently open-ended (no expiry)."
        }
      >
        <select
          id="admin-duration"
          className={INPUT_CLASS}
          value={duration}
          onChange={(event) => setDuration(event.target.value)}
        >
          {DURATIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Subscription status" htmlFor="admin-status">
        <select
          id="admin-status"
          className={INPUT_CLASS}
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as AdminSubscriptionStatus)
          }
        >
          {STATUSES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <fieldset>
        <legend className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          Watch limit (subjects Mylo monitors)
        </legend>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={customLimit}
            onChange={(event) => setCustomLimit(event.target.checked)}
            className="h-4 w-4 rounded border-border text-primary focus-visible:ring-2 focus-visible:ring-ring"
          />
          Set a custom limit (overrides their plan)
        </label>
        {customLimit ? (
          <div className="mt-2">
            <input
              type="number"
              min={0}
              max={WATCH_LIMIT_MAX}
              step={1}
              value={limitValue}
              onChange={(event) => setLimitValue(event.target.value)}
              aria-invalid={limitInvalid}
              className={`${INPUT_CLASS} w-28`}
            />
            <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
              0–{WATCH_LIMIT_MAX} subjects. Current cap: {detail.watch_topic_cap}.
            </p>
          </div>
        ) : (
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            Uses their plan&apos;s cap.
          </p>
        )}
      </fieldset>

      <SaveRow
        pending={update.isPending}
        disabled={limitInvalid}
        error={update.isError ? (update.error as Error)?.message : null}
        saved={saved && !update.isPending}
      />
    </form>
  );
}

function UserMeta({ detail }: { detail: AdminUserDetail }) {
  return (
    <div className="rounded-lg border border-border bg-surface-alt px-3.5 py-3 text-xs text-[var(--text-secondary)]">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Joined <strong className="font-semibold">{formatDate(detail.date_joined)}</strong>
        </span>
        <span>
          Effective tier{" "}
          <strong className="font-semibold">{TIER_LABEL[detail.effective_tier]}</strong>
        </span>
        <span>
          Watch used{" "}
          <strong className="font-semibold">
            {detail.watch_topics_used}/{detail.watch_topic_cap}
          </strong>
        </span>
      </div>
      {detail.lab_memberships.length > 0 ? (
        <div className="mt-1.5">
          Labs: {detail.lab_memberships.map((m) => m.name).join(", ")}
        </div>
      ) : null}
    </div>
  );
}

// ==============================================================================
// Labs
// ==============================================================================

function LabsPanel() {
  const [rawQuery, setRawQuery] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [selectedSlug, setSelectedSlug] = React.useState<string | null>(null);

  const query = React.useDeferredValue(rawQuery).trim();
  const { data, isLoading, isError, isPlaceholderData } = useAdminLabs({
    q: query || undefined,
    page,
  });

  const rows = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <>
      <SearchBar
        value={rawQuery}
        onChange={(value) => {
          setRawQuery(value);
          setPage(1);
        }}
        total={total}
        noun={["lab", "labs"]}
        placeholder="Search by lab name, slug, or department…"
      />
      <ManagePanel
        table={
          <>
            <LabsTable
              rows={rows}
              loading={isLoading}
              error={isError}
              fetching={isPlaceholderData}
              selectedSlug={selectedSlug}
              onSelect={setSelectedSlug}
            />
            <TablePager
              page={page}
              showing={rows.length}
              total={total}
              hasPrev={Boolean(data?.previous) && page > 1}
              hasNext={Boolean(data?.next)}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => p + 1)}
            />
          </>
        }
        editor={
          selectedSlug != null ? (
            <LabEditor
              key={selectedSlug}
              slug={selectedSlug}
              onClose={() => setSelectedSlug(null)}
            />
          ) : (
            <EmptyState
              icon={<ShieldIcon size={24} />}
              title="Select a lab"
              description="Choose a lab from the list to change its plan, how it ends, or whether Mylo is included."
              className="h-full"
            />
          )
        }
      />
    </>
  );
}

function LabsTable({
  rows,
  loading,
  error,
  fetching,
  selectedSlug,
  onSelect,
}: {
  rows: AdminLabRow[];
  loading: boolean;
  error: boolean;
  fetching: boolean;
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}) {
  const state = tableState({
    loading,
    error,
    empty: rows.length === 0,
    errorText: "Could not load the lab list. Refresh to try again.",
    emptyText: "No labs match your search.",
  });
  if (state) return state;

  return (
    <div
      className="overflow-x-auto"
      aria-busy={fetching}
      style={{ opacity: fetching ? 0.6 : 1 }}
    >
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--divider)] text-left text-[11px] uppercase tracking-[0.06em] text-[var(--text-secondary)]">
            <th scope="col" className="px-4 py-2.5 font-semibold">
              Lab
            </th>
            <th scope="col" className="px-3 py-2.5 font-semibold">
              Plan
            </th>
            <th scope="col" className="px-3 py-2.5 font-semibold">
              Mylo
            </th>
            <th scope="col" className="px-4 py-2.5 font-semibold text-right">
              <span className="sr-only">Manage</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <LabRow
              key={row.slug}
              row={row}
              selected={row.slug === selectedSlug}
              onSelect={() => onSelect(row.slug)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LabRow({
  row,
  selected,
  onSelect,
}: {
  row: AdminLabRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const sub = row.subscription;
  return (
    <tr
      className={
        selected
          ? "border-b border-[var(--divider)] bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]"
          : "border-b border-[var(--divider)] hover:bg-surface-alt"
      }
    >
      <td className="px-4 py-3 align-top">
        <div className="font-semibold text-[var(--text-primary)]">{row.name}</div>
        <div className="text-xs text-[var(--text-secondary)]">
          {row.member_count} {row.member_count === 1 ? "member" : "members"}
          {row.department ? ` · ${row.department.name}` : ""}
        </div>
      </td>
      <td className="px-3 py-3 align-top">
        {sub ? (
          <>
            <div className="flex flex-wrap items-center gap-1">
              <Pill tone={tierTone(sub.tier)}>{TIER_LABEL[sub.tier]}</Pill>
              <Pill tone={statusTone(sub.status)} className="text-[10px]">
                {sub.status.replace("_", " ")}
              </Pill>
              {sub.is_comped ? (
                <Pill tone="accent" className="text-[10px]">
                  Free
                </Pill>
              ) : null}
            </div>
            <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
              {sub.is_comped
                ? "No end date"
                : sub.expires_at
                  ? `until ${formatDate(sub.expires_at)}`
                  : `${usd(sub.recurring_monthly_cents)} / mo`}
            </div>
          </>
        ) : (
          <span className="text-xs text-[var(--text-secondary)]">No plan</span>
        )}
      </td>
      <td className="px-3 py-3 align-top">
        <Pill tone={sub?.mylo_included ? "primary" : "dashed"}>
          {sub?.mylo_included ? "Included" : "No"}
        </Pill>
      </td>
      <td className="px-4 py-3 align-top text-right">
        <Button
          variant={selected ? "default" : "secondary"}
          size="sm"
          onClick={onSelect}
          aria-pressed={selected}
        >
          Manage
        </Button>
      </td>
    </tr>
  );
}

function LabEditor({ slug, onClose }: { slug: string; onClose: () => void }) {
  const { data: detail, isLoading, isError } = useAdminLab(slug);

  return (
    <EditorCard
      eyebrow="Manage lab"
      title={detail?.name ?? "Loading…"}
      subtitle={detail ? `/${detail.slug}` : undefined}
      loading={isLoading}
      error={isError || !detail}
      onClose={onClose}
    >
      {detail ? <LabEditorForm detail={detail} /> : null}
    </EditorCard>
  );
}

/** "" for no override, else the number as typed. */
function limitInput(value: number | null): string {
  return value === null ? "" : String(value);
}

/** A typed override: blank clears it (null); otherwise a whole number ≥ 0. */
function parseLimit(text: string): number | null | undefined {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

function capLabel(cap: number | null): string {
  return cap === null ? "unlimited" : String(cap);
}

function LabEditorForm({ detail }: { detail: AdminLabDetail }) {
  const update = useUpdateAdminLab();
  const sub = detail.subscription;
  // With billing off the plan fields decide nothing, so only the limits show.
  const { data: entitlements } = useEntitlements();
  const billingOff = entitlements?.billing_mode === "off";
  const [projectLimit, setProjectLimit] = React.useState(
    limitInput(detail.limits.project_limit),
  );
  const [memberLimit, setMemberLimit] = React.useState(
    limitInput(detail.limits.member_limit),
  );
  const parsedProject = parseLimit(projectLimit);
  const parsedMember = parseLimit(memberLimit);
  const limitsInvalid = parsedProject === undefined || parsedMember === undefined;

  const [tier, setTier] = React.useState<AdminLabTier>(
    sub?.tier === "canopy" ? "canopy" : "lab",
  );
  const [status, setStatus] = React.useState<AdminOrgStatus>(sub?.status ?? "inactive");
  const [ending, setEnding] = React.useState("");
  const [endDate, setEndDate] = React.useState(dateInputValue(sub?.expires_at ?? null));
  const [mylo, setMylo] = React.useState(Boolean(sub?.mylo_included));
  const [saved, setSaved] = React.useState(false);

  const customDateMissing = ending === "custom" && endDate === "";

  const buildPatch = (): AdminLabUpdate => {
    const limits: AdminLabUpdate = {
      project_limit: parsedProject ?? null,
      member_limit: parsedMember ?? null,
    };
    if (billingOff) return limits;
    const patch: AdminLabUpdate = { ...limits, tier, status, mylo_included: mylo };
    if (ending === "never") {
      // The free case: no end date, and comped so the plan page strikes the price.
      patch.duration_days = null;
      patch.is_comped = true;
    } else if (ending === "custom") {
      patch.expires_at = new Date(`${endDate}T23:59:59`).toISOString();
      patch.is_comped = false;
    } else if (ending !== "") {
      patch.duration_days = Number(ending);
      patch.is_comped = false;
    }
    return patch;
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (customDateMissing || limitsInvalid) return;
    setSaved(false);
    update.mutate(
      { slug: detail.slug, patch: buildPatch() },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <LabMeta detail={detail} />

      <fieldset className="space-y-3">
        <legend className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          Limits for this lab
        </legend>
        <Field
          label="Active projects"
          htmlFor="admin-lab-project-limit"
          hint={`Blank uses the instance value. In effect now: ${capLabel(detail.limits.project_cap)}.`}
        >
          <input
            id="admin-lab-project-limit"
            type="number"
            min={0}
            inputMode="numeric"
            className={INPUT_CLASS}
            value={projectLimit}
            placeholder="Instance default"
            aria-invalid={parsedProject === undefined}
            onChange={(event) => setProjectLimit(event.target.value)}
          />
        </Field>
        <Field
          label="Members"
          htmlFor="admin-lab-member-limit"
          hint={`Blank uses the instance value. In effect now: ${capLabel(detail.limits.member_cap)}; ${detail.member_count} today. Lowering it never removes anyone.`}
        >
          <input
            id="admin-lab-member-limit"
            type="number"
            min={0}
            inputMode="numeric"
            className={INPUT_CLASS}
            value={memberLimit}
            placeholder="Instance default"
            aria-invalid={parsedMember === undefined}
            onChange={(event) => setMemberLimit(event.target.value)}
          />
        </Field>
      </fieldset>

      {billingOff ? null : (
        <>
      <Field
        label="Plan tier"
        htmlFor="admin-lab-tier"
        hint={`Priced per member — ${detail.member_count} in this lab today.`}
      >
        <select
          id="admin-lab-tier"
          className={INPUT_CLASS}
          value={tier}
          onChange={(event) => setTier(event.target.value as AdminLabTier)}
        >
          {LAB_TIERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="Plan status"
        htmlFor="admin-lab-status"
        hint="Setting this Active opens the billing period and seats every current member."
      >
        <select
          id="admin-lab-status"
          className={INPUT_CLASS}
          value={status}
          onChange={(event) => setStatus(event.target.value as AdminOrgStatus)}
        >
          {ORG_STATUSES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="How the plan ends"
        htmlFor="admin-lab-ending"
        hint={
          sub?.is_comped
            ? "Currently complimentary — no end date, nothing billed."
            : sub?.expires_at
              ? `Currently ends ${formatDate(sub.expires_at)}, then reverts to Free.`
              : "Currently open-ended. Nothing is ever deleted when a plan ends — the lab just reverts to Free."
        }
      >
        <select
          id="admin-lab-ending"
          className={INPUT_CLASS}
          value={ending}
          onChange={(event) => setEnding(event.target.value)}
        >
          {LAB_ENDINGS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      {ending === "custom" ? (
        <Field label="End date" htmlFor="admin-lab-end-date">
          <input
            id="admin-lab-end-date"
            type="date"
            className={INPUT_CLASS}
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            aria-invalid={customDateMissing}
            required
          />
        </Field>
      ) : null}

      {ending === "never" ? (
        <p className="rounded-lg border border-border bg-surface-alt px-3.5 py-2.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">
          A plan with no end date is treated as free: the lab keeps the full{" "}
          {TIER_LABEL[tier]} entitlement and its plan page shows the price struck
          through.
        </p>
      ) : null}

      <fieldset>
        <legend className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          Mylo on Discord
        </legend>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={mylo}
            onChange={(event) => setMylo(event.target.checked)}
            className="h-4 w-4 rounded border-border text-primary focus-visible:ring-2 focus-visible:ring-ring"
          />
          Include Mylo in this plan
        </label>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          Without it the lab can&apos;t add Mylo to a Discord server or activate one.
        </p>
      </fieldset>
        </>
      )}

      <SaveRow
        pending={update.isPending}
        disabled={customDateMissing || limitsInvalid}
        error={update.isError ? (update.error as Error)?.message : null}
        saved={saved && !update.isPending}
      />
    </form>
  );
}

function LabMeta({ detail }: { detail: AdminLabDetail }) {
  const sub = detail.subscription;
  const leads = detail.leads.filter((m) => m.is_lead);
  return (
    <div className="rounded-lg border border-border bg-surface-alt px-3.5 py-3 text-xs text-[var(--text-secondary)]">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Created <strong className="font-semibold">{formatDate(detail.created_at)}</strong>
        </span>
        <span>
          Members <strong className="font-semibold">{detail.member_count}</strong>
        </span>
        <span>
          Seats <strong className="font-semibold">{sub?.seat_count ?? 0}</strong>
        </span>
        {sub ? (
          <span>
            Billed{" "}
            <strong className="font-semibold">
              {sub.is_comped ? "Free" : `${usd(sub.recurring_monthly_cents)} / mo`}
            </strong>
          </span>
        ) : null}
      </div>
      {leads.length > 0 ? (
        <div className="mt-1.5">PI: {leads.map((m) => m.name).join(", ")}</div>
      ) : null}
      {detail.department ? (
        <div className="mt-1.5">
          Department: {detail.department.name}
          {detail.department.included_in_plan ? " · in the department plan" : ""}
        </div>
      ) : null}
    </div>
  );
}

// -- shared save footer --------------------------------------------------------

function SaveRow({
  pending,
  disabled,
  error,
  saved,
}: {
  pending: boolean;
  disabled: boolean;
  error: string | null;
  saved: boolean;
}) {
  return (
    <>
      {error ? (
        <p className="text-sm text-clay" role="alert">
          {error || "Could not save the changes."}
        </p>
      ) : null}
      {saved ? <p className="text-sm text-primary">Changes saved.</p> : null}
      <Button type="submit" disabled={pending || disabled}>
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </>
  );
}
