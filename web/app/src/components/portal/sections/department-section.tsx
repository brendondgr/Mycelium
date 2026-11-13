"use client";

/**
 * A department's roster and labs, as cards: Settings → People and → Labs use
 * them with their controls, the workspace Members directory without. The
 * department itself is managed in Settings (`components/portal/settings/`).
 */

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { ConfirmModal } from "@/components/portal/sections/member-row";
import { useDeptLabs, useDeptManagement, useDeptMembers } from "@/lib/portal/hooks";
import { CAPABILITY, can } from "@/lib/portal/capabilities";
import type {
  DeptLabRow,
  DeptMemberRow,
  LabRole,
  MyDepartment,
} from "@/lib/portal/types";

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const INPUT =
  "min-w-0 flex-1 rounded-full border border-border bg-surface px-3.5 py-2 text-sm text-[var(--text-primary)] outline-none focus-visible:ring-2 focus-visible:ring-ring";

function seatPill(status: string | null): React.ReactNode {
  if (status === "active") return <Pill tone="primary">Seated</Pill>;
  if (status === "pending") return <Pill tone="dashed">Pending</Pill>;
  return <Pill tone="neutral">No seat</Pill>;
}

/**
 * A department's people: its direct members, then everyone folded in through
 * one of its labs. With `canManage` (Settings → People) it adds people and
 * draws each row's controls; without it (the workspace Members directory) it
 * only lists them.
 */
