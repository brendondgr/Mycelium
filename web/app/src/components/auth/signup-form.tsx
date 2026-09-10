"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { checkEmailAvailable, register } from "@/lib/auth-client";
import type { AccountType } from "@/lib/auth-types";
import { cn } from "@/lib/utils";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "mb-1.5 block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

const errorClass = "mt-1.5 text-xs font-medium text-destructive";

function IconPersonal() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}

function IconLab() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2">
      <path d="M9 3v6l-5 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-9V3" />
      <path d="M8 3h8" />
    </svg>
  );
}

function IconDepartment() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2">
      <path d="M3 21V8l9-5 9 5v13" />
      <path d="M3 21h18M9 21v-6h6v6" />
    </svg>
  );
}

const ACCOUNT_OPTIONS: {
  value: AccountType;
  title: string;
  caption: string;
  icon: React.ReactNode;
}[] = [
  { value: "personal", title: "Personal", caption: "Spore · just you", icon: <IconPersonal /> },
  { value: "lab", title: "Lab", caption: "Lab · you lead a PI group", icon: <IconLab /> },
  { value: "department", title: "Department", caption: "Canopy · institutional", icon: <IconDepartment /> },
];

type FieldKey =
  | "username"
  | "email"
  | "password"
  | "password_confirm"
  | "org_name"
  | "access_code";

type FieldErrors = Partial<Record<FieldKey, string>>;

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function SignupForm() {
  const router = useRouter();
  const [accountType, setAccountType] = useState<AccountType>("personal");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [orgName, setOrgName] = useState("");
  const [institution, setInstitution] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [emailTaken, setEmailTaken] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");

  const isBusy = status === "loading" || status === "success";
  const needsOrgName = accountType === "lab" || accountType === "department";
  const orgLabel = accountType === "lab" ? "Lab name" : "Department name";

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (!accessCode.trim()) {
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
    if (needsOrgName && !orgName.trim()) {
      errors.org_name =
        accountType === "lab"
          ? "A lab name is required."
          : "A department name is required.";
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
   * sign-up gets to ask — so nothing is checked until there is one to send.
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
        account_type: accountType,
        access_code: accessCode.trim(),
        ...(needsOrgName ? { org_name: orgName.trim() } : {}),
        ...(accountType === "department"
          ? { institution: institution.trim() }
          : {}),
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

      <fieldset>
        <legend className={labelClass}>Account type</legend>
        <div
          role="radiogroup"
          aria-label="Account type"
          className="grid grid-cols-3 gap-2.5"
        >
          {ACCOUNT_OPTIONS.map((option) => {
            const selected = accountType === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={isBusy}
                onClick={() => {
                  setAccountType(option.value);
                  setFieldErrors((prev) => ({ ...prev, org_name: undefined }));
                }}
                className={cn(
                  "flex flex-col gap-3 rounded-2xl border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60",
                  selected
                    ? "border-primary"
                    : "border-border bg-card hover:border-brand-secondary",
                )}
                style={
                  selected
                    ? {
                        backgroundColor:
                          "color-mix(in srgb, var(--primary) 8%, var(--card))",
                      }
                    : undefined
                }
              >
                <span className="flex items-start justify-between">
                  <span
                    className="flex h-9 w-9 items-center justify-center rounded-lg"
                    style={{
                      background:
                        "color-mix(in srgb, var(--primary) 12%, var(--card))",
                    }}
                  >
                    {option.icon}
                  </span>
                  {selected ? (
                    <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    </span>
                  ) : null}
                </span>
                <span>
                  <span className="block text-sm font-semibold text-[var(--text-primary)]">
                    {option.title}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-[var(--text-muted)]">
                    {option.caption}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      {needsOrgName ? (
        <div>
          <label className={labelClass} htmlFor="org_name">
            {orgLabel}
          </label>
          <input
            id="org_name"
            name="org_name"
            type="text"
            placeholder={
              accountType === "lab" ? "e.g. Rivera Lab" : "e.g. Molecular Systems"
            }
            value={orgName}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.org_name)}
            aria-describedby={fieldErrors.org_name ? "org_name-error" : undefined}
            onChange={(event) => setOrgName(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.org_name ? (
            <p className={errorClass} id="org_name-error" role="alert">
              {fieldErrors.org_name}
            </p>
          ) : null}
        </div>
      ) : null}

      {accountType === "department" ? (
        <div>
          <label className={labelClass} htmlFor="institution">
            Institution
          </label>
          <input
            id="institution"
            name="institution"
            type="text"
            placeholder="Northgate University"
            value={institution}
            disabled={isBusy}
            onChange={(event) => setInstitution(event.target.value)}
            className={fieldClass}
          />
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
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            onChange={(event) => setEmail(event.target.value)}
            className={fieldClass}
          />
          {fieldErrors.email ? (
            <p className={errorClass} id="email-error" role="alert">
              {fieldErrors.email}
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
            : "Create account & continue"}
      </Button>

      <p className="text-center text-sm text-[var(--text-secondary)]">
        Already have an account?{" "}
        <a
          className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="/login"
        >
          Sign in
        </a>
      </p>
    </form>
  );
}
