"use client";

import * as React from "react";
import Link from "next/link";

import { useAppHref, useAppRouter } from "@/components/demo/demo-context";
import { usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { ConfirmModal } from "@/components/portal/sections/member-row";
import { roleSentence } from "@/components/portal/settings/context-picker";
import { CAPABILITY, type Capability } from "@/lib/portal/capabilities";
import {
  useDeptManagement,
  useDeptMembers,
  useLabMemberMutations,
  useLabMembers,
  useLeaveOrg,
} from "@/lib/portal/hooks";
import { settingsPath, YOU_CONTEXT } from "@/lib/portal/settings";
import type { MyDepartment, MyLab } from "@/lib/portal/types";

const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const DANGER_BUTTON =
  "rounded-full border border-[color-mix(in_srgb,var(--danger)_45%,transparent)] bg-surface px-4 py-2 text-[13px] font-semibold text-clay transition-colors hover:bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const SELECT =
  "min-w-0 flex-1 rounded-full border border-border bg-surface px-3.5 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** What each capability lets someone do, as a member would say it. */
const CAN_DO: Record<Capability, string> = {
  [CAPABILITY.PROFILE_EDIT]: "Edit the profile Mylo ranks against",
  [CAPABILITY.PEOPLE_VIEW]: "See who else is here",
  [CAPABILITY.PEOPLE_MANAGE]: "Change roles and remove people",
  [CAPABILITY.INVITES_ISSUE]: "Invite people",
  [CAPABILITY.PROJECTS_POLICY]: "Set the rules for projects",
  [CAPABILITY.PROJECTS_OVERSEE]: "Oversee every project",
  [CAPABILITY.SERVERS_MANAGE]: "Connect Discord, Slack and Teams",
  [CAPABILITY.ANNOUNCEMENTS_MANAGE]: "Choose what Mylo announces",
  [CAPABILITY.MYLO_POLICY]: "Narrow what Mylo may do",
  [CAPABILITY.BILLING_MANAGE]: "Manage the plan",
  [CAPABILITY.TRANSFER]: "Hand it to someone else",
};

type Org =
  | { kind: "lab"; lab: MyLab }
  | { kind: "department"; dept: MyDepartment };

function orgName(org: Org): string {
  return org.kind === "lab" ? org.lab.name : org.dept.name;
}

/**
 * Settings → Your membership: your role, what it lets you do, and leaving.
 *
 * Every member gets this page, including one who manages nothing — it is how
 * they find their role and leave without asking anyone. The one person who
 * cannot leave is the one the org needs (a lab's owner, a department's head):
 * the page says so and points at the transfer instead of offering a button the
 * server will refuse.
 */
export function MembershipPage({ org }: { org: Org }) {
  const { workspaces } = usePortal();
  const router = useAppRouter();
  const appHref = useAppHref();
  const leave = useLeaveOrg();
  const [confirming, setConfirming] = React.useState(false);

  const row = org.kind === "lab" ? org.lab : org.dept;
  const key = org.kind === "lab" ? org.lab.slug : org.dept.id;
  const workspace = workspaces.find((w) => w.kind === org.kind && w.key === key);
  const noun = org.kind === "lab" ? "lab" : "department";
  const name = orgName(org);
  // The head of a department is never removable; a lab's owner may be the
  // only one, which the server checks. Either way the way out is a transfer.
  const holdsIt = org.kind === "department" ? org.dept.is_owner : org.lab.role === "owner";
  const context =
    org.kind === "lab"
      ? ({ kind: "lab", slug: org.lab.slug } as const)
      : ({ kind: "department", id: org.dept.id } as const);
  const held = (row.capabilities ?? []).filter((c) => c in CAN_DO);

  return (
    <>
      <Card className="p-5" aria-labelledby="membership-role-title">
        <h2 id="membership-role-title" className="text-base font-semibold text-[var(--text-primary)]">
          Your role
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {workspace ? `${roleSentence(workspace)} in ${name}.` : `You belong to ${name}.`}
        </p>
        {held.length ? (
          <>
            <p className="mt-3 text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
              What you can do here
            </p>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
              {held.map((c) => (
                <li key={c}>{CAN_DO[c]}</li>
              ))}
            </ul>
          </>
        ) : null}
      </Card>

      <Card className="p-5" aria-labelledby="membership-leave-title">
        <h2 id="membership-leave-title" className="text-base font-semibold text-[var(--text-primary)]">
          Leave {name}
        </h2>
        {holdsIt && org.kind === "department" ? (
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            You run this department, so you can&apos;t leave it.{" "}
            <Link
              href={appHref(settingsPath(context, "transfer"))}
              className="font-medium text-primary underline-offset-2 hover:underline"
            >
              Hand it to another member
            </Link>{" "}
            first.
          </p>
        ) : (
          <>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {org.kind === "lab"
                ? "You stop seeing the lab's feeds, projects and reports. Someone in the lab can invite you back."
                : "You give up your direct place in the department. If you also belong through one of its labs, you keep that."}
              {holdsIt ? (
                <>
                  {" "}
                  As an owner you can leave only if the lab has another owner;{" "}
                  <Link
                    href={appHref(settingsPath(context, "transfer"))}
                    className="font-medium text-primary underline-offset-2 hover:underline"
                  >
                    hand it over
                  </Link>{" "}
                  otherwise.
                </>
              ) : null}
            </p>
            <div className="mt-3">
              <button
                type="button"
                className={DANGER_BUTTON}
                onClick={() => setConfirming(true)}
                disabled={leave.isPending}
              >
                Leave the {noun}
              </button>
            </div>
            {leave.error ? (
              <p role="alert" className="mt-2 text-[12.5px] text-clay">
                {(leave.error as Error).message}
              </p>
            ) : null}
          </>
        )}
      </Card>

      {confirming ? (
        <ConfirmModal
          title={`Leave ${name}?`}
          body={
            org.kind === "lab"
              ? "You lose access to the lab straight away. Only someone in the lab can bring you back."
              : "You lose your direct place in the department straight away."
          }
          confirmLabel={`Leave the ${noun}`}
          danger
          busy={leave.isPending}
          onClose={() => setConfirming(false)}
          onConfirm={() =>
            leave.mutate(
              org.kind === "lab"
                ? { kind: "lab", slug: org.lab.slug }
                : { kind: "department", id: org.dept.id },
              {
                onSuccess: () => router.replace(settingsPath(YOU_CONTEXT)),
                onSettled: () => setConfirming(false),
              },
            )
          }
        />
      ) : null}
    </>
  );
}

/** A person the org could be handed to. */
type Candidate = { username: string; name: string };

/**
 * Settings → Transfer & close. Handing the org over is one decision on one
 * page: pick the member, confirm, and you step down to admin. Closing an org is
 * not something the app can do yet, and the card says so rather than hiding it.
 */
export function TransferPage({ org }: { org: Org }) {
  if (org.kind === "lab") return <LabTransfer lab={org.lab} />;
  return <DeptTransfer dept={org.dept} />;
}

function LabTransfer({ lab }: { lab: MyLab }) {
  const { user } = usePortal();
  const { data } = useLabMembers(lab.slug);
  const { transfer } = useLabMemberMutations(lab.slug);
  const candidates = (data ?? [])
    .filter((m) => m.username !== user.username)
    .map((m) => ({ username: m.username, name: m.name }));
  return (
    <TransferBody
      noun="lab"
      name={lab.name}
      candidates={candidates}
      busy={transfer.isPending}
      error={(transfer.error as Error | null)?.message ?? null}
      onTransfer={(username, done) => transfer.mutate(username, { onSuccess: done })}
      after="You become an admin. Only the new owner can hand it back."
    />
  );
}

function DeptTransfer({ dept }: { dept: MyDepartment }) {
  const { user } = usePortal();
  const { data } = useDeptMembers(dept.id);
  const { transfer } = useDeptManagement(dept.id);
  // Only a direct member can run a department.
  const candidates = (data ?? [])
    .filter((m) => m.source === "direct" && !m.is_head && m.username !== user.username)
    .map((m) => ({ username: m.username, name: m.name }));
  return (
    <TransferBody
      noun="department"
      name={dept.name}
      candidates={candidates}
      busy={transfer.isPending}
      error={(transfer.error as Error | null)?.message ?? null}
      onTransfer={(username, done) => transfer.mutate(username, { onSuccess: done })}
      after="You become an admin. Only the new head can hand it back."
    />
  );
}

function TransferBody({
  noun,
  name,
  candidates,
  busy,
  error,
  onTransfer,
  after,
}: {
  noun: "lab" | "department";
  name: string;
  candidates: Candidate[];
  busy: boolean;
  error: string | null;
  onTransfer: (username: string, done: () => void) => void;
  after: string;
}) {
  const [target, setTarget] = React.useState("");
  const [confirming, setConfirming] = React.useState(false);
  const chosen = candidates.find((c) => c.username === target) ?? null;
  const selectId = React.useId();

  return (
    <>
      <Card className="p-5" aria-labelledby="transfer-title">
        <h2 id="transfer-title" className="text-base font-semibold text-[var(--text-primary)]">
          Hand {name} over
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The person you choose {noun === "lab" ? "owns the lab" : "runs the department"} from
          then on. {after} This cannot be undone from your side.
        </p>
        {candidates.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-secondary)]">
            {noun === "lab"
              ? "There is nobody else in the lab yet. Invite someone first."
              : "There is no other direct member of the department yet. Add someone first."}
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label htmlFor={selectId} className="sr-only">
              New {noun === "lab" ? "owner" : "head"}
            </label>
            <select
              id={selectId}
              className={SELECT}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value="">Choose a member…</option>
              {candidates.map((c) => (
                <option key={c.username} value={c.username}>
                  {c.name} ({c.username})
                </option>
              ))}
            </select>
            <button
              type="button"
              className={GHOST_BUTTON}
              disabled={!chosen || busy}
              onClick={() => setConfirming(true)}
            >
              Hand over
            </button>
          </div>
        )}
        {error ? (
          <p role="alert" className="mt-2 text-[12.5px] text-clay">
            {error}
          </p>
        ) : null}
      </Card>

      <Card className="p-5" aria-labelledby="close-title">
        <h2 id="close-title" className="text-base font-semibold text-[var(--text-primary)]">
          Close {name}
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Closing a {noun} can&apos;t be done from the app yet. Ask whoever runs this
          Mycelium to remove it.
        </p>
      </Card>

      {confirming && chosen ? (
        <ConfirmModal
          title={`Hand ${name} to ${chosen.name}?`}
          body={`${chosen.name} ${noun === "lab" ? "becomes the owner" : "becomes the head"}. ${after} This cannot be undone.`}
          confirmLabel={noun === "lab" ? "Transfer lab" : "Transfer department"}
          danger
          busy={busy}
          onClose={() => setConfirming(false)}
          onConfirm={() =>
            onTransfer(chosen.username, () => {
              setConfirming(false);
              setTarget("");
            })
          }
        />
      ) : null}
    </>
  );
}