export function DeptMembersCard({
  deptId,
  canManage,
  mine,
  viewer,
  title = "Members",
}: {
  deptId: string;
  canManage: boolean;
  mine: MyDepartment | null;
  viewer: string;
  title?: string;
}) {
  const { data, isLoading, isError } = useDeptMembers(deptId);
  const { addMember } = useDeptManagement(deptId);
  const [username, setUsername] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    const value = username.trim();
    if (!value) return;
    addMember.mutate(
      { username: value },
      {
        onSuccess: (result) => {
          setUsername("");
          setNotice(result.detail);
        },
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {title}
      </h2>

      {canManage ? (
        <form onSubmit={onAdd} className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className={INPUT}
            placeholder="Invite a member by username"
            aria-label="Invite a member by username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button type="submit" className={PRIMARY_BUTTON} disabled={addMember.isPending}>
            {addMember.isPending ? "Inviting…" : "Invite"}
          </button>
        </form>
      ) : null}
      {error ? (
        <p className="mb-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mb-2 text-[12.5px] text-[var(--text-secondary)]" role="status">
          {notice}
        </p>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading members…</p>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load members.</p>
      ) : !data || data.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No members yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((m: DeptMemberRow) => (
            <li key={m.username} className="flex flex-wrap items-center gap-3 py-2.5">
              <Avatar initials={m.initials} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                    {m.name}
                  </span>
                  {m.source === "lab" && m.lab ? (
                    <Pill tone="neutral" className="px-2 py-0.5">
                      via {m.lab}
                    </Pill>
                  ) : null}
                </div>
                <span className="truncate text-xs text-[var(--text-secondary)]">
                  {m.email || m.username}
                </span>
              </div>
              {m.is_head ? <Pill tone="primary">Head</Pill> : null}
              {seatPill(m.seat_status)}
              {canManage && mine && m.source === "direct" ? (
                <DeptMemberControls
                  deptId={deptId}
                  member={m}
                  mine={mine}
                  isSelf={m.username === viewer}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Role, remove and hand-over controls for one direct department member.
 *
 * Authority runs strictly downward (``DEPT_ROLE_RANK`` on the server): an admin
 * re-roles and removes members and viewers, only the head grants admin, and
 * the head changes only by transfer. The server says which rows the caller may
 * act on (`can_act`) and which roles they may grant; a control the caller cannot
 * use is not drawn.
 */
function DeptMemberControls({
  deptId,
  member,
  mine,
  isSelf,
}: {
  deptId: string;
  member: DeptMemberRow;
  mine: MyDepartment;
  isSelf: boolean;
}) {
  const { removeMember, setMemberRole, transfer } = useDeptManagement(deptId);
  const [confirming, setConfirming] = React.useState<null | "remove" | "hand">(
    null,
  );
  const canAct = !isSelf && member.can_act;
  const roles = mine.grantable_roles;
  const canTransfer = can(mine, CAPABILITY.TRANSFER) && !isSelf && !member.is_head;
  const busy =
    removeMember.isPending || setMemberRole.isPending || transfer.isPending;
  const error =
    (removeMember.error as Error | null)?.message ??
    (setMemberRole.error as Error | null)?.message ??
    (transfer.error as Error | null)?.message ??
    null;

  if (!canAct && !canTransfer) return null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {error ? (
        <span role="alert" className="max-w-[14rem] truncate text-xs text-clay" title={error}>
          {error}
        </span>
      ) : null}
      {canAct && roles.length > 0 ? (
        <>
          <label className="sr-only" htmlFor={`dept-role-${member.username}`}>
            Role for {member.name}
          </label>
          <select
            id={`dept-role-${member.username}`}
            value={roles.includes(member.role) ? member.role : ""}
            disabled={busy}
            onChange={(event) =>
              setMemberRole.mutate({
                username: member.username,
                role: event.target.value as LabRole,
              })
            }
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {roles.includes(member.role) ? null : (
              <option value="">{capitalize(member.role)}</option>
            )}
            {roles.map((role) => (
              <option key={role} value={role}>
                {capitalize(role)}
              </option>
            ))}
          </select>
        </>
      ) : null}
      {canTransfer ? (
        <button
          type="button"
          className={GHOST_BUTTON}
          disabled={busy}
          onClick={() => setConfirming("hand")}
        >
          Make head
        </button>
      ) : null}
      {canAct ? (
        <button
          type="button"
          className={GHOST_BUTTON}
          disabled={busy}
          onClick={() => setConfirming("remove")}
        >
          Remove
        </button>
      ) : null}

      {confirming === "remove" ? (
        <ConfirmModal
          title={`Remove ${member.name}?`}
          body="They lose their direct place in the department. Anyone who belongs through a lab keeps that."
          confirmLabel="Remove"
          danger
          busy={busy}
          onClose={() => setConfirming(null)}
          onConfirm={() =>
            removeMember.mutate(member.username, {
              onSuccess: () => setConfirming(null),
            })
          }
        />
      ) : null}
      {confirming === "hand" ? (
        <ConfirmModal
          title={`Hand the department to ${member.name}?`}
          body={
            `${member.name} becomes the department head. You become an admin, ` +
            `and you will not be able to take it back — only they can hand it ` +
            `over again. This cannot be undone.`
          }
          confirmLabel="Transfer department"
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

/**
 * The labs under a department. `canManage` creates, attaches and detaches labs;
 * `canBill` decides which of them the department plan covers. Neither → a list.
 */
export function DeptLabsCard({
  deptId,
  canManage,
  canBill = false,
}: {
  deptId: string;
  canManage: boolean;
  canBill?: boolean;
}) {
  const { data, isLoading, isError } = useDeptLabs(deptId);
  const { attachLab, createLab, detachLab, setLabInclusion } =
    useDeptManagement(deptId);
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const onError = (err: unknown) => setError((err as Error).message);

  function onCreate() {
    setError(null);
    const v = name.trim();
    if (!v) return;
    createLab.mutate(v, { onSuccess: () => setName(""), onError });
  }

  function onAttach() {
    setError(null);
    setNotice(null);
    const v = slug.trim();
    if (!v) return;
    attachLab.mutate(v, {
      onSuccess: (result) => {
        setSlug("");
        // Only the lab's owner attaches it outright; anyone else's attach
        // waits for the owner to accept.
        if (!Array.isArray(result)) setNotice(result.detail);
      },
      onError,
    });
  }

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Labs
      </h2>

      {canManage ? (
        <div className="mb-3 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className={INPUT}
              aria-label="New lab name"
              placeholder="Create a lab by name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={createLab.isPending}
              onClick={onCreate}
            >
              {createLab.isPending ? "Creating…" : "Create"}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className={INPUT}
              aria-label="Slug of a lab to attach"
              placeholder="Attach an existing lab by slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
            <button
              type="button"
              className={GHOST_BUTTON}
              disabled={attachLab.isPending}
              onClick={onAttach}
            >
              {attachLab.isPending ? "Attaching…" : "Attach"}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p className="mb-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mb-2 text-[12.5px] text-[var(--text-secondary)]" role="status">
          {notice}
        </p>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading labs…</p>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load labs.</p>
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No labs yet"
          description="Create a lab under this department or attach an existing one."
        />
      ) : (
        <ul className="divide-y divide-border">
          {data.map((lab: DeptLabRow) => (
            <li key={lab.slug} className="flex flex-wrap items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {lab.name}
                </span>
                <span className="block text-xs text-[var(--text-secondary)]">
                  {lab.member_count} member{lab.member_count === 1 ? "" : "s"}
                  {lab.included_in_plan ? (
                    <span className="ml-2 rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">
                      In plan
                    </span>
                  ) : null}
                </span>
              </div>
              {canManage || canBill ? (
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {canBill ? (
                  <button
                    type="button"
                    className={GHOST_BUTTON}
                    onClick={() => {
                      setError(null);
                      setLabInclusion.mutate(
                        { slug: lab.slug, included: !lab.included_in_plan },
                        { onError },
                      );
                    }}
                    disabled={setLabInclusion.isPending}
                    title={
                      lab.included_in_plan
                        ? "Stop the department paying for this lab's members"
                        : "Cover this lab's members on the department plan"
                    }
                  >
                    {lab.included_in_plan ? "Remove from plan" : "Include in plan"}
                  </button>
                  ) : null}
                  {canManage ? (
                  <button
                    type="button"
                    className={GHOST_BUTTON}
                    onClick={() => detachLab.mutate(lab.slug, { onError })}
                    disabled={detachLab.isPending}
                    aria-label={`Detach ${lab.name} from the department`}
                  >
                    Detach
                  </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
