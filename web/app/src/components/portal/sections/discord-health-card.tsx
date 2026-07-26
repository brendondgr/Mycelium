"use client";

import { Pill } from "@/components/portal/primitives/pill";
import { DetailCard } from "@/components/portal/sections/labs-section";
import { useLabDiscordHealth } from "@/lib/portal/hooks";
import type {
  DiscordChannelHealth,
  DiscordHealth,
  DiscordMemberHealth,
  MyLab,
} from "@/lib/portal/types";

/**
 * Why Mylo can or cannot reach this lab — the answer to "why is nobody getting
 * anything?".
 *
 * The point of this card is that silence has several very different causes, and a
 * lab lead cannot act until they know which: the bot was removed, a channel was
 * deleted, the add-on lapsed, or one person closed their DMs. Each gets its own
 * sentence naming what would fix it, rather than a single "not working" badge.
 *
 * One distinction is load-bearing and easy to get wrong: being in the lab's Discord
 * server and being reachable by direct message are independent. A personal DM works
 * through the person's own installation, so someone who never joined the server
 * still gets their reminders — they just cannot be tagged in a channel post. Saying
 * "unreachable" for that person would be false.
 */
export function DiscordHealthCard({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabDiscordHealth(lab.slug);

  if (isLoading) {
    return (
      <DetailCard title="Mylo in Discord">
        <p className="text-sm text-[var(--text-muted)]">Checking…</p>
      </DetailCard>
    );
  }
  if (isError || !data) {
    return (
      <DetailCard title="Mylo in Discord">
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t check right now. Try again in a moment.
        </p>
      </DetailCard>
    );
  }
  if (!data.guild.state) {
    return (
      <DetailCard title="Mylo in Discord">
        <p className="text-sm text-[var(--text-secondary)]">
          This lab hasn&apos;t connected a Discord server yet.
        </p>
      </DetailCard>
    );
  }

  const unreachable = data.members.filter((m) => !isReachable(m));

  return (
    <DetailCard title="Mylo in Discord">
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-[var(--text-primary)]">
            Reachability
          </span>
          <Pill tone={overallTone(data)}>{overallLabel(data)}</Pill>
        </div>
        {data.guild.state === "kicked" ? (
          <Note tone="clay">
            Mylo isn&apos;t in this lab&apos;s server any more. Nothing has been
            removed from Mycelium — re-add Mylo to start receiving updates again.
          </Note>
        ) : null}

        {data.addon.active === false ? (
          <Note tone="review">
            Scheduled Discord updates are paused because this lab&apos;s Mylo add-on
            has lapsed. Nothing was removed, and commands still work.
          </Note>
        ) : null}

        <ChannelRow
          label="Deadline announcements"
          channel={data.channels.announcements}
        />
        <ChannelRow label="Daily updates" channel={data.channels.updates} />

        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {unreachable.length === 0
              ? `All ${data.members.length} members can be reached.`
              : `${unreachable.length} of ${data.members.length} members can't be reached.`}
          </p>
          {unreachable.length > 0 ? (
            <ul className="mt-2 space-y-1.5">
              {unreachable.map((member) => (
                <li
                  key={member.username}
                  className="flex items-start justify-between gap-3 text-sm"
                >
                  <span className="text-[var(--text-secondary)]">{member.name}</span>
                  <span className="shrink-0 text-right text-xs text-[var(--text-muted)]">
                    {memberReason(member)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </DetailCard>
  );
}

function ChannelRow({
  label,
  channel,
}: {
  label: string;
  channel: DiscordChannelHealth;
}) {
  // A blank binding is a deliberate opt-out, not a fault — it must not read as a
  // problem the lead needs to fix.
  const { tone, text } = !channel.bound
    ? { tone: "neutral" as const, text: "Turned off" }
    : channel.ok === false
      ? { tone: "clay" as const, text: "Mylo can't post here" }
      : channel.ok === true
        ? { tone: "primary" as const, text: "Working" }
        : { tone: "review" as const, text: "Not checked yet" };

  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <Pill tone={tone}>{text}</Pill>
    </div>
  );
}

function Note({
  tone,
  children,
}: {
  tone: "clay" | "review";
  children: React.ReactNode;
}) {
  const border = tone === "clay" ? "var(--clay)" : "var(--accent)";
  return (
    <p
      className="rounded-lg border-l-2 bg-[var(--surface-alt)] px-3 py-2 text-sm text-[var(--text-secondary)]"
      style={{ borderLeftColor: border }}
    >
      {children}
    </p>
  );
}

function isReachable(member: DiscordMemberHealth): boolean {
  // Unprobed (`dm_ok === null`) is not a failure — we simply haven't checked. Only a
  // measured `false`, or never having connected at all, counts as unreachable.
  return member.linked && member.dm_ok !== false;
}

function memberReason(member: DiscordMemberHealth): string {
  if (!member.linked) return "Discord not connected";
  return "Direct messages closed";
}

function overallTone(data: DiscordHealth): "primary" | "review" | "clay" {
  if (data.guild.state === "kicked") return "clay";
  if (data.channels.updates.ok === false) return "clay";
  if (data.channels.announcements.ok === false) return "clay";
  if (data.addon.active === false) return "review";
  return "primary";
}

function overallLabel(data: DiscordHealth): string {
  if (data.guild.state === "kicked") return "Removed";
  if (data.addon.active === false) return "Paused";
  if (
    data.channels.updates.ok === false ||
    data.channels.announcements.ok === false
  ) {
    return "Needs attention";
  }
  return "Healthy";
}
