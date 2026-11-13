"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { CloseIcon, PlusIcon } from "@/components/portal/icons";
import {
  useCancelProjectInvitation,
  useInviteToProject,
  useJoinRequests,
  useLabMembers,
  useProjectInvitations,
  useProjectJoinRequests,
  useProjectMembership,
} from "@/lib/portal/hooks";
import type { LabMember, Project, ProjectMember } from "@/lib/portal/types";

const INPUT =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const GHOST =
  "rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

const PRIMARY =
  "rounded-full bg-primary px-3.5 py-1.5 text-[12.5px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/**
 * The project's team: who is on it, plus the two ways someone joins.
 *
 * A lab project's owner/admin/PI **adds** one of the lab's own members straight
 * on — that person can already see the lab's work, so an invitation would only
 * be ceremony. Anyone else (an outside collaborator, or anyone on a personal
 * project) is **invited** by username or email and joins when they accept.
 * Accepting grants that one project and never lab membership, which the panel
 * says out loud so nobody invites an outsider expecting less — or more. Only
 * the owner invites from outside the lab; such a person is marked "outside the
 * lab" on the roster.
 *
 * The third way in is a **request**: someone inside the project's scope asks,
 * and the owner or an editor approves or refuses here. A refusal is told to
 * the requester alone.
 */
export function ProjectTeamCard({ project }: { project: Project }) {
  const canManage = project.can_manage_members;
  const [mode, setMode] = React.useState<"add" | "invite" | null>(null);

  return (
    <Card className="p-[22px]">
      <div className="mb-[14px] flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
          Team
        </h2>
        <span className="text-xs text-[var(--text-secondary)]">
          {project.member_count} member{project.member_count === 1 ? "" : "s"}
        </span>
      </div>

      {project.members.length === 0 ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          {canManage
            ? "Nobody is on this project yet."
            : "No members yet."}
        </p>
      ) : (
        <ul className="flex flex-col gap-[11px]">
          {project.members.map((member) => (
            <MemberRow
              key={member.username}
              member={member}
              project={project}
              canManage={canManage}
            />
          ))}
        </ul>
      )}

      {canManage ? (
        <div className="mt-4 border-t border-[var(--divider)] pt-4">
          <div className="flex flex-wrap gap-2">
            {project.scope === "lab" ? (
              <button
                type="button"
                onClick={() => setMode(mode === "add" ? null : "add")}
                aria-expanded={mode === "add"}
                className={GHOST}
              >
                <span className="inline-flex items-center gap-1.5">
                  <PlusIcon size={13} aria-hidden="true" />
                  Add from lab
                </span>
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setMode(mode === "invite" ? null : "invite")}
              aria-expanded={mode === "invite"}
              className={GHOST}
            >
              Invite someone
            </button>
          </div>

          {mode === "add" && project.scope_slug ? (
            <AddFromLab
              project={project}
              labSlug={project.scope_slug}
              onDone={() => setMode(null)}
            />
          ) : null}
          {mode === "invite" ? (
            <InviteForm project={project} onDone={() => setMode(null)} />
          ) : null}

          <JoinRequests project={project} />
          <PendingInvitations project={project} />
        </div>
      ) : null}

      {project.can_request ? <AskToJoin project={project} /> : null}
    </Card>
  );
}

