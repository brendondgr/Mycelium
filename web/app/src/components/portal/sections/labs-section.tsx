"use client";

import * as React from "react";

import Link from "next/link";

import {
  DiscordIcon,
  EditIcon,
  FolderIcon,
  MembersIcon,
  PlusIcon,
} from "@/components/portal/icons";
import { roleLabel, usePortal } from "@/components/portal/portal-context";
import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { LabEditorModal } from "@/components/portal/sections/lab-editor-modal";
import { MemberRow } from "@/components/portal/sections/member-row";
import { OrgInviteCard } from "@/components/portal/sections/org-invite-card";
import {
  useConnectLabDiscord,
  useCreateDepartment,
  useCreateLab,
  useCreateProject,
  useIssueLabActivationCode,
  useLabBilling,
  useLabDiscordStatus,
  useLabMembers,
  useLabProfile,
  useLabProjects,
  useMyDepartments,
  useProjectMembership,
} from "@/lib/portal/hooks";
import { ApiError } from "@/lib/api-error";
import { SECTION_ROUTES } from "@/lib/portal/routes";
import type { ClusterGroup } from "@/lib/auth-types";
import type { LabMember, MyDepartment, MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Pull the (untyped) `clusters` array off a lab's stored `interests` blob. */
function readClusters(interests: Record<string, unknown> | undefined | null): ClusterGroup[] {
  const raw = interests?.clusters;
  return Array.isArray(raw) ? (raw as ClusterGroup[]) : [];
}

/**
 * Partition `items` across `clusters` by membership test `inCluster`, in
 * cluster order, claiming each item for at most one group. Anything unclaimed
 * comes back as `other`.
 */
function groupByCluster<T>(
  items: T[],
  clusters: ClusterGroup[],
  inCluster: (item: T, cluster: ClusterGroup) => boolean,
): { groups: { cluster: ClusterGroup; items: T[] }[]; other: T[] } {
  const claimed = new Set<T>();
  const groups = clusters
    .map((cluster) => {
      const matched = items.filter(
        (item) => !claimed.has(item) && inCluster(item, cluster),
      );
      matched.forEach((item) => claimed.add(item));
      return { cluster, items: matched };
    })
    .filter((group) => group.items.length > 0);
  const other = items.filter((item) => !claimed.has(item));
  return { groups, other };
}

/** A small colored dot + label used as a cluster group header. */
function ClusterGroupHeading({ cluster }: { cluster: ClusterGroup }) {
  const token = clusterAccentVar(cluster.id);
  return (
    <p
      className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em]"
      style={{ color: `var(${token})` }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: `var(${token})` }}
      />
      {cluster.label}
    </p>
  );
}

function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

const SECONDARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full border border-border bg-surface px-4 py-[9px] text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

// Discord's own brand blurple — the one sanctioned exception to the botanical
// palette (like a "Sign in with Google" button), used only for this affordance.
const DISCORD_BUTTON =
  "inline-flex items-center gap-2 rounded-full bg-[#5865F2] px-4 py-[9px] text-[13px] font-semibold text-white transition-colors hover:bg-[#4752c4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5865F2] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)] disabled:opacity-50";

const INPUT =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

// ---------------------------------------------------------------------------
// LabsSection — the Lab tab: a list of the caller's labs + a management detail.
// ---------------------------------------------------------------------------

