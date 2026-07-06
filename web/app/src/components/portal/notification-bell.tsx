"use client";

import * as React from "react";

import { BellIcon } from "@/components/portal/icons";
import { roleLabel } from "@/components/portal/portal-context";
import { IconButton } from "@/components/portal/primitives/icon-button";
import { useMyInvitations, useRespondInvitation } from "@/lib/portal/hooks";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type { InvitationAction, MyInvitation } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * Notifications entry point. The feed is the caller's pending lab invitations:
 * each can be accepted (joins the lab), rejected, or ignored (silently
 * dismissed). Closes on outside click / Escape via the shared popover hook.
 */
export function NotificationBell() {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const { data, isLoading, isError } = useMyInvitations();
  const invitations = data ?? [];
  const count = invitations.length;

  return (
    <div ref={ref} className="relative">
      <IconButton
        label={
          count > 0
            ? `Notifications — ${count} pending invitation${count === 1 ? "" : "s"}`
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

          {isLoading ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--text-muted)]">
              Loading…
            </p>
          ) : isError ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--text-muted)]">
              Couldn&apos;t load your notifications.
            </p>
          ) : count === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
              You&apos;re all caught up.
            </p>
          ) : (
            <ul className="max-h-[60vh] divide-y divide-[var(--divider)] overflow-y-auto">
              {invitations.map((invitation) => (
                <InvitationRow key={invitation.id} invitation={invitation} />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
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