function MemberRow({
  member,
  project,
  canManage,
}: {
  member: ProjectMember;
  project: Project;
  canManage: boolean;
}) {
  const projectId = project.id;
  const { removeMember, setRole } = useProjectMembership();
  const [error, setError] = React.useState<string | null>(null);
  // The owner stays: a personal project's own user, or the owner-role member.
  const isOwner = project.scope === "user" || member.role === "owner";
  const canSetRole =
    project.can_change_visibility &&
    (member.role === "editor" || member.role === "member");

  return (
    <li className="flex items-center gap-[11px]">
      <Avatar initials={member.initials} seed={member.username} size={32} />
      <div className="min-w-0 flex-1">
        <p className="m-0 truncate text-[13px] font-medium text-[var(--text-primary)]">
          {member.name}
        </p>
        <p className="m-0 flex flex-wrap items-center gap-1.5 truncate text-[11.5px] text-[var(--text-secondary)]">
          @{member.username}
          {member.role === "owner" ? <Pill tone="primary">Owner</Pill> : null}
          {member.role === "editor" ? <Pill tone="dashed">Editor</Pill> : null}
          {member.outside ? (
            <Pill tone="clay">
              Outside the {project.scope === "department" ? "department" : "lab"}
            </Pill>
          ) : null}
        </p>
        {error ? (
          <p className="m-0 text-[11px] text-clay" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      {canSetRole ? (
        <button
          type="button"
          onClick={() => {
            setError(null);
            setRole.mutate(
              {
                id: projectId,
                username: member.username,
                role: member.role === "editor" ? "member" : "editor",
              },
              { onError: (e) => setError((e as Error).message) },
            );
          }}
          disabled={setRole.isPending}
          className={GHOST}
          title={
            member.role === "editor"
              ? "Editors invite, remove, edit and archive."
              : "Let them invite, remove, edit and archive."
          }
        >
          {member.role === "editor" ? "Make member" : "Make editor"}
        </button>
      ) : null}
      {canManage && !isOwner ? (
        <button
          type="button"
          onClick={() => {
            setError(null);
            removeMember.mutate(
              { id: projectId, username: member.username },
              { onError: (e) => setError((e as Error).message) },
            );
          }}
          disabled={removeMember.isPending}
          aria-label={`Remove ${member.name} from this project`}
          title="Remove from project"
          className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-clay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <CloseIcon size={12} />
        </button>
      ) : null}
    </li>
  );
}

/** The lab-project direct-add: pick a lab member, they are on immediately. */
function AddFromLab({
  project,
  labSlug,
  onDone,
}: {
  project: Project;
  labSlug: string;
  onDone: () => void;
}) {
  const { data, isLoading, isError } = useLabMembers(labSlug);
  const { addMember } = useProjectMembership();
  const [error, setError] = React.useState<string | null>(null);

  const onProject = new Set(project.members.map((m) => m.username));
  const candidates: LabMember[] = (data ?? []).filter(
    (m) => !onProject.has(m.username),
  );

  return (
    <div className="mt-3 rounded-xl border border-border bg-surface-alt p-3">
      <p className="mb-2 text-[11.5px] text-[var(--text-secondary)]">
        Members of {project.scope_name} join straight away — no invitation
        needed.
      </p>
      {isLoading ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Loading the lab roster…
        </p>
      ) : isError ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Couldn&apos;t load the lab roster.
        </p>
      ) : candidates.length === 0 ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Everyone in this lab is already on the project. Invite someone outside
          it instead.
        </p>
      ) : (
        <ul className="flex max-h-[220px] flex-col gap-1.5 overflow-y-auto">
          {candidates.map((member) => (
            <li key={member.username}>
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  addMember.mutate(
                    { id: project.id, username: member.username },
                    {
                      onSuccess: onDone,
                      onError: (e) => setError((e as Error).message),
                    },
                  );
                }}
                disabled={addMember.isPending}
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              >
                <Avatar initials={member.initials} seed={member.username} size={24} />
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--text-primary)]">
                  {member.name}
                </span>
                <PlusIcon size={13} aria-hidden="true" className="text-primary" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Invite by username or email — the path for anyone who has to accept first. */
function InviteForm({
  project,
  onDone,
}: {
  project: Project;
  onDone: () => void;
}) {
  const invite = useInviteToProject(project.id);
  const [identifier, setIdentifier] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [sentTo, setSentTo] = React.useState<string | null>(null);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const value = identifier.trim();
    if (!value || invite.isPending) {
      return;
    }
    setError(null);
    invite.mutate(
      { identifier: value, message: message.trim() || undefined },
      {
        onSuccess: (invitation) => {
          setSentTo(invitation.invitee.name);
          setIdentifier("");
          setMessage("");
        },
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  return (
    <form
      onSubmit={submit}
      className="mt-3 rounded-xl border border-border bg-surface-alt p-3"
    >
      <p className="mb-2 text-[11.5px] text-[var(--text-secondary)]">
        {project.scope === "user"
          ? "They join this project only. Invitations go to people who already have a Mycelium account."
          : project.can_invite_outside
            ? `They join this project only. Someone outside the ${project.scope} is shown as "outside the ${project.scope}" and gets no other part of it — no feeds, roster, directory or server role.`
            : `You can invite people already in the ${project.scope}. Only the project's owner invites someone from outside it.`}
      </p>
      <input
        value={identifier}
        onChange={(e) => setIdentifier(e.target.value)}
        placeholder="Username or email"
        aria-label="Username or email"
        className={INPUT}
      />
      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Add a note (optional)"
        aria-label="Invitation note"
        className={`${INPUT} mt-2`}
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="submit"
          disabled={invite.isPending || identifier.trim() === ""}
          className={PRIMARY}
        >
          {invite.isPending ? "Sending…" : "Send invitation"}
        </button>
        <button type="button" onClick={onDone} className={GHOST}>
          Done
        </button>
      </div>
      {sentTo ? (
        <p className="mt-2 text-[11.5px] text-primary">
          Invitation sent to {sentTo}. They&apos;ll see it in their
          notifications.
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

/** The outstanding invitations an editor can still withdraw. */
function PendingInvitations({ project }: { project: Project }) {
  const { data } = useProjectInvitations(project.id);
  const cancel = useCancelProjectInvitation(project.id);
  const [error, setError] = React.useState<string | null>(null);
  const pending = data?.items ?? [];

  if (pending.length === 0) {
    return null;
  }

  return (
    <div className="mt-4">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Invited
      </p>
      <ul className="flex flex-col gap-2">
        {pending.map((invitation) => (
          <li key={invitation.id} className="flex items-center gap-2.5">
            <Avatar
              initials={invitation.invitee.initials}
              seed={invitation.invitee.username}
              size={24}
            />
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-[var(--text-primary)]">
              {invitation.invitee.name}
            </span>
            <Pill tone="dashed">Pending</Pill>
            <button
              type="button"
              onClick={() => {
                setError(null);
                cancel.mutate(invitation.id, {
                  onError: (e) => setError((e as Error).message),
                });
              }}
              disabled={cancel.isPending}
              aria-label={`Withdraw the invitation to ${invitation.invitee.name}`}
              title="Withdraw invitation"
              className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-clay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              <CloseIcon size={12} />
            </button>
          </li>
        ))}
      </ul>
      {error ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Requests to join, for the owner and editors to approve or refuse. A refusal
 * is told to the requester alone — never announced to the lab.
 */
function JoinRequests({ project }: { project: Project }) {
  const { data } = useProjectJoinRequests(project.id, project.can_manage_members);
  const { decide } = useJoinRequests();
  const [error, setError] = React.useState<string | null>(null);
  const pending = data?.items ?? [];

  if (pending.length === 0) {
    return null;
  }

  const answer = (requestId: string, action: "approve" | "refuse") => {
    setError(null);
    decide.mutate(
      { projectId: project.id, requestId, action },
      { onError: (e) => setError((e as Error).message) },
    );
  };

  return (
    <div className="mt-4">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Asking to join
      </p>
      <ul className="flex flex-col gap-2.5">
        {pending.map((request) => (
          <li key={request.id} className="flex flex-wrap items-center gap-2.5">
            <Avatar
              initials={request.user.initials}
              seed={request.user.username}
              size={24}
            />
            <div className="min-w-0 flex-1">
              <p className="m-0 truncate text-[12.5px] text-[var(--text-primary)]">
                {request.user.name}
              </p>
              {request.note ? (
                <p className="m-0 text-[11.5px] text-[var(--text-secondary)]">
                  &ldquo;{request.note}&rdquo;
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => answer(request.id, "approve")}
              disabled={decide.isPending}
              className={PRIMARY}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => answer(request.id, "refuse")}
              disabled={decide.isPending}
              className={GHOST}
            >
              Decline
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
        Declining tells only the person who asked.
      </p>
      {error ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** For someone who can open the project without being on it (the lab's PI,
 * a department head): ask to join. */
function AskToJoin({ project }: { project: Project }) {
  const { request } = useJoinRequests();
  const [error, setError] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState(false);

  return (
    <div className="mt-4 border-t border-[var(--divider)] pt-4">
      {sent ? (
        <p className="text-[12px] text-primary">
          Asked. The owner or an editor will decide.
        </p>
      ) : (
        <button
          type="button"
          onClick={() => {
            setError(null);
            request.mutate(
              { id: project.id },
              {
                onSuccess: () => setSent(true),
                onError: (e) => setError((e as Error).message),
              },
            );
          }}
          disabled={request.isPending}
          className={GHOST}
        >
          {request.isPending ? "Asking…" : "Ask to join"}
        </button>
      )}
      {error ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