export function LabsSection() {
  const { user, labs, labsLoading, labScope, setLabScope, currentLab } =
    usePortal();
  const [showCreate, setShowCreate] = React.useState(false);
  const [showCreateDept, setShowCreateDept] = React.useState(false);
  const [editing, setEditing] = React.useState(false);

  // Standing up an org is what verifying the address unlocks, so the button is
  // disabled here rather than left to 403 after someone has typed a name in.
  const canCreateOrg = user.isVerified;
  const lockedTitle = canCreateOrg
    ? undefined
    : "Verify your email address on the Account page to create a lab or department.";

  const createAction = (
    <button
      type="button"
      className={PRIMARY_BUTTON}
      disabled={!canCreateOrg}
      title={lockedTitle}
      onClick={() => setShowCreate(true)}
    >
      <PlusIcon size={15} />
      Create lab
    </button>
  );

  // When a lab is the active workspace, this page is that lab's management —
  // no list of other labs (switch labs from the workspace switcher instead).
  if (currentLab) {
    const canManage = canManageLab(currentLab);
    return (
      <div>
        <SectionHeader
          title={`Manage ${currentLab.name}`}
          subtitle="Switch labs from the workspace switcher in the top bar."
          action={
            <div className="flex flex-wrap items-center gap-2">
              {canManage ? (
                <button
                  type="button"
                  className={SECONDARY_BUTTON}
                  onClick={() => setEditing(true)}
                >
                  <EditIcon size={14} />
                  Edit profile
                </button>
              ) : null}
              {createAction}
            </div>
          }
        />
        <LabDetail
          lab={currentLab}
          onEditProfile={canManage ? () => setEditing(true) : undefined}
        />

        {editing ? (
          <LabEditorModal
            lab={currentLab}
            onClose={() => setEditing(false)}
          />
        ) : null}

        {showCreate ? (
          <CreateLabModal
            onClose={() => setShowCreate(false)}
            onCreated={(slug) => {
              setLabScope(slug);
              setShowCreate(false);
            }}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        title="Labs & departments"
        subtitle="Your research groups. Select a lab to make it the active workspace and manage it."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={SECONDARY_BUTTON}
              disabled={!canCreateOrg}
              title={lockedTitle}
              onClick={() => setShowCreateDept(true)}
            >
              <PlusIcon size={15} />
              Create department
            </button>
            {createAction}
          </div>
        }
      />

      {canCreateOrg ? null : <VerifyToCreateNotice />}

      {labsLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="h-[92px] animate-pulse rounded-2xl bg-surface-alt"
            />
          ))}
        </div>
      ) : labs.length === 0 ? (
        <EmptyState
          icon={<MembersIcon size={28} />}
          title="You're not part of any lab yet"
          description="Create a lab to invite collaborators, define a shared purpose, and organize projects into focus areas."
          action={
            <button
              type="button"
              className={PRIMARY_BUTTON}
              onClick={() => setShowCreate(true)}
            >
              <PlusIcon size={15} />
              Create a lab
            </button>
          }
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {labs.map((lab) => (
              <LabCard
                key={lab.slug}
                lab={lab}
                active={lab.slug === labScope}
                onSelect={() => setLabScope(lab.slug)}
              />
            ))}
          </div>

          <p className="mt-6 text-sm text-[var(--text-secondary)]">
            Select a lab to make it your active workspace, then manage it here.
          </p>
        </>
      )}

      <DepartmentsBlock />

      {showCreate ? (
        <CreateLabModal
          onClose={() => setShowCreate(false)}
          onCreated={(slug) => {
            setLabScope(slug);
            setShowCreate(false);
          }}
        />
      ) : null}

      {showCreateDept ? (
        <CreateDepartmentModal onClose={() => setShowCreateDept(false)} />
      ) : null}
    </div>
  );
}

/** Why the create buttons are dark, and where to go to light them up. */
function VerifyToCreateNotice() {
  return (
    <p className="mb-4 rounded-xl border border-border bg-surface-alt px-3.5 py-2.5 text-[12.5px] text-[var(--text-secondary)]">
      Creating a lab or department needs an activated account. A lab exists to
      invite people into, and Mycelium will not mail strangers on behalf of an
      address that has not answered its own code — enter yours on the{" "}
      <Link
        className="font-medium text-primary underline underline-offset-2"
        href={SECTION_ROUTES.account}
      >
        Account page
      </Link>
      .
    </p>
  );
}

/** The caller's departments, listed under their labs. */
function DepartmentsBlock() {
  const { data, isLoading } = useMyDepartments();

  if (isLoading || !data || data.length === 0) {
    return null;
  }

  return (
    <div className="mt-8">
      <h3 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Departments
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {data.map((department) => (
          <DepartmentCard key={department.id} department={department} />
        ))}
      </div>
    </div>
  );
}

