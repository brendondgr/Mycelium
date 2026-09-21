"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Pill } from "@/components/portal/primitives/pill";
import { Modal, ModalHeader } from "@/components/portal/primitives/modal";
import { useLabMemberMutations } from "@/lib/portal/hooks";
import { grantableLabRoles, outranksLabMember } from "@/lib/portal/nav";
import type { LabMember, LabRole, MyLab } from "@/lib/portal/types";

/** Capitalise the first letter of a role string for display. */
function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type Props = {
  member: LabMember;
  /** The lab in scope — absent when the roster is read-only. */
  lab?: Pick<MyLab, "slug" | "name" | "role" | "is_lead">;
  /** The signed-in user's username, so the row never offers to act on itself. */
  viewer?: string;
};

export function MemberRow({ member, lab, viewer }: Props) {
  const roleDisplay = member.is_lead ? "PI" : capitalize(member.role);

  // Authority runs strictly downward and the server is the authority; this only
  // decides whether to *draw* a control. A row the caller cannot act on renders
  // exactly as it always did, rather than showing a button that will 403.
  const isSelf = viewer !== undefined && viewer === member.username;
  const canAct = Boolean(lab) && !isSelf && outranksLabMember(lab!, member);
  const roles = lab ? grantableLabRoles(lab) : [];
  // Ownership moves by transfer alone, and only the owner may start it.
  const canTransfer = Boolean(lab) && !isSelf && lab!.role === "owner";

  if (!canAct && !canTransfer) {
    return <Row member={member} roleDisplay={roleDisplay} />;
  }
  return (
    <Row member={member} roleDisplay={roleDisplay}>
      <MemberControls
        member={member}
        lab={lab!}
        roles={roles}
        canAct={canAct}
        canTransfer={canTransfer}
      />
    </Row>
  );
}

// ---------------------------------------------------------------------------
// Presentation
// ---------------------------------------------------------------------------

function Row({
  member,
  roleDisplay,
  children,
}: {
  member: LabMember;
  roleDisplay: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3.5 border-b border-[var(--divider)] px-5 py-3.5 hover:bg-surface-alt">
      <Avatar initials={member.initials} seed={member.username} size={36} />

      {/* Name + role */}
      <div className="min-w-0 flex-1">
        <p className="m-0 truncate text-sm font-medium text-[var(--text-primary)]">
          {member.name}
        </p>
        <p className="m-0 text-xs text-[var(--text-secondary)]">{roleDisplay}</p>
      </div>

      {/* Email — hidden on small screens */}
      <span className="hidden text-xs text-[var(--text-secondary)] sm:block">
        {member.email}
      </span>

      {/* Lead PIs get a highlight pill; the role already shows under the name. */}
      {member.is_lead ? <Pill tone="primary">PI</Pill> : null}

      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

function MemberControls({
  member,
  lab,
  roles,
  canAct,
  canTransfer,
}: {
  member: LabMember;
  lab: Pick<MyLab, "slug" | "name" | "role" | "is_lead">;
  roles: LabRole[];
  canAct: boolean;
  canTransfer: boolean;
}) {
  const { remove, setRole, transfer } = useLabMemberMutations(lab.slug);
  const [confirming, setConfirming] = React.useState<null | "remove" | "hand">(
    null,
  );

  // The server's own sentence is the useful part ("Only the lab's PI can grant
  // that role"), so it is shown rather than a generic failure.
  const error =
    (remove.error as Error | null)?.message ??
    (setRole.error as Error | null)?.message ??
    (transfer.error as Error | null)?.message ??
    null;
  const busy = remove.isPending || setRole.isPending || transfer.isPending;

  return (
    <div className="flex items-center gap-2">
      {error ? (
        <span
          role="alert"
          className="hidden max-w-[16rem] truncate text-xs text-[var(--destructive)] md:block"
          title={error}
        >
          {error}
        </span>
      ) : null}

      {canAct && roles.length > 0 ? (
        <label className="sr-only" htmlFor={`role-${member.username}`}>
          Role for {member.name}
        </label>
      ) : null}
      {canAct && roles.length > 0 ? (
        <select
          id={`role-${member.username}`}
          value={roles.includes(member.role) ? member.role : ""}
          disabled={busy}
          onChange={(event) =>
            setRole.mutate({
              username: member.username,
              role: event.target.value,
            })
          }
          className="rounded-md border border-[var(--divider)] bg-surface px-2 py-1 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {/* A role the caller cannot grant (their own, or above) still has to
              render as the current value, or the select would silently lie. */}
          {roles.includes(member.role) ? null : (
            <option value="">{capitalize(member.role)}</option>
          )}
          {roles.map((role) => (
            <option key={role} value={role}>
              {capitalize(role)}
            </option>
          ))}
        </select>
      ) : null}

      {canTransfer ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => setConfirming("hand")}
          className="rounded-full border border-[var(--divider)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          Make PI
        </button>
      ) : null}

      {canAct ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => setConfirming("remove")}
          className="rounded-full border border-[var(--divider)] px-2.5 py-1 text-xs font-medium text-[var(--destructive)] transition-colors hover:bg-[color-mix(in_srgb,var(--destructive)_12%,transparent)] hover:border-[color-mix(in_srgb,var(--destructive)_50%,transparent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          Remove
        </button>
      ) : null}

      {confirming === "remove" ? (
        <ConfirmModal
          title={`Remove ${member.name}?`}
          body={`They lose access to ${lab.name} and its feeds. You can invite them back.`}
          confirmLabel="Remove"
          danger
          busy={busy}
          onClose={() => setConfirming(null)}
          onConfirm={() =>
            remove.mutate(member.username, {
              onSuccess: () => setConfirming(null),
            })
          }
        />
      ) : null}

      {confirming === "hand" ? (
        <ConfirmModal
          title={`Hand ${lab.name} to ${member.name}?`}
          body={
            `${member.name} becomes the PI and owner. You become an admin, and ` +
            `you will not be able to take it back — only they can hand it over ` +
            `again. This cannot be undone.`
          }
          confirmLabel="Transfer ownership"
          danger
          busy={busy}
          onClose={() => setConfirming(null)}
          onConfirm={() =>
            transfer.mutate(member.username, {
              onSuccess: () => setConfirming(null),
            })
          }
        />
      ) : null}
    </div>
  );
}

function ConfirmModal({
  title,
  body,
  confirmLabel,
  danger,
  busy,
  onClose,
  onConfirm,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal onClose={onClose} label={title}>
      <ModalHeader eyebrow="Members" title={title} onClose={onClose} />
      <div className="px-5 py-4">
        <p className="m-0 text-sm text-[var(--text-secondary)]">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-full border border-[var(--divider)] px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={
              danger
                ? "rounded-full bg-[var(--destructive)] px-4 py-2 text-xs font-semibold text-[#fffdf8] transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                : "rounded-full bg-primary px-4 py-2 text-xs font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            }
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
