"use client";

import * as React from "react";

import { Toggle } from "@/components/portal/ambient/ambient-settings-card";
import { Card } from "@/components/portal/primitives/card";
import { AgentError } from "@/lib/portal/agent/client";
import type { AgentPolicy } from "@/lib/portal/agent/types";
import {
  useAgentCatalog,
  useAgentPolicy,
  useAgentPreferences,
  useSaveAgentPolicy,
  useSaveAgentPreferences,
} from "@/lib/portal/hooks";

function message(error: unknown, fallback: string): string {
  if (error instanceof AgentError) return error.fix ? `${error.message} ${error.fix}` : error.message;
  return error instanceof Error ? error.message : fallback;
}

/**
 * Mylo & you → chat: whether Mylo's chat is on for this person, and whether
 * Mylo may learn from what they say in it. Both are the person's own
 * switches on the agent's preferences route; the gate reads them.
 */
export function ChatSettingsCard() {
  const prefs = useAgentPreferences();
  const save = useSaveAgentPreferences();
  const [note, setNote] = React.useState<string | null>(null);
  // No agent on this instance: nothing to switch.
  if (prefs.error instanceof AgentError && prefs.error.status === 404) return null;

  const update = (changes: { chat_enabled?: boolean; learning?: boolean }, done: string) => {
    setNote(null);
    save.mutate(changes, {
      onSuccess: () => setNote(done),
      onError: (error) => setNote(message(error, "Could not save that.")),
    });
  };

  return (
    <Card className="mb-4 p-[22px]" aria-labelledby="mylo-chat-settings-title">
      <h2 id="mylo-chat-settings-title" className="font-display text-lg text-[var(--text-primary)]">
        Chatting with Mylo
      </h2>
      {prefs.isLoading ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : prefs.isError || !prefs.data ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load these settings.</p>
      ) : (
        <fieldset className="mt-3 space-y-3" disabled={save.isPending}>
          <legend className="sr-only">Mylo chat</legend>
          <Toggle
            id="mylo-chat-enabled"
            label="Chat with Mylo"
            help="Ask Mylo about anything in the app from the side panel and the Ask Mylo buttons. Turning it off keeps your conversations; it only hides the chat."
            checked={prefs.data.chat_enabled}
            onChange={(on) => update({ chat_enabled: on }, on ? "Chat is on." : "Chat is off.")}
          />
          <Toggle
            id="mylo-chat-learning"
            label="Let Mylo learn from your chats"
            help="Mylo may notice things you say to keep your profile and recommendations current, and asks you before anything changes. Only your own words are read, never Mylo's."
            checked={prefs.data.learning}
            onChange={(on) =>
              update({ learning: on }, on ? "Mylo learns from your chats." : "Mylo no longer learns from your chats.")
            }
          />
        </fieldset>
      )}
      <p aria-live="polite" className="mt-2 min-h-[1.25rem] text-sm text-[var(--text-secondary)]">
        {note}
      </p>
    </Card>
  );
}

/** Plain names for the agent's function groups; unknown groups show as named. */
const GROUP_LABELS: Record<string, string> = {
  me: "The person's own profile and saves",
  projects: "Projects",
  corpus: "Searching papers and calls",
  org: "The lab, its members and their profiles",
  feeds: "Feeds, saves and deadlines",
  knowledge: "The knowledge graph",
  files: "Stored files",
  fulltext: "Full text of papers",
};

/**
 * A lab's or department's narrowing policy for Mylo: which kinds of things
 * Mylo may use for members asking here, and whether members' chats may inform
 * the shared understanding. It can only narrow what this Mycelium allows; the
 * agent refuses anything wider and anyone who may not change it, and the card
 * shows that refusal as given.
 */
export function AgentPolicyCard({
  kind,
  orgRef,
  name,
}: {
  kind: "lab" | "department";
  orgRef: string;
  name: string;
}) {
  const policy = useAgentPolicy(kind, orgRef);
  const catalog = useAgentCatalog();
  if (policy.error instanceof AgentError && policy.error.status === 404) return null;

  // The groups this instance has, from the gate's own catalog.
  const groups = catalog.data?.ok
    ? Array.from(
        new Set(catalog.data.functions.map((f) => f.group).filter((g) => g && g !== "agent" && g !== "*")),
      ).sort()
    : [];

  return (
    <Card className="p-5" aria-labelledby={`${kind}-agent-policy-title`}>
      <h2
        id={`${kind}-agent-policy-title`}
        className="font-display text-lg text-[var(--text-primary)]"
      >
        Mylo in {name}
      </h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Narrow what Mylo may use when members ask about this {kind}. It can only
        narrow what this Mycelium allows.
      </p>
      {policy.isLoading ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : policy.isError || !policy.data ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load this policy.</p>
      ) : (
        <PolicyBody
          key={JSON.stringify(policy.data)}
          kind={kind}
          orgRef={orgRef}
          data={policy.data}
          groups={Array.from(new Set([...groups, ...policy.data.groups_off])).sort()}
        />
      )}
    </Card>
  );
}

function PolicyBody({
  kind,
  orgRef,
  data,
  groups,
}: {
  kind: "lab" | "department";
  orgRef: string;
  data: AgentPolicy;
  groups: string[];
}) {
  const save = useSaveAgentPolicy(kind, orgRef);
  const [note, setNote] = React.useState<string | null>(null);
  const update = (changes: Partial<AgentPolicy>, done: string) => {
    setNote(null);
    save.mutate(changes, {
      onSuccess: () => setNote(done),
      onError: (error) => setNote(message(error, "Could not save that.")),
    });
  };
  const off = new Set(data.groups_off);

  return (
    <>
      <fieldset className="mt-3 space-y-3" disabled={save.isPending}>
        <legend className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
          What Mylo may use here
        </legend>
        {groups.length ? (
          groups.map((group) => (
            <Toggle
              key={group}
              id={`${kind}-policy-${group}`}
              label={GROUP_LABELS[group] ?? group}
              help={off.has(group) ? "Off for members asking here." : "On, as far as this Mycelium allows."}
              checked={!off.has(group)}
              onChange={(on) => {
                const next = new Set(off);
                if (on) next.delete(group);
                else next.add(group);
                update(
                  { groups_off: Array.from(next) },
                  on ? `${GROUP_LABELS[group] ?? group}: on.` : `${GROUP_LABELS[group] ?? group}: off.`,
                );
              }}
            />
          ))
        ) : (
          <p className="text-sm text-[var(--text-secondary)]">
            Mylo&apos;s chat isn&apos;t available to you here, so there is nothing to narrow.
          </p>
        )}
        <Toggle
          id={`${kind}-policy-inform`}
          label={`Members' chats may inform the ${kind}'s shared understanding`}
          help="When on, what members tell Mylo can shape what Mylo knows about this group. A member's own learning switch still applies."
          checked={data.members_inform_org}
          onChange={(on) => update({ members_inform_org: on }, on ? "Members' chats may inform it." : "Members' chats stay their own.")}
        />
      </fieldset>
      <p aria-live="polite" className="mt-2 min-h-[1.25rem] text-sm text-[var(--text-secondary)]">
        {note}
      </p>
    </>
  );
}
