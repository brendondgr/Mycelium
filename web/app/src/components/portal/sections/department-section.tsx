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
import { usePortal } from "@/components/portal/portal-context";
import {
  useDeptBilling,
  useDeptLabs,
  useEntitlements,
  useDeptManagement,
  useDeptMembers,
} from "@/lib/portal/hooks";
import type { DeptLabRow, DeptMemberRow } from "@/lib/portal/types";

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
          <DeptMembersCard deptId={deptId} canManage={canManage} />
          <DeptLabsCard deptId={deptId} canManage={canManage} />
        </div>
        <div className="space-y-4">
          {canManage && deptId ? <DeptDiscordCard deptId={deptId} /> : null}
          {billingOn ? <DeptPlanCard deptId={deptId} /> : null}
          {deptId ? <AgentPolicyCard kind="department" orgRef={deptId} name={deptName} /> : null}
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
}: {
  deptId: string;
  canManage: boolean;
}) {
  const { data, isLoading, isError } = useDeptMembers(deptId);
  const { addMember, removeMember } = useDeptManagement(deptId);
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
            <li key={m.username} className="flex items-center gap-3 py-2.5">
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
              {seatPill(m.seat_status)}
              {canManage && m.source === "direct" ? (
                <button
                  type="button"
                  className={GHOST_BUTTON}
                  onClick={() => removeMember.mutate(m.username)}
                  disabled={removeMember.isPending}
                >
                  Remove
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
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
