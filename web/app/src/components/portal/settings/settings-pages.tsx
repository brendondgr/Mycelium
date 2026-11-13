"use client";

/**
 * What each Settings page holds. The cards are the ones the old settings
 * surfaces already had, moved onto their pages without being redesigned; the
 * page decides which of them the reader gets from `can(org, …)`, the same
 * capabilities the API checks.
 */

import * as React from "react";
import { FolderKanban } from "lucide-react";

import { MyloAndYouSection } from "@/components/portal/ambient/mylo-and-you-section";
import { CollaborationSettingsCard } from "@/components/portal/collab/collaboration-settings-card";
import { AgentPolicyCard } from "@/components/portal/mylo/settings-cards";
import { usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { EditIcon } from "@/components/portal/icons";
import { SlackLabCard, TeamsLabCard } from "@/components/portal/ambient/slack-cards";
import { AccountSection } from "@/components/portal/sections/account-section";
import { AnnouncementsCard } from "@/components/portal/sections/announcements-card";
import { LabPlanCards, PersonalSubscription } from "@/components/portal/sections/billing-section";
import { DeptLabsCard, DeptMembersCard } from "@/components/portal/sections/department-section";
import { DiscordHealthCard } from "@/components/portal/sections/discord-health-card";
import { DeptEditorModal, LabEditorModal } from "@/components/portal/sections/lab-editor-modal";
import {
  DeptDiscordCard,
  DiscordSyncCard,
  LabPurposeCard,
  ProfilePurposeCard,
  ProjectsCard,
} from "@/components/portal/sections/labs-section";
import { MemberRow } from "@/components/portal/sections/member-row";
import { OrgInviteCard } from "@/components/portal/sections/org-invite-card";
import { DeptPlanCard } from "@/components/portal/sections/org-plan-card";
import { DeliveryCards, ProfileSection } from "@/components/portal/sections/profile-section";
import { AppearanceCard } from "@/components/portal/settings/appearance-card";
import { LabLogoCard } from "@/components/portal/settings/lab-logo-card";
import { CAPABILITY, can } from "@/lib/portal/capabilities";
import { useDeptProfile, useLabMembers } from "@/lib/portal/hooks";
import type { OrgPageKey, YouPageKey } from "@/lib/portal/settings";
import type { MyDepartment, MyLab } from "@/lib/portal/types";

export const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/** One line under each page title: what the page is for. */
export const PAGE_DESCRIPTIONS: Record<string, string> = {
  "you:account": "Who you are on Mycelium, how we reach you, and your password.",
  "you:profile": "Your research focus, what Mylo watches for you, and your eligibility.",
  "you:mylo":
    "What Mylo noticed in your conversations, what changed, and what it knows. Nothing changes a recommendation until you say yes.",
  "you:collaboration": "Whether other researchers can find you, and who.",
  "you:delivery": "Where Mylo reaches you: Discord, Slack and Teams.",
  "you:appearance": "Theme, density and motion on this device.",
  "you:subscription": "The plans on your account and what each one unlocks.",
  "lab:general": "The lab's logo, purpose and focus — what Mylo ranks against for the lab.",
  "lab:people": "The lab's roster, roles and invitations.",
  "lab:projects": "The lab's projects and the rules for them.",
  "lab:servers": "The lab's Discord, Slack and Teams, and what Mylo may do there.",
  "lab:announcements": "Which opportunities Mylo announces to the lab, and where.",
  "lab:plan": "The lab's plan, what it covers, and what it costs.",
  "lab:membership": "Your place in the lab.",
  "lab:transfer": "Hand the lab to another member.",
  "department:general":
    "The department's purpose and focus — what Mylo ranks against for the department.",
  "department:labs": "The labs under the department.",
  "department:people": "The department's people, roles and invitations.",
  "department:projects": "The department's projects and the rules for them.",
  "department:servers": "The department's Discord server and what Mylo may do there.",
  "department:announcements": "Which opportunities Mylo announces to the department, and where.",
  "department:plan": "The department's plan, what it covers, and what it costs.",
  "department:membership": "Your place in the department.",
  "department:transfer": "Hand the department to another member.",
};

/* -------------------------------------------------------------------------- */
/* You                                                                         */
/* -------------------------------------------------------------------------- */

export function YouPage({ page }: { page: YouPageKey }) {
  switch (page) {
    case "account":
      return <AccountSection />;
    case "profile":
      return <ProfileSection />;
    case "mylo":
      return <MyloAndYouSection />;
    case "collaboration":
      return <CollaborationSettingsCard />;
    case "delivery":
      return <DeliveryCards />;
    case "appearance":
      return <AppearanceCard />;
    default:
      return <PersonalSubscription />;
  }
}

/* -------------------------------------------------------------------------- */
/* Shared                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * The page a companion change fills: the project rules (who may create, the
 * default visibility, what the department sees). Until then it says so plainly
 * rather than pretending to be empty.
 */
function ProjectRulesPlaceholder({ noun }: { noun: "lab" | "department" }) {
  return (
    <Card className="p-5" aria-labelledby={`${noun}-project-rules-title`}>
      <h2
        id={`${noun}-project-rules-title`}
        className="flex items-center gap-2 text-base font-semibold text-[var(--text-primary)]"
      >
        <FolderKanban size={16} aria-hidden="true" className="text-[var(--text-muted)]" />
        Project rules
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
        {noun === "lab"
          ? "Who may start a project in this lab, how visible a new project is, and what the department sees of the lab's projects will be set here. There is nothing to set yet."
          : "Who may start a project in this department and how visible a new project is will be set here. There is nothing to set yet."}
      </p>
    </Card>
  );
}

function EditProfileButton({ onClick }: { onClick: () => void }) {
  return (
    <div>
      <button type="button" className={PRIMARY_BUTTON} onClick={onClick}>
        <EditIcon size={14} />
        Edit profile
      </button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Lab                                                                         */
/* -------------------------------------------------------------------------- */

function LabGeneral({ lab }: { lab: MyLab }) {
  const [editing, setEditing] = React.useState(false);
  const canEdit = can(lab, CAPABILITY.PROFILE_EDIT);
  return (
    <>
      {canEdit ? <EditProfileButton onClick={() => setEditing(true)} /> : null}
      {canEdit ? <LabLogoCard lab={lab} /> : null}
      <LabPurposeCard lab={lab} canManage={canEdit} onEdit={() => setEditing(true)} />
      {editing ? (
        <LabEditorModal lab={lab} initialTab="purpose" onClose={() => setEditing(false)} />
      ) : null}
    </>
  );
}

function SkeletonRow() {
  return (
    <div className="flex animate-pulse items-center gap-3.5 border-b border-[var(--divider)] px-5 py-3.5">
      <span className="h-9 w-9 shrink-0 rounded-full bg-surface-alt" />
      <div className="flex-1 space-y-1.5">
        <span className="block h-3 w-32 rounded bg-surface-alt" />
        <span className="block h-2.5 w-20 rounded bg-surface-alt" />
      </div>
    </div>
  );
}

/** The lab's roster with the controls the server says the caller may use. */
export function LabRosterCard({ lab, manage }: { lab: MyLab; manage: boolean }) {
  const { user } = usePortal();
  const { data: members, isLoading, isError } = useLabMembers(lab.slug);
  return (
    <Card className="overflow-hidden" aria-label={`People in ${lab.name}`}>
      {isLoading ? (
        [1, 2, 3].map((i) => <SkeletonRow key={i} />)
      ) : isError ? (
        <p className="px-5 py-4 text-sm text-[var(--text-secondary)]">Couldn&apos;t load members.</p>
      ) : !members || members.length === 0 ? (
        <p className="px-5 py-4 text-sm text-[var(--text-secondary)]">No members yet.</p>
      ) : (
        members.map((member) => (
          <MemberRow
            key={member.username}
            member={member}
            lab={manage ? lab : undefined}
            viewer={user.username}
          />
        ))
      )}
    </Card>
  );
}

function LabPeople({ lab }: { lab: MyLab }) {
  const { user } = usePortal();
  return (
    <>
      {can(lab, CAPABILITY.INVITES_ISSUE) ? (
        <OrgInviteCard
          kind="lab"
          id={lab.slug}
          canInvite
          isVerified={user.isVerified}
          roles={lab.grantable_roles}
        />
      ) : null}
      <LabRosterCard lab={lab} manage />
    </>
  );
}

function LabServers({ lab }: { lab: MyLab }) {
  return (
    <>
      {can(lab, CAPABILITY.SERVERS_MANAGE) ? (
        <>
          <DiscordSyncCard lab={lab} />
          <DiscordHealthCard lab={lab} />
          <SlackLabCard slug={lab.slug} />
          <TeamsLabCard slug={lab.slug} />
        </>
      ) : null}
      {can(lab, CAPABILITY.MYLO_POLICY) ? (
        <AgentPolicyCard kind="lab" orgRef={lab.slug} name={lab.name} />
      ) : null}
    </>
  );
}

export function LabPage({ lab, page }: { lab: MyLab; page: OrgPageKey }) {
  switch (page) {
    case "general":
      return <LabGeneral lab={lab} />;
    case "people":
      return <LabPeople lab={lab} />;
    case "projects":
      return (
        <>
          <ProjectRulesPlaceholder noun="lab" />
          <ProjectsCard lab={lab} canManage={can(lab, CAPABILITY.PROFILE_EDIT)} />
        </>
      );
    case "servers":
      return <LabServers lab={lab} />;
    case "announcements":
      return <AnnouncementsCard target={{ lab: lab.slug }} name={lab.name} />;
    case "plan":
      return <LabPlanCards lab={lab} />;
    default:
      return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Department                                                                  */
/* -------------------------------------------------------------------------- */

function DeptGeneral({ dept }: { dept: MyDepartment }) {
  const [editing, setEditing] = React.useState(false);
  const canEdit = can(dept, CAPABILITY.PROFILE_EDIT);
  const { data, isLoading } = useDeptProfile(dept.id);
  return (
    <>
      {canEdit ? <EditProfileButton onClick={() => setEditing(true)} /> : null}
      <ProfilePurposeCard
        noun="department"
        profile={data}
        isLoading={isLoading}
        canManage={canEdit}
        onEdit={() => setEditing(true)}
      />
      {editing ? (
        <DeptEditorModal deptId={dept.id} name={dept.name} onClose={() => setEditing(false)} />
      ) : null}
    </>
  );
}

function DeptPeople({ dept }: { dept: MyDepartment }) {
  const { user } = usePortal();
  return (
    <>
      {can(dept, CAPABILITY.INVITES_ISSUE) ? (
        <OrgInviteCard
          kind="department"
          id={dept.id}
          canInvite
          isVerified={user.isVerified}
          roles={dept.grantable_roles}
        />
      ) : null}
      <DeptMembersCard
        deptId={dept.id}
        canManage={can(dept, CAPABILITY.PEOPLE_MANAGE)}
        mine={dept}
        viewer={user.username}
        title="People"
      />
    </>
  );
}

export function DeptPage({ dept, page }: { dept: MyDepartment; page: OrgPageKey }) {
  switch (page) {
    case "general":
      return <DeptGeneral dept={dept} />;
    case "labs":
      return (
        <DeptLabsCard
          deptId={dept.id}
          canManage={can(dept, CAPABILITY.PEOPLE_MANAGE)}
          canBill={can(dept, CAPABILITY.BILLING_MANAGE)}
        />
      );
    case "people":
      return <DeptPeople dept={dept} />;
    case "projects":
      return <ProjectRulesPlaceholder noun="department" />;
    case "servers":
      return (
        <>
          {can(dept, CAPABILITY.SERVERS_MANAGE) ? <DeptDiscordCard deptId={dept.id} /> : null}
          {can(dept, CAPABILITY.MYLO_POLICY) ? (
            <AgentPolicyCard kind="department" orgRef={dept.id} name={dept.name} />
          ) : null}
        </>
      );
    case "announcements":
      return <AnnouncementsCard target={{ department: dept.id }} name={dept.name} />;
    case "plan":
      return <DeptPlanCard deptId={dept.id} />;
    default:
      return null;
  }
}
