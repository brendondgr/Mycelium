"use client";

import * as React from "react";

import { ShieldIcon } from "@/components/portal/icons";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill, type PillTone } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { Button } from "@/components/ui/button";
import { useAdminUser, useAdminUsers, useUpdateAdminUser } from "@/lib/portal/hooks";
import type {
  AdminSubscriptionStatus,
  AdminTier,
  AdminUserDetail,
  AdminUserRow,
  AdminUserUpdate,
} from "@/lib/portal/types";

const INPUT_CLASS =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const TIERS: { value: AdminTier; label: string }[] = [
  { value: "free", label: "Free" },
  { value: "spore", label: "Spore" },
  { value: "lab", label: "Mycelium Lab" },
  { value: "canopy", label: "Canopy" },
];

const STATUSES: { value: AdminSubscriptionStatus; label: string }[] = [
  { value: "active", label: "Active" },
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

/** Highest watch-topic override the API accepts (mirrors the server ceiling). */
const WATCH_LIMIT_MAX = 50;

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

function statusTone(status: AdminSubscriptionStatus): PillTone {
  if (status === "active") return "primary";
  if (status === "past_due") return "review";
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

/**
 * The admin dashboard (Research → Personal Workspace → Admin). Staff/superusers
 * page and search every user, then set a user's subscription tier + duration and
 * their watch-topic quota. The backend is the real gate (every endpoint requires
 * staff/superuser); this client guard just avoids rendering the surface for others.
 */
export function AdminSection() {
  const { user } = usePortal();
  const [rawQuery, setRawQuery] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);

  // Defer the query so typing stays responsive without firing a request per key.
  const query = React.useDeferredValue(rawQuery).trim();
  const { data, isLoading, isError, isPlaceholderData } = useAdminUsers({
    q: query || undefined,
    page,
  });

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

  const rows = data?.results ?? [];
  const total = data?.count ?? 0;
  const hasPrev = Boolean(data?.previous) && page > 1;
  const hasNext = Boolean(data?.next);

  const onSearchChange = (value: string) => {
    setRawQuery(value);
    setPage(1);
  };

  return (
    <div>
      <SectionHeader
        title="Admin"
        subtitle="Manage users, their subscription plan and duration, and how many subjects Mylo watches for them."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="relative flex-1 min-w-[220px]">
          <span className="sr-only">Search users</span>
          <input
            type="search"
            value={rawQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search by name, username, or email…"
            className={INPUT_CLASS}
          />
        </label>
        <p aria-live="polite" className="text-sm text-[var(--text-secondary)]">
          {total} {total === 1 ? "user" : "users"}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Card className="overflow-hidden">
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
            hasPrev={hasPrev}
            hasNext={hasNext}
            onPrev={() => setPage((p) => Math.max(1, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </Card>

        <div>
          {selectedId != null ? (
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
          )}
        </div>
      </div>
    </div>
  );
}

// -- table ---------------------------------------------------------------------

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
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="h-12 animate-pulse rounded-lg bg-surface-alt"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="px-5 py-10 text-center text-sm text-clay">
        Could not load the user list. Refresh to try again.
      </p>
    );
  }

  if (rows.length === 0) {
    return (
      <p className="px-5 py-10 text-center text-sm text-[var(--text-secondary)]">
        No users match your search.
      </p>
    );
  }

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

// -- editor --------------------------------------------------------------------

function UserEditor({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: detail, isLoading, isError } = useAdminUser(id);

  return (
    <Card className="p-[22px]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Manage user
          </p>
          <h2 className="truncate font-serif text-lg font-semibold text-[var(--text-primary)]">
            {detail?.name ?? "Loading…"}
          </h2>
          {detail ? (
            <p className="truncate text-xs text-[var(--text-secondary)]">
              @{detail.username}
              {detail.email ? ` · ${detail.email}` : ""}
            </p>
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

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded-lg bg-surface-alt" />
          ))}
        </div>
      ) : isError || !detail ? (
        <p className="text-sm text-clay">Could not load this user.</p>
      ) : (
        <EditorForm detail={detail} />
      )}
    </Card>
  );
}

function EditorForm({ detail }: { detail: AdminUserDetail }) {
  const update = useUpdateAdminUser();

  const currentTier = detail.subscription?.tier ?? "free";
  const currentStatus = detail.subscription?.status ?? "active";
  const hasOverride = detail.watch_topic_limit != null;

  const [tier, setTier] = React.useState<AdminTier>(currentTier);
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
      <ReadOnlyMeta detail={detail} />

      <Field label="Subscription tier" htmlFor="admin-tier">
        <select
          id="admin-tier"
          className={INPUT_CLASS}
          value={tier}
          onChange={(event) => setTier(event.target.value as AdminTier)}
        >
          {TIERS.map((option) => (
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

      {update.isError ? (
        <p className="text-sm text-clay">
          {(update.error as Error)?.message ?? "Could not save the changes."}
        </p>
      ) : null}
      {saved && !update.isPending ? (
        <p className="text-sm text-primary">Changes saved.</p>
      ) : null}

      <Button type="submit" disabled={update.isPending || limitInvalid}>
        {update.isPending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}

function ReadOnlyMeta({ detail }: { detail: AdminUserDetail }) {
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
          Labs:{" "}
          {detail.lab_memberships.map((m) => m.name).join(", ")}
        </div>
      ) : null}
    </div>
  );
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
