"use client";

import * as React from "react";

import {
  AlertTriangleIcon,
  BellIcon,
  CalendarIcon,
  ClockIcon,
  DiscordIcon,
  EditIcon,
  LinkIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { ReminderEditor } from "@/components/portal/reminder-editor";
import { formatOffset } from "@/components/portal/reminder-offsets-field";
import { useReminderMutations, useReminders } from "@/lib/portal/hooks";
import type { Reminder } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<string, string> = {
  application: "Application",
  abstract: "Abstract",
  manuscript: "Manuscript",
  event: "Event",
  other: "Deadline",
};

const AREA_LABELS: Record<string, string> = {
  grant: "Grant",
  fellowship: "Fellowship",
  conference: "Conference",
  paper: "Paper",
};

/** "Mar 4, 2027" from a plain `YYYY-MM-DD` (parsed as local, never UTC-shifted). */
function formatDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Whole days from today to `iso`, or null when there is no date. */
function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const target = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

function countdown(iso: string | null): string {
  const days = daysUntil(iso);
  if (days === null) return "";
  if (days < 0) return "passed";
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

/**
 * When a reminder lands, in words. Day-granular by design — the tick runs once a
 * day — so a lab's configured local hour is named and a personal reminder says
 * only "with the daily run" rather than implying an hour nothing honours.
 */
function sendTimeLabel(reminder: Reminder): string {
  if (reminder.send_hour_local === null) return "with the daily run";
  const hour = reminder.send_hour_local;
  const suffix = hour < 12 ? "am" : "pm";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `around ${twelve}${suffix} ${reminder.timezone}`;
}

/** Reminders split into the three lists the page shows, in that order. */
function groupReminders(items: Reminder[]) {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming: Reminder[] = [];
  const snoozed: Reminder[] = [];
  const finished: Reminder[] = [];
  for (const r of items) {
    if (r.state !== "active") finished.push(r);
    else if (r.snoozed_until && r.snoozed_until > today) snoozed.push(r);
    else upcoming.push(r);
  }
  return { upcoming, snoozed, finished };
}

/**
 * The reminders page: every deadline reminder that has been set, when each one
 * will actually reach you, and the controls to change it.
 *
 * Scope-aware like Saves — the personal workspace lists your own reminders, a lab
 * workspace lists that lab's. `can_manage` comes from the server (owner, or lab
 * PI/admin), so a plain lab member sees the reminders their lab has set without
 * being offered buttons the API would refuse.
 */
export function RemindersSection() {
  const { currentLab } = usePortal();
  const { data, isLoading, isError } = useReminders();
  const [editing, setEditing] = React.useState<Reminder | null>(null);

  const items = React.useMemo(() => {
    const all = data?.items ?? [];
    return currentLab
      ? all.filter((r) => r.lab_slug === currentLab.slug)
      : all.filter((r) => r.scope === "user");
  }, [data, currentLab]);

  const { upcoming, snoozed, finished } = React.useMemo(
    () => groupReminders(items),
    [items],
  );

  const title = currentLab ? `${currentLab.name} reminders` : "Reminders";
  const subtitle = isLoading
    ? "Loading your reminders…"
    : items.length === 0
      ? "Deadline reminders you set from a grant, fellowship, or conference collect here."
      : `${upcoming.length} active · ${snoozed.length} snoozed · ${finished.length} finished or cancelled.`;

  // The live row for the open editor, so an edit re-renders against fresh data
  // instead of the snapshot captured when the modal opened.
  const editingRow = editing
    ? (items.find((r) => r.id === editing.id) ?? null)
    : null;

  return (
    <div>
      <SectionHeader eyebrow="Workspace" title={title} subtitle={subtitle} />

      {isLoading ? (
        <div className="space-y-3.5">
          <ReminderSkeleton />
          <ReminderSkeleton />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<BellIcon size={26} className="text-accent" />}
          title="Couldn't load your reminders"
          description="Something went wrong fetching them. Please try again in a moment."
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<BellIcon size={26} className="text-accent" />}
          title={
            currentLab ? "No reminders for this lab yet" : "No reminders set yet"
          }
          description={
            currentLab
              ? "Set one from a saved grant, fellowship, or conference and it will post to the lab's Discord channel — and show up here."
              : "Save a grant, fellowship, or conference with a deadline, then use “Remind me”. Every reminder you set lands on this page."
          }
        />
      ) : (
        <div className="space-y-8">
          <Group
            title="Upcoming"
            hint="Waiting on their next lead time."
            items={upcoming}
            onEdit={setEditing}
          />
          <Group
            title="Snoozed"
            hint="Paused until the date shown, then they resume."
            items={snoozed}
            onEdit={setEditing}
          />
          <Group
            title="Finished & cancelled"
            hint="Kept so you can see what was set — and restart it if the deadline is still ahead."
            items={finished}
            onEdit={setEditing}
          />
        </div>
      )}

      {editingRow ? (
        <ReminderEditor
          reminder={editingRow}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}

function Group({
  title,
  hint,
  items,
  onEdit,
}: {
  title: string;
  hint: string;
  items: Reminder[];
  onEdit: (reminder: Reminder) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <div className="mb-3">
        <h2 className="font-serif text-[17px] font-semibold text-[var(--text-primary)]">
          {title}{" "}
          <span className="font-sans text-[13px] font-medium text-[var(--text-secondary)]">
            ({items.length})
          </span>
        </h2>
        <p className="mt-0.5 text-[12.5px] text-[var(--text-secondary)]">{hint}</p>
      </div>
      <div className="space-y-3.5">
        {items.map((reminder, index) => (
          <div
            key={reminder.id}
            className="portal-fade-up"
            style={{ animationDelay: `${index * 45}ms` }}
          >
            <ReminderRow reminder={reminder} onEdit={onEdit} />
          </div>
        ))}
      </div>
    </section>
  );
}

/** One reminder: what it's for, when it fires, and what you can do to it. */
function ReminderRow({
  reminder,
  onEdit,
}: {
  reminder: Reminder;
  onEdit: (reminder: Reminder) => void;
}) {
  const { update, remove } = useReminderMutations();
  const [error, setError] = React.useState<string | null>(null);
  const pending = update.isPending || remove.isPending;

  const kind = KIND_LABELS[reminder.deadline_kind] ?? "Deadline";
  const area = AREA_LABELS[reminder.area] ?? reminder.area;
  const dueDays = daysUntil(reminder.due_date);
  const deadlinePassed = dueDays !== null && dueDays < 0;

  const act = (input: Parameters<typeof update.mutate>[0]["input"]) => {
    setError(null);
    update.mutate(
      { id: reminder.id, input },
      { onError: (e) => setError((e as Error).message) },
    );
  };

  const snoozeBy = (days: number) => {
    const until = new Date();
    until.setHours(0, 0, 0, 0);
    until.setDate(until.getDate() + days);
    act({ snoozed_until: until.toISOString().slice(0, 10) });
  };

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <Badge>{area}</Badge>
            <Badge>{kind}</Badge>
            <ScopeBadge reminder={reminder} />
            <StateBadge reminder={reminder} />
          </div>
          {reminder.url ? (
            <a
              href={reminder.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-start gap-1.5 text-[15px] font-semibold leading-snug text-[var(--text-primary)] hover:text-primary hover:underline"
            >
              {reminder.title}
              <LinkIcon size={13} className="mt-1 shrink-0 opacity-60" />
            </a>
          ) : (
            <p className="text-[15px] font-semibold leading-snug text-[var(--text-primary)]">
              {reminder.title}
            </p>
          )}

          <dl className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5 text-[12.5px] text-[var(--text-secondary)]">
            <Fact icon={<CalendarIcon size={13} />} label={`${kind} deadline`}>
              {reminder.due_date ? (
                <>
                  {formatDate(reminder.due_date)}
                  <span className="ml-1 opacity-70">
                    ({countdown(reminder.due_date)})
                  </span>
                </>
              ) : (
                "no date on record"
              )}
            </Fact>
            <Fact icon={<ClockIcon size={13} />} label="Next reminder">
              {reminder.snoozed_until &&
              reminder.snoozed_until > new Date().toISOString().slice(0, 10) ? (
                <>snoozed until {formatDate(reminder.snoozed_until)}</>
              ) : reminder.next_fire_date ? (
                <>
                  {formatDate(reminder.next_fire_date)} ·{" "}
                  {sendTimeLabel(reminder)}
                </>
              ) : reminder.state === "active" ? (
                "all lead times have passed"
              ) : (
                "not scheduled"
              )}
            </Fact>
          </dl>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {reminder.offsets.map((o) => {
              const fired =
                o.fire_date !== null &&
                (daysUntil(o.fire_date) ?? 0) < 0 &&
                reminder.state === "active";
              return (
                <span
                  key={`${o.amount}-${o.unit}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[12px] font-semibold",
                    fired
                      ? "bg-surface text-[var(--text-secondary)] line-through decoration-1"
                      : "bg-surface-alt text-[var(--text-secondary)]",
                  )}
                  title={
                    fired
                      ? "This lead time has already gone by."
                      : "Still to come."
                  }
                >
                  {formatOffset(o)} before
                  {o.fire_date ? (
                    <span className="font-normal opacity-75">
                      {formatDate(o.fire_date)}
                    </span>
                  ) : null}
                </span>
              );
            })}
          </div>

          {reminder.mentions.length > 0 ? (
            <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-[var(--text-secondary)]">
              <DiscordIcon size={13} />
              Pings {reminder.mentions.map((m) => m.name).join(", ")}
              {reminder.has_unlinked_targets ? (
                <span className="inline-flex items-center gap-1 text-clay">
                  <AlertTriangleIcon size={12} />
                  someone hasn&apos;t linked Discord
                </span>
              ) : null}
            </p>
          ) : null}

          {reminder.content_id === null ? (
            <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-[var(--text-secondary)]">
              <AlertTriangleIcon size={12} className="text-accent" />
              The original listing is no longer in Mycelium; this reminder runs on
              the details saved when you set it.
            </p>
          ) : null}
        </div>

        {reminder.can_manage ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {reminder.state === "active" ? (
              <>
                <RowButton onClick={() => onEdit(reminder)} disabled={pending}>
                  <EditIcon size={13} />
                  Edit
                </RowButton>
                {reminder.snoozed_until ? (
                  <RowButton
                    onClick={() => act({ snoozed_until: null })}
                    disabled={pending}
                  >
                    Un-snooze
                  </RowButton>
                ) : (
                  <>
                    <RowButton onClick={() => snoozeBy(1)} disabled={pending}>
                      Snooze 1d
                    </RowButton>
                    <RowButton onClick={() => snoozeBy(7)} disabled={pending}>
                      Snooze 1w
                    </RowButton>
                  </>
                )}
                <RowButton
                  onClick={() => act({ state: "cancelled" })}
                  disabled={pending}
                  tone="danger"
                >
                  Cancel
                </RowButton>
              </>
            ) : (
              <>
                {!deadlinePassed && reminder.due_date ? (
                  <RowButton
                    onClick={() => act({ state: "active" })}
                    disabled={pending}
                  >
                    Restart
                  </RowButton>
                ) : null}
                <RowButton
                  onClick={() => {
                    setError(null);
                    remove.mutate(
                      { id: reminder.id, purge: true },
                      { onError: (e) => setError((e as Error).message) },
                    );
                  }}
                  disabled={pending}
                  tone="danger"
                >
                  Delete
                </RowButton>
              </>
            )}
          </div>
        ) : (
          <p className="text-[12px] text-[var(--text-secondary)]">
            Set by a lab manager
          </p>
        )}
      </div>

      {error ? (
        <p className="mt-2.5 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}

function Fact({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span aria-hidden="true" className="text-[var(--text-secondary)] opacity-70">
        {icon}
      </span>
      <dt className="sr-only">{label}</dt>
      <dd>
        <span className="font-semibold text-[var(--text-primary)]">{label}:</span>{" "}
        {children}
      </dd>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-surface-alt px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
      {children}
    </span>
  );
}

function ScopeBadge({ reminder }: { reminder: Reminder }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-alt px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
      <DiscordIcon size={11} />
      {reminder.scope === "lab" ? (reminder.lab_name ?? "Lab channel") : "Just me"}
    </span>
  );
}

/** The row's state, in words — never colour alone. */
function StateBadge({ reminder }: { reminder: Reminder }) {
  const label =
    reminder.state === "cancelled"
      ? "Cancelled"
      : reminder.state === "fired_out"
        ? "Deadline passed"
        : reminder.state === "stale"
          ? "Deadline withdrawn"
          : reminder.snoozed_until &&
              reminder.snoozed_until > new Date().toISOString().slice(0, 10)
            ? "Snoozed"
            : null;
  if (!label) return null;
  return (
    <span className="rounded-full border border-dashed border-border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
      {label}
    </span>
  );
}

function RowButton({
  onClick,
  disabled,
  tone,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  tone?: "danger";
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        tone === "danger"
          ? "border-border bg-surface text-clay hover:bg-surface-alt"
          : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]",
      )}
    >
      {children}
    </button>
  );
}

function ReminderSkeleton() {
  return (
    <Card className="p-4">
      <div className="space-y-2.5">
        <div className="h-3 w-28 rounded-full bg-surface-alt" />
        <div className="h-4 w-2/3 rounded-full bg-surface-alt" />
        <div className="h-3 w-1/2 rounded-full bg-surface-alt" />
      </div>
    </Card>
  );
}