function DepartmentCard({ department }: { department: MyDepartment }) {
  return (
    <Link
      href={`/app/department/${department.id}`}
      className="block rounded-2xl border border-border bg-card p-4 transition-colors hover:border-brand-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <p className="text-[15px] font-semibold text-[var(--text-primary)]">
        {department.name}
      </p>
      <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
        {department.institution || "No institution set"} ·{" "}
        {roleLabel(department.role as never)}
      </p>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Lab card
// ---------------------------------------------------------------------------

function LabCard({
  lab,
  active,
  onSelect,
}: {
  lab: MyLab;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        "flex flex-col items-start gap-1.5 rounded-2xl border bg-surface px-5 py-4 text-left shadow-[var(--shadow)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "border-primary" : "border-border",
      )}
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="truncate font-serif text-[17px] font-semibold text-[var(--text-primary)]">
          {lab.name}
        </span>
        {active ? <Pill tone="primary">Active</Pill> : null}
      </div>
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--text-secondary)]">
        <Pill tone="neutral">{roleLabel(lab)}</Pill>
        {lab.department ? <span>{lab.department}</span> : null}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Lab detail — purpose & goals, invitations, members, projects
// ---------------------------------------------------------------------------

export function LabDetail({
  lab,
  onEditProfile,
}: {
  lab: MyLab;
  /** Opens the lab editor on its Purpose tab (managers only). */
  onEditProfile?: () => void;
}) {
  const { user } = usePortal();
  const canManage = canManageLab(lab);

  return (
    <div className="space-y-4">
      <LabPurposeCard lab={lab} canManage={canManage} onEdit={onEditProfile} />
      {canManage ? (
        <OrgInviteCard
          kind="lab"
          id={lab.slug}
          canInvite
          isVerified={user.isVerified}
        />
      ) : null}
      {canManage ? <DiscordSyncCard lab={lab} /> : null}
      <MembersCard lab={lab} />
      <ProjectsCard lab={lab} canManage={canManage} />
    </div>
  );
}

export function DetailCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {title}
      </h3>
      {children}
    </Card>
  );
}

// -- Purpose & goals ----------------------------------------------------------

/**
 * A read-only view of a lab's purpose & goals. Editing happens in
 * `LabEditorModal`, opened from the Edit button in the page header — the card
 * only offers `onEdit` as a shortcut into the same dialog, so there is exactly
 * one editing surface for a lab no matter which page you started from.
 */
export function LabPurposeCard({
  lab,
  canManage,
  onEdit,
}: {
  lab: MyLab;
  canManage: boolean;
  /** Opens the lab editor on its Purpose tab. Omitted → no inline affordance. */
  onEdit?: () => void;
}) {
  const { data: profile, isLoading } = useLabProfile(lab.slug);

  if (isLoading || !profile) {
    return (
      <DetailCard title="Purpose & goals">
        <div className="h-16 animate-pulse rounded-xl bg-surface-alt" />
      </DetailCard>
    );
  }

  const empty =
    !profile.statement &&
    profile.areas.length === 0 &&
    profile.funding_needs.length === 0 &&
    profile.strategic_needs.length === 0;

  const clusters = readClusters(profile.interests);
  const { groups: areaGroups, other: otherAreas } =
    clusters.length > 0
      ? groupByCluster(profile.areas, clusters, (area, cluster) =>
          cluster.areas.includes(area),
        )
      : { groups: [], other: [] };

  return (
    <DetailCard title="Purpose & goals">
      {empty ? (
        <p className="text-sm text-[var(--text-secondary)]">
          {canManage
            ? "Describe this lab's collective research purpose and focus areas."
            : "This lab hasn't described its purpose yet."}
        </p>
      ) : (
        <div className="space-y-3">
          {profile.statement ? (
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
              {profile.statement}
            </p>
          ) : null}
          {clusters.length > 0 ? (
            <div className="space-y-3">
              {areaGroups.map(({ cluster, items }) => (
                <div key={cluster.id}>
                  <ClusterGroupHeading cluster={cluster} />
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((item) => (
                      <Pill key={item} tone="neutral">
                        {item}
                      </Pill>
                    ))}
                  </div>
                </div>
              ))}
              <ChipRow label="Other" items={otherAreas} />
            </div>
          ) : (
            <ChipRow label="Focus areas" items={profile.areas} />
          )}
          <ChipRow label="Funding needs" items={profile.funding_needs} />
          <ChipRow label="Strategic needs" items={profile.strategic_needs} />
        </div>
      )}

      {canManage && onEdit ? (
        <button
          type="button"
          className="mt-4 rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onEdit}
        >
          {empty ? "Add purpose & goals" : "Edit"}
        </button>
      ) : null}
    </DetailCard>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <Pill key={item} tone="neutral">
            {item}
          </Pill>
        ))}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      {children}
    </label>
  );
}

