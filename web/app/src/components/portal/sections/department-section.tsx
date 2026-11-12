"use client";

import * as React from "react";
import { useParams } from "next/navigation";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { AnnouncementsCard } from "@/components/portal/sections/announcements-card";
import { AgentPolicyCard } from "@/components/portal/mylo/settings-cards";
import { DeptDiscordCard } from "@/components/portal/sections/labs-section";
import { DeptPlanCard } from "@/components/portal/sections/org-plan-card";
import { OrgInviteCard } from "@/components/portal/sections/org-invite-card";
import { ConfirmModal } from "@/components/portal/sections/member-row";
import { usePortal } from "@/components/portal/portal-context";
import {
  useDeptBilling,
  useDeptLabs,
  useEntitlements,
  useDeptManagement,
  useDeptMembers,
  useMyDepartments,
} from "@/lib/portal/hooks";
import { grantableDeptRoles, outranksDeptMember } from "@/lib/portal/nav";
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

/** The department management surface — members, labs, and the plan (head/admins). */
export function DepartmentSection() {
  const params = useParams();
  const deptId = String((params?.id as string) ?? "");

  const { user } = usePortal();
  const billing = useDeptBilling(deptId);
  // The caller's own standing here decides which roster controls to draw; the
  // server re-checks every one of them.
  const departments = useMyDepartments();
  const mine = (departments.data ?? []).find((d) => d.id === deptId) ?? null;
  const canManage = Boolean(billing.data?.can_manage);
  const deptName = billing.data?.scope_name ?? "Department";
  // No plan to show when the instance runs without billing (mycelium.toml).
  const { data: entitlements } = useEntitlements();
  const billingOn = entitlements?.billing_mode !== "off";

  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title={`${deptName} settings`}
        subtitle={
          billingOn
            ? "Manage the department's members, labs, and subscription plan."
            : "Manage the department's members and labs."
        }
      />
      <div className="grid items-start gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          {canManage ? (
            <OrgInviteCard
              kind="department"
              id={deptId}
              canInvite
              isVerified={user.isVerified}
            />
          ) : null}
          <DeptMembersCard
            deptId={deptId}
            canManage={canManage}
            mine={mine}
            viewer={user.username}
          />
          <DeptLabsCard deptId={deptId} canManage={canManage} />
        </div>
        <div className="space-y-4">
          {canManage && deptId ? <DeptDiscordCard deptId={deptId} /> : null}
          {billingOn ? <DeptPlanCard deptId={deptId} /> : null}
          {canManage && deptId ? (
            <AgentPolicyCard kind="department" orgRef={deptId} name={deptName} />
          ) : null}
        </div>
      </div>
      {canManage ? (
        <div className="mt-4">
          <AnnouncementsCard target={{ department: deptId }} name={deptName} />
        </div>
      ) : null}
    </div>
  );
}

function seatPill(status: string | null): React.ReactNode {
  if (status === "active") return <Pill tone="primary">Seated</Pill>;
  if (status === "pending") return <Pill tone="dashed">Pending</Pill>;
  return <Pill tone="neutral">No seat</Pill>;
}

function DeptMembersCard({
  deptId,
  canManage,
  mine,
  viewer,
}: {
  deptId: string;
  canManage: boolean;
  mine: MyDepartment | null;
  viewer: string;
}) {
  const { data, isLoading, isError } = useDeptMembers(deptId);
  const { addMember } = useDeptManagement(deptId);
  const [username, setUsername] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const value = username.trim();
    if (!value) return;
    addMember.mutate(
      { username: value },
      {
        onSuccess: () => setUsername(""),
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Members
      </h3>

      {canManage ? (
        <form onSubmit={onAdd} className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className={INPUT}
            placeholder="Add a member by username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button type="submit" className={PRIMARY_BUTTON} disabled={addMember.isPending}>
            {addMember.isPending ? "Adding…" : "Add"}
          </button>
        </form>
      ) : null}
      {error ? (
        <p className="mb-2 text-[12.5px] text-clay" role="alert">
          {error}
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
 * Authority runs strictly downward (``DEPT_ROLE_RANK``): an admin re-roles and
 * removes members and viewers, only the head grants admin, and the head
 * changes only by transfer. A control the caller cannot use is not drawn.
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
  const canAct = !isSelf && outranksDeptMember(mine, member);
  const roles = grantableDeptRoles(mine);
  const canTransfer = mine.is_owner && !isSelf && !member.is_head;
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

function DeptLabsCard({ deptId, canManage }: { deptId: string; canManage: boolean }) {
  const { data, isLoading, isError } = useDeptLabs(deptId);
  const { attachLab, createLab, detachLab, setLabInclusion } =
    useDeptManagement(deptId);
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const onError = (err: unknown) => setError((err as Error).message);

  function onCreate() {
    setError(null);
    const v = name.trim();
    if (!v) return;
    createLab.mutate(v, { onSuccess: () => setName(""), onError });
  }

  function onAttach() {
    setError(null);
    const v = slug.trim();
    if (!v) return;
    attachLab.mutate(v, { onSuccess: () => setSlug(""), onError });
  }

  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Labs
      </h3>

      {canManage ? (
        <div className="mb-3 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className={INPUT}
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
            <li key={lab.slug} className="flex items-center gap-3 py-2.5">
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
              {canManage ? (
                <div className="flex items-center gap-2">
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
                  <button
                    type="button"
                    className={GHOST_BUTTON}
                    onClick={() => detachLab.mutate(lab.slug)}
                    disabled={detachLab.isPending}
                  >
                    Detach
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
