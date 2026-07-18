"use client";

import * as React from "react";

import { ClusterOrganizer } from "@/components/onboarding/cluster-organizer";
import {
  DiscordIcon,
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
import { MemberRow } from "@/components/portal/sections/member-row";
import {
  useConnectLabDiscord,
  useCreateLab,
  useCreateProject,
  useInviteToLab,
  useIssueLabActivationCode,
  useLabDiscordStatus,
  useLabMembers,
  useLabProfile,
  useLabProjects,
  useLabWatch,
  useProjectMembership,
  useUpdateLabProfile,
} from "@/lib/portal/hooks";
import { ApiError } from "@/lib/api-error";
import type { ClusterGroup } from "@/lib/auth-types";
import type { LabMember, LabProfileData, MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Split a comma-separated field into a trimmed, non-empty list. */
function parseList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

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
  const { labs, labsLoading, labScope, setLabScope, currentLab } = usePortal();
  const [showCreate, setShowCreate] = React.useState(false);

  const createAction = (
    <button
      type="button"
      className={PRIMARY_BUTTON}
      onClick={() => setShowCreate(true)}
    >
      <PlusIcon size={15} />
      Create lab
    </button>
  );

  // When a lab is the active workspace, this page is that lab's management —
  // no list of other labs (switch labs from the workspace switcher instead).
  if (currentLab) {
    return (
      <div>
        <SectionHeader
          title={`Manage ${currentLab.name}`}
          subtitle="Switch labs from the workspace switcher in the top bar."
          action={createAction}
        />
        <LabDetail lab={currentLab} />

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
        title="Labs"
        subtitle="Your research labs. Select one to make it the active workspace and manage it."
        action={createAction}
      />

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

          <p className="mt-6 text-sm text-[var(--text-muted)]">
            Select a lab to make it your active workspace, then manage it here.
          </p>
        </>
      )}

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
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--text-muted)]">
        <Pill tone="neutral">{roleLabel(lab)}</Pill>
        {lab.department ? <span>{lab.department}</span> : null}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Lab detail — purpose & goals, invitations, members, projects
// ---------------------------------------------------------------------------

export function LabDetail({ lab }: { lab: MyLab }) {
  const canManage = canManageLab(lab);

  return (
    <div className="space-y-4">
      <LabPurposeCard lab={lab} canManage={canManage} />
      {canManage ? <InviteCard lab={lab} /> : null}
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
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
        {title}
      </h3>
      {children}
    </Card>
  );
}

// -- Purpose & goals ----------------------------------------------------------

