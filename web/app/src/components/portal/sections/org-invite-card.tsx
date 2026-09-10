"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { useOrgInvites } from "@/lib/portal/hooks";
import type { OrgKind } from "@/lib/auth-types";
import type { OrgInvite } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const INPUT =
  "min-w-0 flex-1 rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

const ROLES = ["member", "admin", "viewer"] as const;

type Tab = "email" | "link";

/**
 * The two ways into a lab or a department, side by side.
 *
 * They are presented as a choice rather than one form with options because they
 * trade off against each other and the person picking should see the trade:
 * an emailed invitation only the named mailbox can spend, or a link anyone can
 * follow that is held instead by a headcount and a clock.
 */
export function OrgInviteCard({
  kind,
  id,
  canInvite,
  isVerified,
}: {
  kind: OrgKind;
  id: string;
  canInvite: boolean;
  /** Creating an invitation needs an activated account; the card says so. */
  isVerified: boolean;
}) {
  const { list, create, revoke } = useOrgInvites(kind, id);
  const [tab, setTab] = React.useState<Tab>("email");
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<string>("member");
  const [maxUses, setMaxUses] = React.useState("25");
  const [expiryDays, setExpiryDays] = React.useState("7");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState<string | null>(null);

  if (!canInvite) {
    return null;
  }

  const noun = kind === "lab" ? "lab" : "department";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSent(null);
    create.mutate(
      tab === "email"
        ? { kind: "email", email: email.trim(), role, message: message.trim() }
        : {
            kind: "link",
            role,
            max_uses: Number(maxUses) || undefined,
            expires_in_days: Number(expiryDays) || undefined,
            message: message.trim(),
          },
      {
        onSuccess: (invite) => {
          setEmail("");
          setMessage("");
          setSent(
            invite.kind === "email"
              ? `Invitation sent to ${invite.email}.`
              : "Link created — copy it below.",
          );
        },
        onError: (cause) => setError((cause as Error).message),
      },
    );
  }

  const live = (list.data ?? []).filter((invite) => invite.is_live);

  return (
    <Card className="p-5">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Invite members
      </h3>

      {!isVerified ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Verify your email address to invite people. Mycelium sends these
          invitations on your behalf, so your own address has to answer first —
          the code is on your{" "}
          <a
            className="font-medium text-primary underline underline-offset-2"
            href="/app/account"
          >
            Account page
          </a>
          .
        </p>
      ) : (
        <>
          <div
            role="tablist"
            aria-label="How to invite"
            className="mb-3 mt-2 flex gap-1.5"
          >
            {(["email", "link"] as Tab[]).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => {
                  setTab(value);
                  setError(null);
                  setSent(null);
                }}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  tab === value
                    ? "border-primary text-[var(--text-primary)]"
                    : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt",
                )}
                style={
                  tab === value
                    ? {
                        backgroundColor:
                          "color-mix(in srgb, var(--primary) 10%, var(--card))",
                      }
                    : undefined
                }
              >
                {value === "email" ? "By email" : "Share a link"}
              </button>
            ))}
          </div>

          <p className="mb-3 text-[12px] text-[var(--text-muted)]">
            {tab === "email"
              ? `Only the address you name can use this invitation, so it is the safer of the two.`
              : `Anyone with the link can join this ${noun} until it runs out of places or expires.`}
          </p>

          <form onSubmit={submit} className="space-y-2.5">
            {tab === "email" ? (
              <input
                type="email"
                required
                className={INPUT + " w-full"}
                placeholder="colleague@university.edu"
                aria-label="Email address to invite"
                value={email}
                disabled={create.isPending}
                onChange={(event) => setEmail(event.target.value)}
              />
            ) : (
              <div className="flex flex-wrap gap-2.5">
                <label className="flex-1 text-[12px] text-[var(--text-secondary)]">
                  Max accounts
                  <input
                    type="number"
                    min={1}
                    max={500}
                    className={INPUT + " mt-1 w-full"}
                    value={maxUses}
                    disabled={create.isPending}
                    onChange={(event) => setMaxUses(event.target.value)}
                  />
                </label>
                <label className="flex-1 text-[12px] text-[var(--text-secondary)]">
                  Expires in (days)
                  <input
                    type="number"
                    min={1}
                    max={90}
                    className={INPUT + " mt-1 w-full"}
                    value={expiryDays}
                    disabled={create.isPending}
                    onChange={(event) => setExpiryDays(event.target.value)}
                  />
                </label>
              </div>
            )}

            <div className="flex flex-wrap items-end gap-2.5">
              <label className="text-[12px] text-[var(--text-secondary)]">
                Joins as
                <select
                  className={INPUT + " mt-1 block"}
                  value={role}
                  disabled={create.isPending}
                  onChange={(event) => setRole(event.target.value)}
                >
                  {ROLES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <input
                type="text"
                className={INPUT}
                placeholder="Optional note"
                aria-label="Optional note to the invitee"
                value={message}
                disabled={create.isPending}
                onChange={(event) => setMessage(event.target.value)}
              />
              <button
                type="submit"
                className={PRIMARY_BUTTON}
                disabled={create.isPending || (tab === "email" && !email.trim())}
              >
                {create.isPending
                  ? "Working…"
                  : tab === "email"
                    ? "Send invitation"
                    : "Create link"}
              </button>
            </div>
          </form>

          {error ? (
            <p className="mt-2 text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
          {sent ? (
            <p className="mt-2 text-[12.5px] text-[var(--text-secondary)]" role="status">
              {sent}
            </p>
          ) : null}

          <div className="mt-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
              Open invitations
            </p>
            {list.isLoading ? (
              <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
            ) : live.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">
                Nothing outstanding.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {live.map((invite) => (
                  <InviteRow
                    key={invite.id}
                    invite={invite}
                    onRevoke={() => revoke.mutate(invite.id)}
                    revoking={revoke.isPending}
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function InviteRow({
  invite,
  onRevoke,
  revoking,
}: {
  invite: OrgInvite;
  onRevoke: () => void;
  revoking: boolean;
}) {
  const [copied, setCopied] = React.useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(invite.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the link is on screen either way.
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">
          {invite.kind === "email" ? invite.email : invite.url}
        </p>
        <p className="mt-0.5 text-[11.5px] text-[var(--text-muted)]">
          Joins as {invite.role} · {invite.uses_left} of {invite.max_uses} left ·
          expires {new Date(invite.expires_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex flex-none items-center gap-1.5">
        <Pill tone={invite.kind === "email" ? "primary" : "dashed"}>
          {invite.kind === "email" ? "Email" : "Link"}
        </Pill>
        {invite.kind === "link" ? (
          <button type="button" className={GHOST_BUTTON} onClick={() => void copy()}>
            {copied ? "Copied" : "Copy"}
          </button>
        ) : null}
        <button
          type="button"
          className={GHOST_BUTTON}
          onClick={onRevoke}
          disabled={revoking}
        >
          Withdraw
        </button>
      </div>
    </li>
  );
}
