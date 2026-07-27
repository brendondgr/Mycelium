"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { MembersIcon, PlusIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { useLabMembers } from "@/lib/portal/hooks";
import { MemberRow } from "@/components/portal/sections/member-row";

// ---------------------------------------------------------------------------
// Skeleton row — shown while members are loading
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div className="flex animate-pulse items-center gap-3.5 border-b border-[var(--divider)] px-5 py-3.5">
      <span className="h-9 w-9 shrink-0 rounded-full bg-surface-alt" />
      <div className="flex-1 space-y-1.5">
        <span className="block h-3 w-32 rounded bg-surface-alt" />
        <span className="block h-2.5 w-20 rounded bg-surface-alt" />
      </div>
      <span className="hidden h-2.5 w-28 rounded bg-surface-alt sm:block" />
      <span className="h-5 w-12 rounded-full bg-surface-alt" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// MembersSection
// ---------------------------------------------------------------------------

export function MembersSection() {
  const { currentLab, scopeLabel } = usePortal();
  const { data: members, isLoading, isError } = useLabMembers(
    currentLab?.slug,
  );

  // Subtitle varies: unscoped vs. loaded vs. loading
  const subtitle: React.ReactNode = (() => {
    if (!currentLab) {
      return `Across ${scopeLabel}.`;
    }
    if (!isLoading && members) {
      const n = members.length;
      return `${n} researcher${n === 1 ? "" : "s"} in ${currentLab.name}.`;
    }
    return `Members of ${currentLab.name}.`;
  })();

  // Disabled "Invite member" button (coming soon)
  const inviteButton = (
    <button
      type="button"
      disabled
      title="Inviting — coming soon"
      aria-disabled="true"
      className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-full border border-border bg-surface px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] opacity-60"
    >
      <PlusIcon size={14} aria-hidden="true" />
      Invite member
    </button>
  );

  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title="Members"
        subtitle={subtitle}
        action={inviteButton}
      />

      {/* All-labs scope — no roster to show */}
      {!currentLab ? (
        <EmptyState
          icon={<MembersIcon size={28} />}
          title="Pick a lab to see its members"
          description="Choose a lab from the workspace switcher to view its roster."
        />
      ) : isLoading ? (
        <Card className="overflow-hidden">
          {[1, 2, 3].map((i) => (
            <SkeletonRow key={i} />
          ))}
        </Card>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load members.
        </p>
      ) : !members || members.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No members yet.</p>
      ) : (
        <Card className="overflow-hidden">
          {members.map((member) => (
            <MemberRow key={member.username} member={member} />
          ))}
        </Card>
      )}
    </div>
  );
}
