"use client";

import { useAppHref } from "@/components/demo/demo-context";
import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { useInviteToLab, useOrgInvites } from "@/lib/portal/hooks";
import type { OrgKind } from "@/lib/auth-types";
import type { OrgInvite, OrgInviteBatchResult } from "@/lib/portal/types";
import { ORG_INVITE_BATCH_MAX } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const INPUT =
  "min-w-0 flex-1 rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

const ROLES = ["member", "admin", "viewer"] as const;

const TAB_LABELS: Record<Tab, string> = {
  email: "By email",
  link: "Share a link",
  member: "Already on Mycelium",
};

type Tab = "email" | "link" | "member";

/** What separates one pasted address from the next. Mirrors the server's split. */
const ADDRESS_SPLIT = /[,;\s]+/;

/**
 * Deliberately permissive: the server is the authority on whether an address is
 * real, and this only has to stop an obvious slip becoming a chip.
 */
function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function splitAddresses(raw: string): string[] {
  return raw
    .split(ADDRESS_SPLIT)
    .map((part) => part.trim().replace(/^[<,;]+|[>,;]+$/g, "").toLowerCase())
    .filter(Boolean);
}

/**
 * The two ways into a lab or a department, side by side.
 *
 * They are presented as a choice rather than one form with options because they
 * trade off against each other and the person picking should see the trade:
 * an emailed invitation only the named mailbox can spend, or a link anyone can
 * follow that is held instead by a headcount and a clock. A lab gets a third way
 * that mails nothing at all — see the `member` tab.
 *
 * Exported without card chrome so the same panel can sit in a settings rail or in
 * a dialog opened from the roster. Every surface that invites mounts this, so
 * invite copy is fixed in one place rather than three.
 */
export type OrgInvitePanelProps = {
  kind: OrgKind;
  /** A lab's slug, or a department's id — whichever the routes take. */
  id: string;
  canInvite: boolean;
  /** Creating an invitation needs an activated account; the panel says so. */
  isVerified: boolean;
  /**
   * The roles the caller may hand out here (the org row's `grantable_roles`),
   * so the picker never offers a role the server refuses. Omitted → all three.
   */
  roles?: readonly string[];
};

