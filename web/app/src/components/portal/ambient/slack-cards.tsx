"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  useSlackLabCode,
  useSlackLabSwitches,
  useSlackLinkCode,
  useSlackStatus,
  useSlackUnlink,
  useTeamsLabCode,
  useTeamsLabSwitches,
  useTeamsLinkCode,
  useTeamsStatus,
} from "@/lib/portal/ambient/slack";

/**
 * Slack, beside Discord (ambient Plan 11). Nothing renders while the
 * deployment has Slack off. A person links by DMing Mylo a code; a lab
 * manager links the lab's workspace by mentioning Mylo with a lab code in the
 * channel that should get the lab's posts.
 */
export function SlackPersonCard() {
  const status = useSlackStatus();
  const code = useSlackLinkCode();
  const unlink = useSlackUnlink();
  if (!status.data?.enabled) return null;
  const identities = status.data.identities;
  return (
    <Card className="p-[22px]" data-ambient="slack-person">
      <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">Slack</h2>
      {identities.length ? (
        <ul className="mb-3 space-y-1.5 text-sm text-[var(--text-secondary)]">
          {identities.map((identity) => (
            <li key={identity.team_id} className="flex items-center justify-between gap-2">
              <span>Linked in {identity.team || identity.team_id}</span>
              <button
                type="button"
                onClick={() => unlink.mutate(identity.team_id)}
                disabled={unlink.isPending}
                aria-label={`Unlink Slack in ${identity.team || identity.team_id}`}
                className="text-sm font-medium text-clay underline-offset-2 hover:underline disabled:opacity-60"
              >
                Unlink
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-sm text-[var(--text-secondary)]">
          Link your Slack account so Mylo can ask you questions and send your report there.
        </p>
      )}
      {code.data ? (
        <p role="status" className="text-sm text-[var(--text-primary)]">
          Send Mylo this in a Slack direct message:{" "}
          <code className="rounded bg-surface-alt px-1.5 py-0.5 font-mono text-[13px]">{code.data.code}</code>{" "}
          <span className="text-[var(--text-secondary)]">
            (valid for {Math.round(code.data.expires_in / 60)} minutes)
          </span>
        </p>
      ) : (
        <button
          type="button"
          onClick={() => code.mutate()}
          disabled={code.isPending}
          className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
        >
          {identities.length ? "Link another workspace" : "Link Slack"}
        </button>
      )}
      {code.error ? <p className="mt-2 text-sm text-clay">{code.error.message}</p> : null}
    </Card>
  );
}

export function SlackLabCard({ slug }: { slug: string }) {
  const status = useSlackStatus(slug);
  const code = useSlackLabCode(slug);
  const switches = useSlackLabSwitches(slug);
  if (!status.data?.enabled) return null;
  const workspace = status.data.lab_workspace;
  return (
    <Card className="p-[22px]" data-ambient="slack-lab">
      <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">Slack</h2>
      {workspace ? (
        <div className="space-y-3 text-sm text-[var(--text-secondary)]">
          <p>
            Linked to <span className="font-medium text-[var(--text-primary)]">{workspace.name || workspace.team_id}</span>
            {workspace.has_channel ? ", with a channel for the lab's posts." : "."}
          </p>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={workspace.listening}
              disabled={switches.isPending}
              onChange={(event) => switches.mutate({ on: event.target.checked })}
            />
            Listen in this workspace (each person still opts in themselves)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={workspace.primary}
              disabled={switches.isPending}
              onChange={(event) => switches.mutate({ primary: event.target.checked })}
            />
            Post the lab&apos;s reports here instead of Discord
          </label>
        </div>
      ) : (
        <div className="space-y-3 text-sm text-[var(--text-secondary)]">
          {status.data.installable ? (
            <p>
              <a
                href="/api/integrations/slack/install/"
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Add Mylo to your Slack workspace
              </a>
              , then link it to this lab with a code.
            </p>
          ) : null}
          {code.data ? (
            <p role="status" className="text-[var(--text-primary)]">
              In the channel that should get the lab&apos;s posts, mention Mylo with:{" "}
              <code className="rounded bg-surface-alt px-1.5 py-0.5 font-mono text-[13px]">{code.data.code}</code>
            </p>
          ) : (
            <button
              type="button"
              onClick={() => code.mutate()}
              disabled={code.isPending}
              className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
            >
              Make a lab link code
            </button>
          )}
          {code.error ? <p className="text-clay">{code.error.message}</p> : null}
        </div>
      )}
    </Card>
  );
}

export function TeamsPersonCard() {
  const status = useTeamsStatus();
  const code = useTeamsLinkCode();
  if (!status.data?.enabled) return null;
  const linked = status.data.identities.length > 0;
  return (
    <Card className="p-[22px]" data-ambient="teams-person">
      <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">Microsoft Teams</h2>
      <p className="mb-3 text-sm text-[var(--text-secondary)]">
        {linked
          ? "Your Teams account is linked."
          : "Link your Teams account so Mylo can ask you questions there."}
      </p>
      {code.data ? (
        <p role="status" className="text-sm text-[var(--text-primary)]">
          Send Mylo this in a Teams chat:{" "}
          <code className="rounded bg-surface-alt px-1.5 py-0.5 font-mono text-[13px]">{code.data.code}</code>
        </p>
      ) : (
        <button
          type="button"
          onClick={() => code.mutate()}
          disabled={code.isPending}
          className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
        >
          {linked ? "Link again" : "Link Teams"}
        </button>
      )}
      {code.error ? <p className="mt-2 text-sm text-clay">{code.error.message}</p> : null}
    </Card>
  );
}

export function TeamsLabCard({ slug }: { slug: string }) {
  const status = useTeamsStatus(slug);
  const code = useTeamsLabCode(slug);
  const switches = useTeamsLabSwitches(slug);
  if (!status.data?.enabled) return null;
  const team = status.data.lab_team;
  return (
    <Card className="p-[22px]" data-ambient="teams-lab">
      <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">Microsoft Teams</h2>
      {team ? (
        <div className="space-y-3 text-sm text-[var(--text-secondary)]">
          <p>
            Linked to <span className="font-medium text-[var(--text-primary)]">{team.name || "a team"}</span>.
            Reading channels without a mention needs your tenant admin&apos;s consent at install.
          </p>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={team.listening}
              disabled={switches.isPending}
              onChange={(event) => switches.mutate({ on: event.target.checked })}
            />
            Listen in this team (each person still opts in themselves)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={team.primary}
              disabled={switches.isPending}
              onChange={(event) => switches.mutate({ primary: event.target.checked })}
            />
            Post the lab&apos;s reports here instead of Discord
          </label>
        </div>
      ) : code.data ? (
        <p role="status" className="text-sm text-[var(--text-primary)]">
          Add Mylo to your team, then in the channel for the lab&apos;s posts mention Mylo with:{" "}
          <code className="rounded bg-surface-alt px-1.5 py-0.5 font-mono text-[13px]">{code.data.code}</code>
        </p>
      ) : (
        <button
          type="button"
          onClick={() => code.mutate()}
          disabled={code.isPending}
          className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
        >
          Make a lab link code
        </button>
      )}
    </Card>
  );
}
