"use client";

import * as React from "react";

import { DiscordLink } from "@/components/portal/primitives/discord-link";
import type {
  DiscordThreadLink,
  Usability,
  UsabilityCheck,
} from "@/lib/portal/types";

const TONE: Record<UsabilityCheck["status"], { bg: string; fg: string; word: string }> = {
  ok: {
    bg: "color-mix(in srgb, var(--success) 16%, transparent)",
    fg: "var(--text-primary)",
    word: "Yes",
  },
  warn: {
    bg: "color-mix(in srgb, var(--warning) 20%, transparent)",
    fg: "var(--text-primary)",
    word: "Check",
  },
  unknown: {
    bg: "color-mix(in srgb, var(--text-secondary) 12%, transparent)",
    fg: "var(--text-secondary)",
    word: "Unknown",
  },
  block: {
    bg: "color-mix(in srgb, var(--destructive) 16%, transparent)",
    fg: "var(--text-primary)",
    word: "No",
  },
};

function StatusGlyph({ status }: { status: UsabilityCheck["status"] }) {
  const common = {
    "aria-hidden": true,
    width: 13,
    height: 13,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (status === "ok") return <svg {...common}><polyline points="5 12.5 10 17 19 7" /></svg>;
  if (status === "warn")
    return (
      <svg {...common}>
        <path d="M12 4 L21 19 H3 Z" />
        <line x1="12" y1="10" x2="12" y2="14" />
      </svg>
    );
  if (status === "block")
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5" />
    </svg>
  );
}

/** One check as a pill: an icon, a status word for screen readers, the label. */
export function CheckPill({ check }: { check: UsabilityCheck }) {
  const tone = TONE[check.status];
  return (
    <li
      className="inline-flex min-h-[28px] items-center gap-1.5 rounded-full px-2.5 py-1 text-[12.5px] font-medium"
      style={{ background: tone.bg, color: tone.fg }}
      title={`Read from the record's ${check.field.replace(/_/g, " ")}`}
    >
      <StatusGlyph status={check.status} />
      <span className="sr-only">{tone.word}: </span>
      {check.label}
    </li>
  );
}

/**
 * The one "Can we use this?" strip on an opportunity card (plan "Web surfaces"):
 * the record's checks, who should look, and where it was announced. It replaces
 * the separate "Best suited to" and team-fit strips. No percentage anywhere.
 */
export function UsabilityStrip({
  usability,
  people,
  announced,
  fallbackChannel,
}: {
  usability: Usability | null | undefined;
  /** Who should look: names (and a short why) the lab strip already shows. */
  people?: { name: string; why?: string }[];
  announced?: DiscordThreadLink[];
  fallbackChannel?: string;
}) {
  const checks = (usability?.checks ?? []).filter((c) => c.key !== "team");
  if (!checks.length && !people?.length && !announced?.length) return null;
  return (
    <section
      aria-label="Can we use this?"
      className="mt-3 flex flex-col gap-2.5 rounded-xl border border-[var(--divider)] bg-surface-alt p-3"
    >
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Can we use this?
      </h3>
      {checks.length ? (
        <ul className="flex flex-wrap gap-1.5">
          {checks.map((check) => (
            <CheckPill key={check.key} check={check} />
          ))}
        </ul>
      ) : null}
      {people?.length ? (
        <div className="text-[13px] text-[var(--text-primary)]">
          <p className="m-0">
            <span className="text-[var(--text-secondary)]">Who should look: </span>
            {people.map((p, i) => (
              <React.Fragment key={p.name}>
                {i ? " · " : ""}
                <strong className="font-semibold">{p.name}</strong>
              </React.Fragment>
            ))}
          </p>
          {people[0].why ? (
            <p className="m-0 mt-0.5 text-[12.5px] leading-snug text-[var(--text-secondary)]">
              {people[0].why.startsWith(people[0].name)
                ? people[0].why
                : `${people[0].name}: ${people[0].why}`}
            </p>
          ) : null}
        </div>
      ) : null}
      {announced?.length ? (
        <p className="m-0 flex flex-wrap items-center gap-1 text-[13px] text-[var(--text-secondary)]">
          Announced
          <DiscordLink links={announced} fallbackChannel={fallbackChannel} surface="card" />
        </p>
      ) : null}
    </section>
  );
}