export function OrgInvitePanel({
  kind,
  id,
  canInvite,
  isVerified,
  roles: allowed,
}: OrgInvitePanelProps) {
  const roleOptions = allowed ? ROLES.filter((r) => allowed.includes(r)) : [...ROLES];
  const appHref = useAppHref();
  const { list, create, createMany, revoke } = useOrgInvites(kind, id);
  const [tab, setTab] = React.useState<Tab>("email");
  const [chips, setChips] = React.useState<string[]>([]);
  const [draft, setDraft] = React.useState("");
  const [role, setRole] = React.useState<string>("member");
  const [maxUses, setMaxUses] = React.useState("25");
  const [expiryDays, setExpiryDays] = React.useState("7");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState<string | null>(null);
  const [batch, setBatch] = React.useState<OrgInviteBatchResult | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  // The third way in, lab-only: add somebody who already has an account. It mails
  // nothing, so it is not an invitation in the sense the other two tabs mean.
  const inviteExisting = useInviteToLab(id);
  const [username, setUsername] = React.useState("");

  /** Address -> why it was refused, so a chip can carry its own explanation. */
  const refusals = React.useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of batch?.failed ?? []) {
      map[row.email] = row.detail;
    }
    return map;
  }, [batch]);

  if (!canInvite) {
    return null;
  }

  const noun = kind === "lab" ? "lab" : "department";
  const full = chips.length >= ORG_INVITE_BATCH_MAX;
  const busy = create.isPending || createMany.isPending || inviteExisting.isPending;
  // Only a lab has the legacy roster invitation; a department has no equivalent.
  const tabs: Tab[] =
    kind === "lab" ? ["email", "link", "member"] : ["email", "link"];

  /**
   * Turn whatever is in the draft into chips.
   *
   * Returns the chips it produced so the submit handler can catch an address the
   * person typed but never committed — pressing Send with text still in the box
   * should send it, not silently drop it.
   */
  function commitDraft(raw: string): string[] {
    const parts = splitAddresses(raw);
    if (parts.length === 0) {
      setDraft("");
      return chips;
    }
    const next = [...chips];
    const rejected: string[] = [];
    for (const part of parts) {
      if (next.length >= ORG_INVITE_BATCH_MAX) {
        rejected.push(part);
        continue;
      }
      if (!looksLikeEmail(part)) {
        rejected.push(part);
        continue;
      }
      if (!next.includes(part)) {
        next.push(part);
      }
    }
    setChips(next);
    // Anything refused stays in the box so it can be corrected in place.
    setDraft(rejected.join(", "));
    if (rejected.length > 0) {
      setError(
        next.length >= ORG_INVITE_BATCH_MAX
          ? `That is as many as one invitation can carry — ${ORG_INVITE_BATCH_MAX}. Send these, then add the rest.`
          : "That does not look like an email address.",
      );
    } else {
      setError(null);
    }
    return next;
  }

  function removeChip(value: string) {
    setChips((current) => current.filter((chip) => chip !== value));
    setError(null);
  }

  function onDraftKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === "," || event.key === ";") {
      // Enter must not submit the form; in a chip field it commits the address.
      event.preventDefault();
      commitDraft(draft);
      return;
    }
    if (event.key === "Backspace" && draft === "" && chips.length > 0) {
      event.preventDefault();
      removeChip(chips[chips.length - 1]);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSent(null);
    setBatch(null);

    if (tab === "member") {
      const value = username.trim();
      if (!value) {
        setError("Enter the username of someone already on Mycelium.");
        return;
      }
      inviteExisting.mutate(
        { identifier: value, role },
        {
          onSuccess: () => {
            setUsername("");
            setSent(`${value} has been asked to join. It is in their notifications now.`);
          },
          onError: (cause) => setError((cause as Error).message),
        },
      );
      return;
    }

    if (tab === "email") {
      const addresses = commitDraft(draft);
      if (addresses.length === 0) {
        setError("Add at least one email address.");
        return;
      }
      createMany.mutate(
        { emails: addresses, role, message: message.trim() },
        {
          onSuccess: (result) => {
            setBatch(result);
            // Keep only what was refused, so a typo is fixed rather than retyped.
            setChips(result.failed.map((row) => row.email));
            if (result.created.length > 0) {
              setMessage("");
              setSent(
                result.created.length === 1
                  ? `Invitation sent to ${result.created[0].email}.`
                  : `${result.created.length} invitations sent.`,
              );
            }
          },
          onError: (cause) => setError((cause as Error).message),
        },
      );
      return;
    }

    create.mutate(
      {
        kind: "link",
        role,
        max_uses: Number(maxUses) || undefined,
        expires_in_days: Number(expiryDays) || undefined,
        message: message.trim(),
      },
      {
        onSuccess: () => {
          setMessage("");
          setSent("Link created — copy it below.");
        },
        onError: (cause) => setError((cause as Error).message),
      },
    );
  }

  const live = (list.data ?? []).filter((invite) => invite.is_live);

  return (
    <>
      {!isVerified ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Verify your email address to invite people. Mycelium sends these
          invitations on your behalf, so your own address has to answer first —
          the code is on your{" "}
          <a
            className="font-medium text-primary underline underline-offset-2"
            href={appHref("/app/settings/you/account")}
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
            {tabs.map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => {
                  setTab(value);
                  setError(null);
                  setSent(null);
                  setBatch(null);
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
                {TAB_LABELS[value]}
              </button>
            ))}
          </div>

          <p className="mb-3 text-[12px] text-[var(--text-muted)]">
            {tab === "email"
              ? `Type an address and press Enter to add it. Up to ${ORG_INVITE_BATCH_MAX} at a time — each person gets their own invitation, usable only from the address you named.`
              : tab === "link"
                ? `Anyone with the link can join this ${noun} until it runs out of places or expires.`
                : `For someone who already has a Mycelium account. It lands in their notifications for them to accept — nothing is emailed, and it does nothing for a person without an account.`}
          </p>

          <form onSubmit={submit} className="space-y-2.5">
            {tab === "email" ? (
              <div>
                <div
                  className="flex w-full flex-wrap items-center gap-1.5 rounded-xl border border-border bg-surface px-2 py-2 focus-within:ring-2 focus-within:ring-ring"
                  onClick={() => inputRef.current?.focus()}
                >
                  {chips.length > 0 ? (
                    <ul className="flex flex-wrap items-center gap-1.5">
                      {chips.map((chip) => (
                        <li
                          key={chip}
                          className={cn(
                            "flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-[12.5px]",
                            refusals[chip]
                              ? "border-clay text-clay"
                              : "border-border bg-surface-alt text-[var(--text-primary)]",
                          )}
                        >
                          <span className="truncate">{chip}</span>
                          <button
                            type="button"
                            className="flex-none rounded-full px-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label={`Remove ${chip}`}
                            onClick={() => removeChip(chip)}
                            disabled={busy}
                          >
                            &times;
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <input
                    ref={inputRef}
                    type="email"
                    className="min-w-[14ch] flex-1 bg-transparent px-1.5 py-1 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none disabled:opacity-60"
                    placeholder={
                      full
                        ? "That is the maximum"
                        : chips.length === 0
                          ? "colleague@university.edu"
                          : "Add another…"
                    }
                    aria-label={`Email addresses to invite to this ${noun}`}
                    aria-describedby="invite-chip-count"
                    value={draft}
                    // Stay editable while full if something is still in the box,
                    // or a rejected address would be stranded there unfixable.
                    disabled={busy || (full && draft.trim() === "")}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onDraftKeyDown}
                    onBlur={() => commitDraft(draft)}
                    onPaste={(event) => {
                      const text = event.clipboardData.getData("text");
                      if (ADDRESS_SPLIT.test(text)) {
                        event.preventDefault();
                        commitDraft(text);
                      }
                    }}
                  />
                </div>
                <p
                  id="invite-chip-count"
                  className="mt-1 text-[11.5px] text-[var(--text-muted)]"
                >
                  {chips.length} of {ORG_INVITE_BATCH_MAX}
                  {full ? " — remove one to add another." : ""}
                </p>
              </div>
            ) : tab === "link" ? (
              <div className="flex flex-wrap gap-2.5">
                <label className="flex-1 text-[12px] text-[var(--text-secondary)]">
                  Max accounts
                  <input
                    type="number"
                    min={1}
                    max={500}
                    className={INPUT + " mt-1 w-full"}
                    value={maxUses}
                    disabled={busy}
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
                    disabled={busy}
                    onChange={(event) => setExpiryDays(event.target.value)}
                  />
                </label>
              </div>
            ) : null}

            {tab === "member" ? (
              <input
                type="text"
                className={INPUT + " w-full"}
                placeholder="Username"
                aria-label="Username of someone already on Mycelium"
                value={username}
                disabled={busy}
                onChange={(event) => setUsername(event.target.value)}
              />
            ) : null}

            <div className="flex flex-wrap items-end gap-2.5">
              <label className="text-[12px] text-[var(--text-secondary)]">
                Joins as
                <select
                  className={INPUT + " mt-1 block"}
                  value={role}
                  disabled={busy}
                  onChange={(event) => setRole(event.target.value)}
                >
                  {roleOptions.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              {/* The note rides in the email body or the link preview; the
                  roster invitation has nowhere to put one. */}
              {tab === "member" ? null : (
                <input
                  type="text"
                  className={INPUT}
                  placeholder="Optional note"
                  aria-label="Optional note to the invitee"
                  value={message}
                  disabled={busy}
                  onChange={(event) => setMessage(event.target.value)}
                />
              )}
              <button
                type="submit"
                className={PRIMARY_BUTTON}
                disabled={
                  busy ||
                  (tab === "email" && chips.length === 0 && !draft.trim()) ||
                  (tab === "member" && !username.trim())
                }
              >
                {busy
                  ? "Working…"
                  : tab === "link"
                    ? "Create link"
                    : tab === "member"
                      ? "Add to lab"
                      : chips.length > 1
                        ? `Send ${chips.length} invitations`
                        : "Send invitation"}
              </button>
            </div>
          </form>

          {error ? (
            <p className="mt-2 text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}

          {/*
            One polite live region for both halves of the outcome. A batch is
            usually a partial success, so the sent count and the refusals have to
            be readable together rather than as competing alerts.
          */}
          <div aria-live="polite" className="mt-2 space-y-1.5">
            {sent ? (
              <p className="text-[12.5px] text-[var(--text-secondary)]">{sent}</p>
            ) : null}
            {batch && batch.failed.length > 0 ? (
              <div>
                <p className="text-[12.5px] text-[var(--text-secondary)]">
                  {batch.failed.length === 1
                    ? "One address was not invited:"
                    : `${batch.failed.length} addresses were not invited:`}
                </p>
                <ul className="mt-1 space-y-0.5">
                  {batch.failed.map((row) => (
                    <li key={row.email} className="text-[12px] text-clay">
                      <span className="font-medium">{row.email}</span> — {row.detail}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

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
    </>
  );
}

/**
 * The panel in a card, as the lab and department settings rails mount it.
 *
 * A thin wrapper on purpose: the roster's dialog wants the same panel without a
 * card around it, and the only way those two stay identical is for one of them to
 * be the other plus chrome.
 */
export function OrgInviteCard(props: OrgInvitePanelProps) {
  if (!props.canInvite) {
    return null;
  }
  return (
    <Card className="p-5">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Invite members
      </h3>
      <OrgInvitePanel {...props} />
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