// -- Discord ------------------------------------------------------------------

/**
 * Connect a lab's Discord server to Mylo.
 *
 * The install is **one step**. "Add Mylo to Discord" carries the lab through the OAuth
 * state, so the callback binds the guild to this lab on the way back — there is no code
 * to copy and no slash command to run. The one-time activation code exists only for the
 * other direction: somebody added Mylo from Discord's own menu, so the bot is sitting in
 * a guild that no lab claims (`pending_setup`), or it was removed and re-added
 * (`kicked`). Showing both buttons side by side made a one-step install look like a
 * two-step one, so the code path now appears only in the states that actually need it.
 *
 * The card still reads the lab's plan first: when Mylo genuinely is not available it
 * says so and points at billing rather than offering a button that cannot succeed.
 *
 * Titled "Connected services" to match the personal profile's card: a lab's outside
 * connections are the same kind of thing as a person's, and a manager moving between
 * the two surfaces should recognise it without re-reading.
 */
export function DiscordSyncCard({ lab }: { lab: MyLab }) {
  const { data: status, isLoading, isError } = useLabDiscordStatus(lab.slug);
  const { data: billing, isLoading: billingLoading } = useLabBilling(lab.slug);
  const connect = useConnectLabDiscord();
  const issueCode = useIssueLabActivationCode();

  const synced = Boolean(status?.synced);
  // Treat "still loading" as included so the card never flashes a false lock; the
  // buttons stay disabled while either read is in flight anyway.
  const myloIncluded = billingLoading || billing?.mylo_included !== false;
  // The manual code path is the fallback for a guild Mylo reached some other way,
  // not a second step of the normal install.
  const needsCode =
    status?.state === "pending_setup" || status?.state === "kicked";

  const badge = (() => {
    if (isLoading || billingLoading)
      return { tone: "neutral" as const, label: "Checking…" };
    if (isError) return { tone: "clay" as const, label: "Unknown" };
    if (synced) return { tone: "primary" as const, label: "Synced" };
    if (!myloIncluded) return { tone: "dashed" as const, label: "Not on plan" };
    if (status?.state === "pending_setup")
      return { tone: "review" as const, label: "Setup pending" };
    if (status?.state === "kicked")
      return { tone: "clay" as const, label: "Removed" };
    return { tone: "neutral" as const, label: "Not connected" };
  })();

  const detail = (() => {
    if (isLoading || billingLoading)
      return "Checking this lab's Discord connection…";
    if (isError) return "Couldn't check the Discord connection. Try again.";
    if (!myloIncluded && !synced)
      return "Mylo isn't part of this lab's plan yet, so this lab can't add him to a Discord server. Add Mylo to the plan from Account, then come back to connect your server.";
    if (synced) {
      const where = status?.guild_name
        ? `the ${status.guild_name} server`
        : "your Discord server";
      return `Mylo is synced to ${where}. Run /setup there to choose where reminders and updates post.`;
    }
    if (status?.state === "pending_setup")
      return "Mylo is in a server but no lab has claimed it yet. Re-add Mylo from here to link it automatically, or use a one-time code if you added Mylo from Discord.";
    if (status?.state === "kicked")
      return "Mylo was removed from the connected server. Add Mylo again from here and the lab reconnects itself.";
    return "Add Mylo to your Discord server. You'll pick the server in Discord, and this lab connects itself on the way back.";
  })();

  const connectError =
    connect.error instanceof ApiError && connect.error.status === 409
      ? "Link your own Discord first — the Connected services card on your profile — then try again."
      : connect.isError
        ? "Couldn't start adding Mylo. Try again."
        : null;

  return (
    <DetailCard title="Connected services">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
          <DiscordIcon size={16} className="text-[#5865F2]" />
          Mylo on Discord
        </span>
        <Pill tone={badge.tone}>{badge.label}</Pill>
      </div>
      <p className="mt-2 text-[12.5px] text-[var(--text-secondary)]">{detail}</p>
      {!synced && !isLoading && !billingLoading && !myloIncluded ? (
        <Link
          href={SECTION_ROUTES.account}
          className="mt-3 inline-flex items-center gap-[7px] rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Activate Mylo on this plan
        </Link>
      ) : null}
      {!synced && !isLoading && myloIncluded ? (
        <div className="mt-3 space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={DISCORD_BUTTON}
              onClick={() => connect.mutate(lab.slug)}
              disabled={connect.isPending}
            >
              <DiscordIcon size={16} />
              {connect.isPending
                ? "Opening Discord…"
                : status?.state === "pending_setup"
                  ? "Re-add Mylo to Discord"
                  : "Add Mylo to Discord"}
            </button>
            {needsCode ? (
              <button
                type="button"
                className={SECONDARY_BUTTON}
                onClick={() => issueCode.mutate(lab.slug)}
                disabled={issueCode.isPending}
              >
                {issueCode.isPending ? "Generating…" : "Use a code instead"}
              </button>
            ) : null}
          </div>
          {connectError ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {connectError}
            </p>
          ) : null}
          {issueCode.data ? (
            <div className="rounded-lg border border-border bg-surface-alt px-3 py-2">
              <p className="text-[12.5px] text-[var(--text-secondary)]">
                In your Discord server, run{" "}
                <code className="font-mono text-[var(--text-primary)]">
                  /activate-lab code:{issueCode.data.code}
                </code>{" "}
                within {Math.round(issueCode.data.expires_in / 60)} minutes. Shown
                once.
              </p>
            </div>
          ) : null}
          {issueCode.isError ? (
            <p className="text-[12.5px] text-clay" role="alert">
              Couldn&apos;t generate a lab code. Try again.
            </p>
          ) : null}
        </div>
      ) : null}
    </DetailCard>
  );
}

