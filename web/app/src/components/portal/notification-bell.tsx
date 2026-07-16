"use client";

import * as React from "react";

import {
  AlertTriangleIcon,
  BellIcon,
  CloseIcon,
  SporeNode,
} from "@/components/portal/icons";
import { roleLabel, usePortal } from "@/components/portal/portal-context";
import { IconButton } from "@/components/portal/primitives/icon-button";
import {
  useDismissSuggestion,
  useMemberSuggestions,
  useMyInvitations,
  useNotificationAction,
  useNotifications,
  useRespondInvitation,
} from "@/lib/portal/hooks";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type {
  InvitationAction,
  MemberSuggestion,
  MyInvitation,
  NotificationItem,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * Notifications entry point. The feed combines the caller's pending lab
 * invitations (accept / reject / ignore) with deadline alerts for saved grants
 * and conferences due within a week. Closes on outside click / Escape via the
 * shared popover hook.
 */
export function NotificationBell() {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const { goToSection } = usePortal();
  const { data, isLoading, isError } = useMyInvitations();
  const notifications = useNotifications();
  const suggestionsQuery = useMemberSuggestions();
  const invitations = data ?? [];
  const alerts = notifications.data?.items ?? [];
  const suggestions = suggestionsQuery.data?.items ?? [];
  const count = invitations.length + alerts.length + suggestions.length;
  const loading = isLoading || notifications.isLoading || suggestionsQuery.isLoading;
  const errored = isError || notifications.isError || suggestionsQuery.isError;

  return (
    <div ref={ref} className="relative">
      <IconButton
        label={
          count > 0
            ? `Notifications — ${count} new item${count === 1 ? "" : "s"}`
            : "Notifications"
        }
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <BellIcon size={18} />
        {count > 0 ? (
          <span
            className="absolute -right-1 -top-1 flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-[#fffdf8]"
            aria-hidden="true"
          >
            {count > 9 ? "9+" : count}
          </span>
        ) : null}
      </IconButton>

      {open ? (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 top-11 z-40 w-[320px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow)]"
        >
          <p className="border-b border-[var(--divider)] px-4 py-2.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            Notifications
          </p>

          {loading ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--text-muted)]">
              Loading…
            </p>
          ) : errored ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--text-muted)]">
              Couldn&apos;t load your notifications.
            </p>
          ) : count === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
              You&apos;re all caught up.
            </p>
          ) : (
            <ul className="max-h-[60vh] divide-y divide-[var(--divider)] overflow-y-auto">
              {alerts.map((note) => (
                <NotificationRow key={note.id} note={note} />
              ))}
              {invitations.map((invitation) => (
                <InvitationRow key={invitation.id} invitation={invitation} />
              ))}
              {suggestions.map((suggestion) => (
                <SuggestionRow
                  key={suggestion.id}
                  suggestion={suggestion}
                  onView={() => {
                    setOpen(false);
                    goToSection("suggested");
                  }}
                />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * One bell notification (a fired reminder, a moved deadline, or a high-signal
 * pick). The ✕ dismisses it via the notifications endpoint, refreshing the badge.
 */
function NotificationRow({ note }: { note: NotificationItem }) {
  const act = useNotificationAction();
  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-2">
        <AlertTriangleIcon
          size={15}
          aria-hidden="true"
          className="mt-0.5 shrink-0 text-accent"
        />
        <div className="min-w-0 flex-1">
          {note.url ? (
            <a
              href={note.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {note.title}
            </a>
          ) : (
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {note.title}
            </p>
          )}
          {note.body ? (
            <p className="mt-0.5 text-[12.5px] text-[var(--text-muted)]">
              {note.body}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => act.mutate({ id: note.id, action: "dismiss" })}
          disabled={act.isPending}
          aria-label={`Dismiss notification: ${note.title}`}
          title="Dismiss"
          className="shrink-0 rounded-full p-1 text-[var(--text-muted)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <CloseIcon size={13} />
        </button>
      </div>
    </li>
  );
}

function InvitationRow({ invitation }: { invitation: MyInvitation }) {
  const respond = useRespondInvitation();
  const [error, setError] = React.useState<string | null>(null);

  const act = (action: InvitationAction) => {
    setError(null);
    respond.mutate(
      { id: invitation.id, action },
      { onError: (e) => setError((e as Error).message) },
    );
  };

  return (
    <li className="px-4 py-3">
      <p className="text-sm text-[var(--text-primary)]">
        You&apos;ve been invited to{" "}
        <span className="font-semibold">{invitation.lab_name}</span>
        {" as "}
        {roleLabel({ role: invitation.role, is_lead: false })}.
      </p>
      {invitation.inviter ? (
        <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
          From {invitation.inviter}
        </p>
      ) : null}

      <div className="mt-2.5 flex items-center gap-2">
        <ResponseButton
          tone="accept"
          disabled={respond.isPending}
          onClick={() => act("accept")}
        >
          Accept
        </ResponseButton>
        <ResponseButton
          tone="reject"
          disabled={respond.isPending}
          onClick={() => act("reject")}
        >
          Reject
        </ResponseButton>
        <ResponseButton
          tone="plain"
          disabled={respond.isPending}
          onClick={() => act("ignore")}
        >
          Ignore
        </ResponseButton>
      </div>

      {error ? (
        <p className="mt-2 text-[12px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function ResponseButton({
  tone,
  disabled,
  onClick,
  children,
}: {
  tone: "accept" | "reject" | "plain";
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const toneClass =
    tone === "accept"
      ? "bg-primary text-[#fffdf8] hover:bg-[var(--brand-primary-hover)]"
      : tone === "reject"
        ? "border border-destructive/40 bg-transparent text-destructive hover:bg-destructive hover:text-[var(--destructive-foreground)]"
        : "border border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]";
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        toneClass,
      )}
    >
      {children}
    </button>
  );
}

/**
 * A paper a teammate shared that closely matches the caller's own profile.
 * Clicking the title marks it viewed via navigation; the ✕ dismisses it via
 * the suggestions endpoint, refreshing this feed and the badge count.
 */
function SuggestionRow({
  suggestion,
  onView,
}: {
  suggestion: MemberSuggestion;
  onView: () => void;
}) {
  const dismiss = useDismissSuggestion();
  const [error, setError] = React.useState<string | null>(null);

  const handleDismiss = () => {
    setError(null);
    dismiss.mutate(suggestion.id, {
      onError: (e) => setError((e as Error).message),
    });
  };

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-2">
        <SporeNode size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          {suggestion.url ? (
            <a
              href={suggestion.url}
              target="_blank"
              rel="noreferrer"
              onClick={onView}
              className="text-sm font-medium text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {suggestion.title}
            </a>
          ) : (
            <p className="text-sm text-[var(--text-primary)]">{suggestion.title}</p>
          )}
          <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
            {suggestion.shared_by ? `Shared by ${suggestion.shared_by.name} · ` : ""}
            {suggestion.project.name}
            {suggestion.match_percent !== null
              ? ` · ${suggestion.match_percent}% match`
              : ""}
          </p>
          {error ? (
            <p className="mt-1 text-[11px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          disabled={dismiss.isPending}
          aria-label={`Dismiss suggestion: ${suggestion.title}`}
          title="Dismiss"
          className="shrink-0 rounded-full p-1 text-[var(--text-muted)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <CloseIcon size={13} />
        </button>
      </div>
    </li>
  );
}