export function LabPurposeCard({
  lab,
  canManage,
}: {
  lab: MyLab;
  canManage: boolean;
}) {
  const { data: profile, isLoading } = useLabProfile(lab.slug);
  const update = useUpdateLabProfile(lab.slug);
  const [editing, setEditing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  if (isLoading || !profile) {
    return (
      <DetailCard title="Purpose & goals">
        <div className="h-16 animate-pulse rounded-xl bg-surface-alt" />
      </DetailCard>
    );
  }

  if (editing) {
    return (
      <DetailCard title="Purpose & goals">
        <LabPurposeForm
          profile={profile}
          saving={update.isPending}
          error={error}
          onCancel={() => {
            setError(null);
            setEditing(false);
          }}
          onSave={(payload) => {
            setError(null);
            update.mutate(payload, {
              onSuccess: () => setEditing(false),
              onError: (e) => setError((e as Error).message),
            });
          }}
        />
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
        <p className="text-sm text-[var(--text-muted)]">
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

      {canManage ? (
        <button
          type="button"
          className="mt-4 rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setEditing(true)}
        >
          {empty ? "Add purpose & goals" : "Edit"}
        </button>
      ) : null}
    </DetailCard>
  );
}

// -- What Mylo watches (read card) -------------------------------------------

/** A read-only view of a lab's watch topics, grouped by cluster when the lab
 * profile has any (same treatment as the personal profile's WatchCard). */
export function LabWatchCard({ lab }: { lab: MyLab }) {
  const { data: watch, isLoading, isError } = useLabWatch(lab.slug);
  const { data: profile } = useLabProfile(lab.slug);

  if (isLoading) {
    return (
      <DetailCard title="What Mylo watches">
        <div className="h-16 animate-pulse rounded-xl bg-surface-alt" />
      </DetailCard>
    );
  }

  if (isError || !watch) {
    return (
      <DetailCard title="What Mylo watches">
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t load the lab&apos;s watch settings.
        </p>
      </DetailCard>
    );
  }

  const topics = watch.topics ?? [];
  const clusters = readClusters(profile?.interests);
  const cadenceLabel = watch.cadence === "daily" ? "daily" : "weekly";

  if (topics.length === 0) {
    return (
      <DetailCard title="What Mylo watches">
        <p className="text-sm text-[var(--text-muted)]">
          This lab hasn&apos;t set watch topics yet.
        </p>
      </DetailCard>
    );
  }

  const { groups: topicGroups, other: otherTopics } =
    clusters.length > 0
      ? groupByCluster(topics, clusters, (topic, cluster) => {
          const key = topic.toLowerCase();
          return (
            cluster.label.toLowerCase() === key ||
            cluster.areas.some((area) => area.toLowerCase() === key)
          );
        })
      : { groups: [], other: [] };

  return (
    <DetailCard title="What Mylo watches">
      {clusters.length > 0 ? (
        <div className="mb-3 flex flex-col gap-3">
          {topicGroups.map(({ cluster, items }) => (
            <div key={cluster.id}>
              <ClusterGroupHeading cluster={cluster} />
              <div className="flex flex-wrap gap-1.5">
                {items.map((topic) => (
                  <Pill key={topic} tone="neutral">
                    {topic}
                  </Pill>
                ))}
              </div>
            </div>
          ))}
          {otherTopics.length > 0 ? (
            <ChipRow label="Other" items={otherTopics} />
          ) : null}
        </div>
      ) : (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {topics.map((topic) => (
            <Pill key={topic} tone="neutral">
              {topic}
            </Pill>
          ))}
        </div>
      )}

      {watch.categories?.length ? (
        <p className="mb-1.5 text-[12.5px] text-[var(--text-secondary)]">
          Signals:{" "}
          <span className="font-medium">{watch.categories.join(", ")}</span>
        </p>
      ) : null}

      <p className="text-[12.5px] text-[var(--text-secondary)]">
        Cadence: <span className="font-medium">{cadenceLabel} digest</span>
      </p>
    </DetailCard>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
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

function LabPurposeForm({
  profile,
  saving,
  error,
  onSave,
  onCancel,
}: {
  profile: LabProfileData;
  saving: boolean;
  error: string | null;
  onSave: (payload: {
    statement: string;
    areas: string[];
    funding_needs: string[];
    strategic_needs: string[];
    interests?: Record<string, unknown>;
  }) => void;
  onCancel: () => void;
}) {
  const [statement, setStatement] = React.useState(profile.statement);
  const [areas, setAreas] = React.useState(profile.areas.join(", "));
  const [funding, setFunding] = React.useState(profile.funding_needs.join(", "));
  const [strategic, setStrategic] = React.useState(
    profile.strategic_needs.join(", "),
  );
  const [clusters, setClusters] = React.useState<ClusterGroup[]>(() =>
    readClusters(profile.interests),
  );

  const parsedAreas = parseList(areas);

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const cleanAreas = parseList(areas);
        // Same partial-partition guard as onboarding's organize step: sanitize the
        // clusters against the current areas (drop phantom/duplicate areas the user
        // may have introduced by editing the comma list after organizing), then
        // attach only when they cover every area — else omit the key so a stale or
        // partial grouping never overwrites a valid saved one or 400s on save.
        const validAreas = new Set(cleanAreas);
        const claimed = new Set<string>();
        const cleanedClusters = clusters
          .map((cluster) => ({
            ...cluster,
            areas: cluster.areas.filter((area) => {
              if (!validAreas.has(area) || claimed.has(area)) return false;
              claimed.add(area);
              return true;
            }),
          }))
          .filter((cluster) => cluster.areas.length > 0);
        const allAssigned =
          cleanedClusters.length > 0 && cleanAreas.every((area) => claimed.has(area));
        const nextInterests: Record<string, unknown> = {
          ...(profile.interests ?? {}),
          version: 2,
          areas: cleanAreas,
        };
        if (allAssigned) {
          nextInterests.clusters = cleanedClusters;
        } else {
          delete nextInterests.clusters;
        }
        onSave({
          statement: statement.trim(),
          areas: cleanAreas,
          funding_needs: parseList(funding),
          strategic_needs: parseList(strategic),
          interests: nextInterests,
        });
      }}
    >
      <Field label="Statement">
        <textarea
          value={statement}
          onChange={(e) => setStatement(e.target.value)}
          rows={3}
          placeholder="The lab's shared research purpose."
          className={cn(INPUT, "resize-y")}
        />
      </Field>
      <Field label="Focus areas (comma-separated)">
        <input
          value={areas}
          onChange={(e) => setAreas(e.target.value)}
          placeholder="Oceanography, Healthcare ML"
          className={INPUT}
        />
      </Field>
      <ClusterOrganizer
        areas={parsedAreas}
        clusters={clusters}
        statement={statement}
        onChange={setClusters}
      />
      <Field label="Funding needs (comma-separated)">
        <input
          value={funding}
          onChange={(e) => setFunding(e.target.value)}
          placeholder="NSF, NIH R01"
          className={INPUT}
        />
      </Field>
      <Field label="Strategic needs (comma-separated)">
        <input
          value={strategic}
          onChange={(e) => setStrategic(e.target.value)}
          placeholder="New postdoc, GPU cluster"
          className={INPUT}
        />
      </Field>

      {error ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}

      <div className="flex items-center gap-2">
        <button type="submit" className={PRIMARY_BUTTON} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Cancel
        </button>
      </div>
    </form>
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

// -- Invite -------------------------------------------------------------------

export function InviteCard({ lab }: { lab: MyLab }) {
  const invite = useInviteToLab(lab.slug);
  const [identifier, setIdentifier] = React.useState("");
  const [role, setRole] = React.useState("member");
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = identifier.trim();
    if (!value) {
      return;
    }
    setMessage(null);
    setError(null);
    invite.mutate(
      { identifier: value, role },
      {
        onSuccess: () => {
          setMessage(`Invitation sent to ${value}.`);
          setIdentifier("");
        },
        onError: (e2) => setError((e2 as Error).message),
      },
    );
  };

  return (
    <DetailCard title="Invite members">
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="Email or username"
          aria-label="Invite by email or username"
          className={cn(INPUT, "sm:flex-1")}
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Role"
          className="rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="member">Member</option>
          <option value="admin">Admin</option>
          <option value="viewer">Viewer</option>
        </select>
        <button
          type="submit"
          className={PRIMARY_BUTTON}
          disabled={invite.isPending || !identifier.trim()}
        >
          {invite.isPending ? "Sending…" : "Invite"}
        </button>
      </form>
      <p className="mt-2 text-[12px] text-[var(--text-muted)]">
        People with an account are notified in-app. An email with no account yet
        is invited when they sign up.
      </p>
      {message ? (
        <p className="mt-2 text-[12.5px] text-primary">{message}</p>
      ) : null}
      {error ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </DetailCard>
  );
}

// -- Discord ------------------------------------------------------------------

export function DiscordSyncCard({ lab }: { lab: MyLab }) {
  const { data: status, isLoading, isError } = useLabDiscordStatus(lab.slug);
  const connect = useConnectLabDiscord();
  const issueCode = useIssueLabActivationCode();

  const synced = Boolean(status?.synced);

  const badge = (() => {
    if (isLoading) return { tone: "neutral" as const, label: "Checking…" };
    if (isError) return { tone: "clay" as const, label: "Unknown" };
    if (synced) return { tone: "primary" as const, label: "Synced" };
    if (status?.state === "pending_setup")
      return { tone: "review" as const, label: "Setup pending" };
    if (status?.state === "kicked")
      return { tone: "clay" as const, label: "Removed" };
    return { tone: "neutral" as const, label: "Not connected" };
  })();

  const detail = (() => {
    if (isLoading) return "Checking this lab's Discord connection…";
    if (isError) return "Couldn't check the Discord connection. Try again.";
    if (synced) {
      const where = status?.guild_name
        ? `the ${status.guild_name} server`
        : "your Discord server";
      return `Mylo is synced to ${where}. Run /setup there to choose where reminders and updates post.`;
    }
    if (status?.state === "pending_setup")
      return "Mylo is in a server but not linked to this lab yet. Click Activate Lab for a code, then run /activate-lab code:<code> in that server.";
    if (status?.state === "kicked")
      return "Mylo was removed from the connected server. Add it again, then click Activate Lab and run /activate-lab in your server.";
    return "Connect this lab to a Discord server in two steps: add Mylo, then activate the lab with a one-time code.";
  })();

  const connectError =
    connect.error instanceof ApiError && connect.error.status === 409
      ? "Link your own Discord first — the Connected services card on your profile — then try again."
      : connect.isError
        ? "Couldn't start adding Mylo. Try again."
        : null;

  return (
    <DetailCard title="Discord">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
          <DiscordIcon size={16} className="text-[#5865F2]" />
          Mylo on Discord
        </span>
        <Pill tone={badge.tone}>{badge.label}</Pill>
      </div>
      <p className="mt-2 text-[12.5px] text-[var(--text-muted)]">{detail}</p>
      {!synced && !isLoading ? (
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
            <button
              type="button"
              className={SECONDARY_BUTTON}
              onClick={() => issueCode.mutate(lab.slug)}
              disabled={issueCode.isPending}
            >
              {issueCode.isPending ? "Generating…" : "Activate Lab"}
            </button>
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
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t load members.
        </p>
      ) : !members || members.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No members yet.</p>
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
        <p className="m-0 truncate text-xs text-[var(--text-muted)]">
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
        <p className="text-sm text-[var(--text-muted)]">
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
                <span className="shrink-0 text-[12px] text-[var(--text-muted)]">
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