// -- Members ------------------------------------------------------------------

export function MembersCard({
  lab,
  grid = false,
}: {
  lab: MyLab;
  /** Render members as a responsive tile grid instead of full-width rows. */
  grid?: boolean;
}) {
  const { data: members, isLoading, isError } = useLabMembers(lab.slug);

  return (
    <DetailCard title="Members">
      {isLoading ? (
        <div className="h-12 animate-pulse rounded-xl bg-surface-alt" />
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load members.
        </p>
      ) : !members || members.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No members yet.</p>
      ) : grid ? (
        <div className="grid gap-2.5 sm:grid-cols-2">
          {members.map((member) => (
            <MemberTile key={member.username} member={member} />
          ))}
        </div>
      ) : (
        <div className="-mx-5 -mb-5 overflow-hidden rounded-b-2xl">
          {members.map((member) => (
            <MemberRow key={member.username} member={member} />
          ))}
        </div>
      )}
    </DetailCard>
  );
}

/** A compact member card for the Lab-settings members grid. */
function MemberTile({ member }: { member: LabMember }) {
  const roleDisplay = member.is_lead
    ? "PI"
    : member.role.charAt(0).toUpperCase() + member.role.slice(1);

  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-alt px-3.5 py-3">
      <Avatar initials={member.initials} seed={member.username} size={36} />
      <div className="min-w-0 flex-1">
        <p className="m-0 truncate text-sm font-medium text-[var(--text-primary)]">
          {member.name}
        </p>
        <p className="m-0 truncate text-xs text-[var(--text-secondary)]">
          {member.email}
        </p>
      </div>
      {member.is_lead ? (
        <Pill tone="primary">PI</Pill>
      ) : (
        <Pill tone="neutral">{roleDisplay}</Pill>
      )}
    </div>
  );
}

// -- Projects -----------------------------------------------------------------

