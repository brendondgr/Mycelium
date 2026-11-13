"use client";

import * as React from "react";
import Link from "next/link";

import { useAppHref } from "@/components/demo/demo-context";
import { MembersIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { DeptLabsCard, DeptMembersCard } from "@/components/portal/sections/department-section";
import { LabRosterCard } from "@/components/portal/settings/settings-pages";
import { CAPABILITY, can } from "@/lib/portal/capabilities";
import { settingsPath } from "@/lib/portal/settings";

/**
 * The workspace's Members page: a directory, not a management surface.
 *
 * In a lab it lists the lab's people. In a department it is one page with two
 * groups — the department's labs, then its people — where it used to be two
 * entries (Labs and Members), one of which told a department reader to "pick a
 * lab". Roles, invitations and removals happen in Settings → People; anyone
 * who may manage people gets a link there.
 */
export function MembersSection() {
  const { currentLab, currentDepartment, user, workspacesLoading } = usePortal();
  const appHref = useAppHref();

  const manageHref = currentLab
    ? can(currentLab, CAPABILITY.PEOPLE_MANAGE)
      ? settingsPath({ kind: "lab", slug: currentLab.slug }, "people")
      : null
    : currentDepartment && can(currentDepartment, CAPABILITY.PEOPLE_MANAGE)
      ? settingsPath({ kind: "department", id: currentDepartment.id }, "people")
      : null;

  const manage = manageHref ? (
    <Link
      href={appHref(manageHref)}
      className="inline-flex items-center rounded-full border border-border bg-surface px-4 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      Manage people
    </Link>
  ) : null;

  if (currentDepartment) {
    return (
      <div>
        <SectionHeader
          eyebrow="Workspace"
          title="Members"
          subtitle={`The labs and people of ${currentDepartment.name}.`}
          action={manage}
        />
        <div className="grid grid-cols-1 gap-4">
          <DeptLabsCard deptId={currentDepartment.id} canManage={false} />
          <DeptMembersCard
            deptId={currentDepartment.id}
            canManage={false}
            mine={null}
            viewer={user.username}
            title="People"
          />
        </div>
      </div>
    );
  }

  if (currentLab) {
    return (
      <div>
        <SectionHeader
          eyebrow="Workspace"
          title="Members"
          subtitle={`The people of ${currentLab.name}.`}
          action={manage}
        />
        <LabRosterCard lab={currentLab} manage={false} />
      </div>
    );
  }

  if (workspacesLoading) {
    return (
      <div aria-busy="true">
        <SectionHeader eyebrow="Workspace" title="Members" />
        <div className="h-40 animate-pulse rounded-2xl bg-surface-alt" />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader eyebrow="Workspace" title="Members" />
      <EmptyState
        icon={<MembersIcon size={28} />}
        title="Your personal workspace has no members"
        description="Switch to a lab or a department to see who is in it."
      />
    </div>
  );
}
