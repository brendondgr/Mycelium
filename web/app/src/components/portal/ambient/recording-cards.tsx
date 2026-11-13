"use client";

/**
 * What Mylo records — both halves of the switch (settings plan, Phase 4).
 *
 * `RecordingScopeCard` is yours, under You → Mylo & you: keep one server or one
 * project out. `OrgServerListeningCard` is the head's, under an org's Mylo &
 * servers page: whether Mylo listens in each of the org's Discord servers. The
 * head's off wins — your switch for that server reads off and locked.
 */

import * as React from "react";

import { Toggle } from "@/components/portal/ambient/ambient-settings-card";
import { Card } from "@/components/portal/primitives/card";
import {
  useOrgServers,
  useRecording,
  useSaveOrgServer,
  useSaveRecording,
} from "@/lib/portal/ambient/hooks";

const PLATFORM_NAME: Record<string, string> = {
  discord: "Discord",
  slack: "Slack",
  teams: "Teams",
};

export function RecordingScopeCard() {
  const query = useRecording();
  const save = useSaveRecording();
  const [message, setMessage] = React.useState<string | null>(null);

  const update = (
    body: { server: number; record: boolean } | { project: string; record: boolean },
    done: string,
  ) => {
    setMessage(null);
    save.mutate(body, {
      onSuccess: () => setMessage(done),
      onError: (error) => setMessage(error.message),
    });
  };

  return (
    <Card className="p-[22px]" aria-labelledby="recording-scope-title" data-ambient="recording">
      <h2 id="recording-scope-title" className="font-display text-lg text-[var(--text-primary)]">
        Where Mylo records you
      </h2>
      <p className="mt-1 max-w-[62ch] text-sm text-[var(--text-secondary)]">
        These are your switches, beneath the platform ones above. A server&apos;s lab or department can
        also switch listening off there, and theirs wins: while it is off, nobody there is recorded and
        you can&apos;t turn yours back on.
      </p>
      {query.isLoading ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : query.isError || !query.data ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load these switches.</p>
      ) : (
        <fieldset className="mt-4 space-y-5" disabled={save.isPending}>
          <legend className="sr-only">Servers and projects</legend>
          <section aria-labelledby="recording-servers-title" className="space-y-3">
            <h3
              id="recording-servers-title"
              className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
            >
              Servers
            </h3>
            {query.data.servers.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">
                Mylo isn&apos;t listening in any of your labs&apos; or departments&apos; servers.
              </p>
            ) : (
              query.data.servers.map((server) => (
                <Toggle
                  key={server.id}
                  id={`recording-server-${server.id}`}
                  label={`${server.label} · ${PLATFORM_NAME[server.platform] ?? server.platform}`}
                  help={
                    server.locked
                      ? server.locked_reason
                      : `${server.orgs.join(", ") || "Your server"}. Off keeps everything you say here out.`
                  }
                  checked={server.recording}
                  disabled={server.locked}
                  onChange={(on) =>
                    update(
                      { server: server.id, record: on },
                      on ? `Mylo may record you in ${server.label}.` : `Nothing you say in ${server.label} is recorded.`,
                    )
                  }
                />
              ))
            )}
          </section>
          <section aria-labelledby="recording-projects-title" className="space-y-3">
            <h3
              id="recording-projects-title"
              className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
            >
              Projects
            </h3>
            {query.data.projects.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">You aren&apos;t on any projects.</p>
            ) : (
              query.data.projects.map((project) => (
                <Toggle
                  key={project.id}
                  id={`recording-project-${project.id}`}
                  label={project.name}
                  help="Off: Mylo never ties what you say to this project, and doesn't record you in a channel set aside for it."
                  checked={!project.excluded}
                  onChange={(on) =>
                    update(
                      { project: project.id, record: on },
                      on ? `${project.name} is back on.` : `Mylo won't record you about ${project.name}.`,
                    )
                  }
                />
              ))
            )}
          </section>
        </fieldset>
      )}
      <p aria-live="polite" className="mt-3 min-h-[1.25rem] text-sm text-[var(--text-secondary)]">
        {message}
      </p>
    </Card>
  );
}

export function OrgServerListeningCard({
  kind,
  orgRef,
  name,
}: {
  kind: "lab" | "department";
  orgRef: string;
  name: string;
}) {
  const query = useOrgServers(kind, orgRef);
  const save = useSaveOrgServer(kind, orgRef);
  const [message, setMessage] = React.useState<string | null>(null);
  return (
    <Card className="p-[22px]" aria-labelledby={`org-listening-${kind}-title`}>
      <h2 id={`org-listening-${kind}-title`} className="font-display text-lg text-[var(--text-primary)]">
        Listening in {name}&apos;s Discord
      </h2>
      <p className="mt-1 max-w-[62ch] text-sm text-[var(--text-secondary)]">
        Whether Mylo may learn from conversation in each server. Off wins over every member&apos;s own
        switch: nobody there is recorded, and members can&apos;t turn it back on for themselves. On,
        each person still decides for themselves.
      </p>
      {query.isLoading ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : query.isError || !query.data ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load the servers.</p>
      ) : query.data.servers.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">No Discord server is linked yet.</p>
      ) : (
        <fieldset className="mt-4 space-y-3" disabled={save.isPending}>
          <legend className="sr-only">Listening per server</legend>
          {query.data.servers.map((server) => (
            <Toggle
              key={server.guild_id}
              id={`org-listening-${server.guild_id}`}
              label={server.name}
              help={
                !server.available && !server.listening
                  ? "Listening isn't turned on for this Mycelium."
                  : server.shared_with.length
                    ? `Shared with ${server.shared_with.join(", ")}; their managers hold this switch too.`
                    : "Only this server."
              }
              checked={server.listening}
              disabled={!server.available && !server.listening}
              onChange={(on) => {
                setMessage(null);
                save.mutate(
                  { guild_id: server.guild_id, on },
                  {
                    onSuccess: () =>
                      setMessage(on ? `Mylo listens in ${server.name}.` : `Listening is off in ${server.name}.`),
                    onError: (error) => setMessage(error.message),
                  },
                );
              }}
            />
          ))}
        </fieldset>
      )}
      <p aria-live="polite" className="mt-3 min-h-[1.25rem] text-sm text-[var(--text-secondary)]">
        {message}
      </p>
    </Card>
  );
}
