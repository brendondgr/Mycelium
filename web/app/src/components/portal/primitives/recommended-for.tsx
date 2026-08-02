"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import type { RecommendedMember } from "@/lib/portal/types";

/**
 * "Mylo suggests" — who in the lab a matched item is most applicable to.
 *
 * The one thing a lab feed carries that a personal feed does not. Everything
 * above it on the card — the ring, the filters, the layout — is identical to the
 * personal page by design, so this strip is the entire visible difference and has
 * to earn its place: it names people, says on what grounds, and quotes Mylo's own
 * sentence rather than leaving the reader to infer why anyone was named.
 *
 * Rendering nothing when there is nobody to name is deliberate — a personal card
 * simply never passes the prop, and a lab card with no confident recommendation
 * shows no strip rather than a hedged one.
 *
 * Each member is a chip; expanding one reveals the reason. The first member's
 * reason is shown open, because a card the reader has to click to understand is
 * a card they will not click.
 */
export function RecommendedFor({
  members,
  className,
}: {
  members: RecommendedMember[] | undefined;
  className?: string;
}) {
  const [openFor, setOpenFor] = React.useState<string | null>(null);

  if (!members || members.length === 0) return null;

  const lead = members[0];
  const active = members.find((m) => m.username === openFor) ?? lead;
  const activeReason = active.reason || describeBasis(active);

  return (
    <div
      className={`mt-3 rounded-xl border p-3 ${className ?? ""}`}
      style={{
        borderColor: "color-mix(in srgb, var(--accent) 30%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)",
      }}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/mylo-portrait-64.webp"
            alt=""
            width={18}
            height={18}
            className="h-[18px] w-[18px] rounded-full object-cover"
          />
          Best suited to
        </span>
        {members.map((member) => {
          const on = member.username === active.username;
          return (
            <button
              key={member.username}
              type="button"
              onClick={() =>
                setOpenFor(on && openFor !== null ? null : member.username)
              }
              aria-pressed={on}
              title={memberTitle(member)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-[3px] text-xs font-medium transition-colors ${
                on
                  ? "border-[color-mix(in_srgb,var(--accent)_45%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[var(--text-primary)]"
                  : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <Avatar initials={member.initials} seed={member.username} size={16} />
              {member.name}
              {typeof member.fit === "number" ? (
                <span className="text-[var(--text-secondary)]">{member.fit}%</span>
              ) : null}
              {member.basis.includes("eligible") ? (
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: "var(--success)" }}
                />
              ) : null}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">
          {active.name}:
        </span>{" "}
        {activeReason}
      </p>

      {active.basis.length > 1 || active.basis[0] !== "profile_fit" ? (
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          {basisNote(active)}
        </p>
      ) : null}
    </div>
  );
}

/** The chip's own tooltip — the whole claim in one line, for a hover or a screen
 * reader that never opens the panel. */
function memberTitle(member: RecommendedMember): string {
  const parts = [member.name];
  if (typeof member.fit === "number") {
    parts.push(`${member.fit}% profile match`);
  }
  if (member.basis.includes("own_match") && member.match_percent != null) {
    parts.push(`${member.match_percent}% on their own feed`);
  }
  if (member.basis.includes("eligible")) {
    parts.push(member.tier === "qualified" ? "qualified" : "possibly eligible");
  }
  return parts.join(" · ");
}

/** The fallback sentence when a member was named on a basis with no prose. */
function describeBasis(member: RecommendedMember): string {
  if (member.basis.includes("own_match")) {
    return `This already matched ${member.name}'s own feed at ${member.match_percent}%.`;
  }
  if (member.basis.includes("eligible")) {
    return `${member.name} is personally eligible for this.`;
  }
  return `Matches ${member.name}'s research profile.`;
}

/** The supporting line under the reason — what else is known about this member. */
function basisNote(member: RecommendedMember): string {
  const notes: string[] = [];
  if (member.basis.includes("own_match") && member.match_percent != null) {
    notes.push(`already a ${member.match_percent}% match on their own feed`);
  }
  if (member.basis.includes("eligible")) {
    notes.push(
      member.tier === "qualified"
        ? "personally qualified"
        : "possibly eligible — worth checking",
    );
  }
  return notes.length > 0
    ? `Also: ${notes.join(" · ")}.`
    : "";
}
