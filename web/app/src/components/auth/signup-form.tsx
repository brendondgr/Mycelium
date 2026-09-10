"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { checkEmailAvailable, previewInvite, register } from "@/lib/auth-client";
import type { InvitePreview } from "@/lib/auth-types";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "mb-1.5 block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

const errorClass = "mt-1.5 text-xs font-medium text-destructive";

type FieldKey =
  | "username"
  | "email"
  | "password"
  | "password_confirm"
  | "access_code";

type FieldErrors = Partial<Record<FieldKey, string>>;

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite")?.trim() ?? "";

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [emailTaken, setEmailTaken] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");
  const [invite, setInvite] = useState<InvitePreview | null>(null);

  const isBusy = status === "loading" || status === "success";
  // An email invitation is spendable by exactly one address, so the form fills
  // that address in and stops anyone editing it into a refusal.
  const lockedEmail = invite?.kind === "email" ? invite.email : "";
  // A live invitation is itself an invitation, so no beta code is asked for.
  const needsAccessCode = invite === null;

  /**
   * Read what the `?invite=` token leads to, so the form can name the lab or
   * department this person is joining before they fill anything in.
   *
   * A dead token is left to the join page to explain. Someone who arrived here
   * anyway can still sign up the ordinary way with a beta code, and blocking a
   * form that would have worked is the worse failure.
   */
  useEffect(() => {
    if (!inviteToken) {
      return;
    }
    let cancelled = false;
    void previewInvite(inviteToken)
      .then((preview) => {
        if (cancelled) {
          return;
        }
        setInvite(preview);
        if (preview.kind === "email") {
          setEmail(preview.email);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [inviteToken]);

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (needsAccessCode && !accessCode.trim()) {
      errors.access_code = "Enter your verification code.";
    }
    if (!username.trim()) {
      errors.username = "Choose a username.";
    }
    if (!EMAIL_RE.test(email.trim())) {
      errors.email = "Enter a valid email.";
    }
    if (password.length < 8) {
      errors.password = "At least 8 characters.";
    }
    if (!confirm || confirm !== password) {
      errors.password_confirm = "Passwords do not match.";
    }
    return errors;
  }

  /**
   * Say that an address is already registered before the form is submitted.
   *
   * Watches both the address and the invite code rather than firing on one
   * field's blur, because the code sits at the bottom of the form: whichever the
   * person fills in last is the one that completes the pair. The endpoint is
   * gated on that code — it is an account-enumeration oracle, and only a genuine
   * sign-up gets to ask — so nothing is checked until there is one to send. An
   * invited sign-up has no code, so the check stays quiet and the server answers.
   */
  useEffect(() => {
    const address = email.trim();
    const code = accessCode.trim();
    if (!EMAIL_RE.test(address) || !code) {
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void checkEmailAvailable(address, code)
        .then((available) => {
          if (!cancelled) {
            setEmailTaken(!available);
          }
        })
        // A failed check is not a failed sign-up — registration re-checks server
        // side and refuses there. Say nothing rather than block the form.
        .catch(() => undefined);
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [email, accessCode]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  async function submit() {
    setFormError(null);
    const nextErrors = validate();
    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors);
      return;
    }
    setFieldErrors({});
    setStatus("loading");

    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        password_confirm: confirm,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        ...(inviteToken ? { invite_token: inviteToken } : {}),
        ...(needsAccessCode ? { access_code: accessCode.trim() } : {}),
      });
      setStatus("success");
      router.replace("/app/onboarding");
      router.refresh();
    } catch (error) {
      setStatus("idle");
      setFormError(
        error instanceof Error
          ? error.message
          : "Sign-up failed. Check your details and try again.",
      );
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit} noValidate aria-busy={isBusy}>
      {formError ? (
        <p
          className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="flex-none">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          {formError}
        </p>
      ) : null}

      {invite ? (
        <div
          className="rounded-2xl border border-primary/30 px-3.5 py-3"
          style={{
            backgroundColor: "color-mix(in srgb, var(--primary) 7%, var(--card))",
          }}
        >
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Joining {invite.org_name}
          </p>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {invite.invited_by
              ? `${invite.invited_by} invited you`
              : "You were invited"}{" "}
            to this {invite.org_kind}. Finish signing up and you are in.
          </p>
          {invite.message ? (
            <p className="mt-2 border-l-2 border-primary/40 pl-2.5 text-xs italic text-[var(--text-secondary)]">
              {invite.message}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className={labelClass} htmlFor="first_name">
            First name
          </label>
          <input
            id="first_name"
            name="first_name"
            type="text"
            autoComplete="given-name"
            placeholder="Jamie"
            value={firstName}
            disabled={isBusy}
            onChange={(event) => setFirstName(event.target.value)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="last_name">
            Last name
          </label>
          <input
            id="last_name"
            name="last_name"
            type="text"
            autoComplete="family-name"
            placeholder="Rivera"
            value={lastName}
            disabled={isBusy}
            onChange={(event) => setLastName(event.target.value)}
            className={fieldClass}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className={labelClass} htmlFor="username">
            Username
          </label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            placeholder="jrivera"
            required
            value={username}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.username)}
            aria-describedby={fieldErrors.username ? "username-error" : undefined}
            onChange={(event) => setUsername(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.username ? (
            <p className={errorClass} id="username-error" role="alert">
              {fieldErrors.username}
            </p>
          ) : null}
        </div>
        <div>
          <label className={labelClass} htmlFor="email">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="jamie@lab.edu"
            required
            value={email}
            readOnly={Boolean(lockedEmail)}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={
              fieldErrors.email
                ? "email-error"
                : lockedEmail
                  ? "email-locked"
                  : undefined
            }
            onChange={(event) => setEmail(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.email ? (
            <p className={errorClass} id="email-error" role="alert">
              {fieldErrors.email}
            </p>
          ) : null}
          {lockedEmail ? (
            <p className="mt-1.5 text-xs text-[var(--text-muted)]" id="email-locked">
              Your invitation was sent here, so sign-up is tied to this address.
            </p>
          ) : null}
          {/* Gated on the pair still being complete rather than cleared from the
              effect: a stale "taken" must not survive the address being edited. */}
          {!fieldErrors.email &&
          emailTaken &&
          EMAIL_RE.test(email.trim()) &&
          accessCode.trim() ? (
            <p className={errorClass} role="alert">
              An account already uses that email.{" "}
              <a href="/login" className="underline underline-offset-2">
                Sign in
              </a>{" "}
              or{" "}
              <a href="/forgot-password" className="underline underline-offset-2">
                reset your password
              </a>
              .
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className={labelClass} htmlFor="password">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            placeholder="8+ characters"
            required
            value={password}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.password)}
            aria-describedby={fieldErrors.password ? "password-error" : undefined}
            onChange={(event) => setPassword(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.password ? (
            <p className={errorClass} id="password-error" role="alert">
              {fieldErrors.password}
            </p>
          ) : null}
        </div>
        <div>
          <label className={labelClass} htmlFor="password_confirm">
            Confirm
          </label>
          <input
            id="password_confirm"
            name="password_confirm"
            type="password"
            autoComplete="new-password"
            placeholder="Re-enter password"
            required
            value={confirm}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.password_confirm)}
            aria-describedby={
              fieldErrors.password_confirm ? "password_confirm-error" : undefined
            }
            onChange={(event) => setConfirm(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.password_confirm ? (
            <p className={errorClass} id="password_confirm-error" role="alert">
              {fieldErrors.password_confirm}
            </p>
          ) : null}
        </div>
      </div>

      {needsAccessCode ? (
        <div>
          <label className={labelClass} htmlFor="access_code">
            Verification code
          </label>
          <input
            id="access_code"
            name="access_code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="6-digit code"
            required
            value={accessCode}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.access_code)}
            aria-describedby={
              fieldErrors.access_code ? "access_code-error" : "access_code-hint"
            }
            onChange={(event) => setAccessCode(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.access_code ? (
            <p className={errorClass} id="access_code-error" role="alert">
              {fieldErrors.access_code}
            </p>
          ) : (
            <p className="mt-1.5 text-xs text-[var(--text-muted)]" id="access_code-hint">
              Mycelium is invite-only right now — use the code you were given.
            </p>
          )}
        </div>
      ) : null}

      <Button
        className="mt-2 w-full rounded-full"
        disabled={isBusy}
        size="lg"
        type="submit"
      >
        {status === "loading"
          ? "Creating account…"
          : status === "success"
            ? "Account created"
            : invite
              ? `Create account & join ${invite.org_name}`
              : "Create account & continue"}
      </Button>

      <p className="text-center text-sm text-[var(--text-secondary)]">
        Already have an account?{" "}
        <a
          className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href={inviteToken ? `/login?next=/join/${inviteToken}` : "/login"}
        >
          Sign in
        </a>
      </p>
    </form>
  );
}