export function ProjectsCard({
  lab,
  canManage,
}: {
  lab: MyLab;
  canManage: boolean;
}) {
  // Every lab member sees all of the lab's projects here so they can decide to
  // join — members are not auto-added to projects.
  const { data: projects, isLoading } = useLabProjects(lab.slug);
  const create = useCreateProject();
  const { join, leave } = useProjectMembership();
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = name.trim();
    if (!value) {
      return;
    }
    setError(null);
    create.mutate(
      { name: value, labSlug: lab.slug },
      {
        onSuccess: () => setName(""),
        onError: (e2) => setError((e2 as Error).message),
      },
    );
  };

  const busy = join.isPending || leave.isPending;

  return (
    <DetailCard title="Projects">
      {isLoading ? (
        <div className="h-10 animate-pulse rounded-xl bg-surface-alt" />
      ) : !projects || projects.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          No projects yet. Each project can represent a distinct focus area.
        </p>
      ) : (
        <ul className="space-y-2">
          {projects.map((project) => (
            <li
              key={project.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-alt px-3.5 py-2.5"
            >
              <span className="flex min-w-0 items-center gap-2 text-[13.5px] text-[var(--text-primary)]">
                <FolderIcon size={14} className="shrink-0 text-brand-secondary" />
                <span className="truncate font-medium">{project.name}</span>
                <span className="shrink-0 text-[12px] text-[var(--text-secondary)]">
                  {project.member_count} member
                  {project.member_count === 1 ? "" : "s"}
                </span>
              </span>
              {project.is_member ? (
                <button
                  type="button"
                  onClick={() => leave.mutate(project.id)}
                  disabled={busy}
                  className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                >
                  Leave
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => join.mutate(project.id)}
                  disabled={busy}
                  className={cn(PRIMARY_BUTTON, "shrink-0")}
                >
                  Join
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canManage ? (
        <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New project (focus area)"
            aria-label="New project name"
            className={cn(INPUT, "sm:flex-1")}
          />
          <button
            type="submit"
            className={PRIMARY_BUTTON}
            disabled={create.isPending || !name.trim()}
          >
            <PlusIcon size={15} />
            {create.isPending ? "Adding…" : "Add"}
          </button>
        </form>
      ) : null}
      {error ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </DetailCard>
  );
}

// ---------------------------------------------------------------------------
// Create lab modal
// ---------------------------------------------------------------------------

function CreateLabModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (slug: string) => void;
}) {
  const create = useCreateLab();
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    inputRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = name.trim();
    if (!value) {
      return;
    }
    setError(null);
    create.mutate(value, {
      onSuccess: (lab) => onCreated(lab.slug),
      onError: (e2) => setError((e2 as Error).message),
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--text-primary)_35%,transparent)] p-4"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-lab-title"
        className="w-full max-w-[420px] rounded-2xl border border-border bg-surface p-6 shadow-[var(--shadow)]"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2
          id="create-lab-title"
          className="font-serif text-[22px] font-semibold text-[var(--text-primary)]"
        >
          Create a lab
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          You become the lab&apos;s PI. You can invite members and set its
          purpose next.
        </p>

        <form className="mt-4" onSubmit={submit}>
          <Field label="Lab name">
            <input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Reyes Lab"
              className={INPUT}
            />
          </Field>

          {error ? (
            <p className="mt-2 text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}

          <div className="mt-5 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Cancel
            </button>
            <button
              type="submit"
              className={PRIMARY_BUTTON}
              disabled={create.isPending || !name.trim()}
            >
              {create.isPending ? "Creating…" : "Create lab"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create department modal
// ---------------------------------------------------------------------------

/**
 * Standing up a department after the fact.
 *
 * Sign-up used to ask this before anyone had seen the product, so it now lives
 * beside the lab it is a parent of. The head keeps their personal workspace;
 * the department arrives with its plan inactive, like a lab does.
 */
function CreateDepartmentModal({ onClose }: { onClose: () => void }) {
  const create = useCreateDepartment();
  const [name, setName] = React.useState("");
  const [institution, setInstitution] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    inputRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = name.trim();
    if (!value) {
      return;
    }
    setError(null);
    create.mutate(
      { name: value, institution: institution.trim() },
      {
        onSuccess: (department) => {
          window.location.href = `/app/department/${department.id}`;
        },
        onError: (e2) => setError((e2 as Error).message),
      },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--text-primary)_35%,transparent)] p-4"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-dept-title"
        className="w-full max-w-[420px] rounded-2xl border border-border bg-surface p-6 shadow-[var(--shadow)]"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2
          id="create-dept-title"
          className="font-serif text-[22px] font-semibold text-[var(--text-primary)]"
        >
          Create a department
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          You become its head. Labs can be attached to it, and its plan stays
          inactive until you turn it on.
        </p>

        <form className="mt-4 space-y-3" onSubmit={submit}>
          <Field label="Department name">
            <input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Molecular Systems"
              className={INPUT}
            />
          </Field>
          <Field label="Institution">
            <input
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              placeholder="Northgate University"
              className={INPUT}
            />
          </Field>

          {error ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Cancel
            </button>
            <button
              type="submit"
              className={PRIMARY_BUTTON}
              disabled={create.isPending || !name.trim()}
            >
              {create.isPending ? "Creating…" : "Create department"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
