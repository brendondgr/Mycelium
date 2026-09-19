"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { AmbientSettingsCard } from "@/components/portal/ambient/ambient-settings-card";
import { CollaborationSettingsCard } from "@/components/portal/collab/collaboration-settings-card";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { BillingSection } from "@/components/portal/sections/billing-section";
import { Button } from "@/components/ui/button";
import { InstitutionFromEmail } from "@/components/ui/institution-from-email";
import {
  changeEmail,
  changePassword,
  getAccount,
  requestPasswordChange,
  resendVerificationCode,
  updateAccount,
  verifyEmailCode,
} from "@/lib/auth-client";
import type { AccountDetails } from "@/lib/auth-types";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

const TITLES: { value: string; label: string }[] = [
  { value: "student", label: "Student" },
  { value: "postdoc", label: "Postdoc" },
  { value: "researcher", label: "Researcher" },
  { value: "pi", label: "PI" },
  { value: "staff", label: "Staff" },
];

/**
 * The Account page: everything tied to the person, then everything tied to the
 * money.
 *
 * The two halves are one page because they answer the same question — "what is
 * true of my account?" — and were previously two places, one of which (Billing)
 * had no way in from the user menu at all.
 */
export function AccountSection() {
  const [account, setAccount] = React.useState<AccountDetails | null>(null);
  const [failed, setFailed] = React.useState(false);

  const load = React.useCallback(() => {
    getAccount()
      .then((next) => {
        setAccount(next);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  React.useEffect(load, [load]);

  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title="Account"
        subtitle="Who you are on Mycelium, how we reach you, and what your plan covers."
      />

      {failed ? (
        <Card className="mb-[22px] p-[22px]">
          <p className="text-sm text-[var(--text-secondary)]">
            Couldn&apos;t load your account. Refresh the page to try again.
          </p>
        </Card>
      ) : null}

      <div className="mb-9 grid grid-cols-1 gap-[22px] lg:grid-cols-2 lg:items-start">
        {/* Keyed on whether the account has arrived, so the form mounts once
            with real initial values instead of syncing them in through an
            effect. A later save changes the values, not the key, so typing is
            never interrupted by a remount. */}
        <IdentityCard
          key={account ? "loaded" : "loading"}
          account={account}
          onSaved={setAccount}
        />
        <div className="flex flex-col gap-[22px]">
          <EmailCard account={account} onChanged={setAccount} />
          <PasswordCard email={account?.email ?? ""} />
        </div>
      </div>

      <CollaborationSettingsCard />

      <AmbientSettingsCard />

      <BillingSection />
    </div>
  );
}

// -- name, affiliation, career stage ------------------------------------------

function IdentityCard({
  account,
  onSaved,
}: {
  account: AccountDetails | null;
  onSaved: (next: AccountDetails) => void;
}) {
  const [firstName, setFirstName] = React.useState(account?.first_name ?? "");
  const [lastName, setLastName] = React.useState(account?.last_name ?? "");
  const [title, setTitle] = React.useState(
    account?.academic_title ?? "researcher",
  );
  const [state, setState] = React.useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = React.useState<string | null>(null);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setState("saving");
    try {
      const next = await updateAccount({
        first_name: firstName,
        last_name: lastName,
        academic_title: title,
      });
      onSaved(next);
      setState("saved");
    } catch (caught) {
      setState("idle");
      setError(caught instanceof Error ? caught.message : "Could not save.");
    }
  }

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Account management
      </h2>
      <p className="mb-4 text-sm text-[var(--text-secondary)]">
        Your name and affiliation. These appear to the labs and departments you
        belong to. Your affiliation comes from your verified email.
      </p>

      <form className="space-y-4" onSubmit={save} noValidate>
        {error ? (
          <p
            className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="first-name">
              First name
            </label>
            <input
              id="first-name"
              className={fieldClass}
              value={firstName}
              disabled={!account}
              onChange={(event) => setFirstName(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="last-name">
              Last name
            </label>
            <input
              id="last-name"
              className={fieldClass}
              value={lastName}
              disabled={!account}
              onChange={(event) => setLastName(event.target.value)}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <p className={labelClass} id="affiliation-label">
            Affiliation
          </p>
          <InstitutionFromEmail
            account={account}
            labelledBy="affiliation-label"
          />
        </div>

        <div className="space-y-1.5">
          <label className={labelClass} htmlFor="academic-title">
            Career stage
          </label>
          <select
            id="academic-title"
            className={fieldClass}
            value={title}
            disabled={!account}
            onChange={(event) => setTitle(event.target.value)}
          >
            {TITLES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className={labelClass} htmlFor="account-username">
            Username
          </label>
          <input
            id="account-username"
            className={fieldClass}
            value={account?.username ?? ""}
            readOnly
            disabled
          />
          <p className="text-xs text-[var(--text-muted)]">
            Your username is fixed. Lab invitations and the activity log resolve
            against it.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            className="rounded-full"
            type="submit"
            disabled={!account || state === "saving"}
          >
            {state === "saving" ? "Saving…" : "Save changes"}
          </Button>
          {state === "saved" ? (
            <span className="text-sm font-medium text-primary" role="status">
              Saved
            </span>
          ) : null}
        </div>
      </form>
    </Card>
  );
}

// -- email address + the code that activates the account -----------------------

function EmailCard({
  account,
  onChanged,
}: {
  account: AccountDetails | null;
  onChanged: (next: AccountDetails) => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [newEmail, setNewEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  const pending = account?.pending_email ?? "";
  const verified = account?.is_verified ?? false;

  async function startChange(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await changeEmail(newEmail.trim(), password);
      setEditing(false);
      setPassword("");
      setNotice(`We sent a code to ${newEmail.trim()}. Enter it below.`);
      onChanged({ ...(account as AccountDetails), pending_email: newEmail.trim() });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not change your email.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const next = await verifyEmailCode(code.trim());
      onChanged(next);
      setCode("");
      setNotice("Your email is verified and your account is active.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not verify that code.");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setBusy(true);
    try {
      const { email } = await resendVerificationCode();
      setNotice(`We sent a new code to ${email}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send a new code.");
    } finally {
      setBusy(false);
    }
  }

  const needsCode = Boolean(pending) || !verified;

  return (
    <Card className="p-[22px]">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          Email address
        </h2>
        {account ? (
          <span
            className={
              verified
                ? "rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary"
                : "rounded-full bg-accent/15 px-2.5 py-1 text-[11px] font-semibold text-[var(--text-primary)]"
            }
          >
            {verified ? "Verified" : "Not verified"}
          </span>
        ) : null}
      </div>
      <p className="mb-4 text-sm text-[var(--text-secondary)]">
        {account?.email || "Loading…"}
      </p>

      {!verified && account ? (
        <p className="mb-4 rounded-xl border border-accent/40 bg-accent/10 px-3.5 py-3 text-sm text-[var(--text-primary)]">
          Verifying your email activates your account. Until then you can browse,
          but you cannot create a lab or department, fill in either&apos;s
          profile, or invite anyone.
        </p>
      ) : null}

      {error ? (
        <p
          className="mb-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          className="mb-4 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2.5 text-sm text-[var(--text-primary)]"
          role="status"
        >
          {notice}
        </p>
      ) : null}

      {pending ? (
        <p className="mb-4 text-sm text-[var(--text-secondary)]">
          Waiting on <strong>{pending}</strong> to confirm. Your current address
          stays in place until it does.
        </p>
      ) : null}

      {needsCode && account ? (
        <form className="mb-4 space-y-3" onSubmit={submitCode} noValidate>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="verification-code">
              Verification code
            </label>
            <input
              id="verification-code"
              className={fieldClass}
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={code}
              disabled={busy}
              onChange={(event) =>
                setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              className="rounded-full"
              type="submit"
              disabled={busy || code.length < 6}
            >
              {busy ? "Checking…" : "Verify"}
            </Button>
            <button
              type="button"
              onClick={() => void resend()}
              disabled={busy}
              className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
            >
              Send a new code
            </button>
          </div>
        </form>
      ) : null}

      {editing ? (
        <form className="space-y-3" onSubmit={startChange} noValidate>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="new-email">
              New email
            </label>
            <input
              id="new-email"
              type="email"
              autoComplete="email"
              className={fieldClass}
              value={newEmail}
              disabled={busy}
              onChange={(event) => setNewEmail(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="email-password">
              Current password
            </label>
            <input
              id="email-password"
              type="password"
              autoComplete="current-password"
              className={fieldClass}
              value={password}
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button className="rounded-full" type="submit" disabled={busy}>
              {busy ? "Sending…" : "Send code"}
            </Button>
            <button
              type="button"
              className="text-sm font-medium text-[var(--text-secondary)] hover:underline"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setEditing(true)}
          disabled={!account}
        >
          Change email address
        </button>
      )}
    </Card>
  );
}

// -- password ------------------------------------------------------------------

function PasswordCard({ email }: { email: string }) {
  const [code, setCode] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [stage, setStage] = React.useState<"start" | "confirm" | "done">("start");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function sendCode() {
    setError(null);
    setBusy(true);
    try {
      await requestPasswordChange();
      setStage("confirm");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not send a confirmation code.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (next !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(code, next, confirm);
      setCode("");
      setNext("");
      setConfirm("");
      setStage("done");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not change your password.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Password
      </h2>
      <p className="mb-4 text-sm text-[var(--text-secondary)]">
        We email you a code to confirm it is you. You do not need your current
        password. Changing it signs every other device out; this one stays.
      </p>

      {error ? (
        <p
          className="mb-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {stage === "done" ? (
        <div className="space-y-3">
          <p
            className="rounded-xl border border-primary/30 bg-primary/10 px-3 py-2.5 text-sm text-[var(--text-primary)]"
            role="status"
          >
            Your password has been changed.
          </p>
          <button
            type="button"
            className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setStage("start")}
          >
            Change it again
          </button>
        </div>
      ) : stage === "start" ? (
        <div className="space-y-3">
          <Button
            className="rounded-full"
            type="button"
            disabled={busy || !email}
            onClick={() => void sendCode()}
          >
            {busy ? "Sending…" : "Email me a code"}
          </Button>
          <p className="text-xs text-[var(--text-muted)]">
            We will send a confirmation code to {email || "your address"}.
          </p>
        </div>
      ) : (
        <form className="space-y-3" onSubmit={save} noValidate>
          <p className="text-sm text-[var(--text-secondary)]">
            We sent a code to <strong>{email}</strong>. Enter it with your new
            password.
          </p>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="password-code">
              Confirmation code
            </label>
            <input
              id="password-code"
              className={fieldClass}
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={code}
              disabled={busy}
              onChange={(event) =>
                setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
            />
          </div>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="next-password">
              New password
            </label>
            <input
              id="next-password"
              type="password"
              autoComplete="new-password"
              className={fieldClass}
              value={next}
              disabled={busy}
              onChange={(event) => setNext(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className={labelClass} htmlFor="confirm-new-password">
              Confirm new password
            </label>
            <input
              id="confirm-new-password"
              type="password"
              autoComplete="new-password"
              className={fieldClass}
              value={confirm}
              disabled={busy}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              className="rounded-full"
              type="submit"
              disabled={busy || code.length < 6 || !next}
            >
              {busy ? "Saving…" : "Change password"}
            </Button>
            <button
              type="button"
              onClick={() => void sendCode()}
              disabled={busy}
              className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
            >
              Send a new code
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}
