"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { register } from "@/lib/auth-client";
import type { AccountType } from "@/lib/auth-types";
import { cn } from "@/lib/utils";

const inputClass =
  "min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60";

const labelClass = "text-sm font-medium text-[var(--text-primary)]";

const ACCOUNT_OPTIONS: {
  value: AccountType;
  title: string;
  caption: string;
}[] = [
  { value: "personal", title: "Personal", caption: "Spore · just you" },
  { value: "lab", title: "Lab", caption: "Lab · you lead a PI group" },
  {
    value: "department",
    title: "Department",
    caption: "Canopy · institutional",
  },
];

type FieldKey =
  | "username"
  | "email"
  | "password"
  | "password_confirm"
  | "org_name";

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
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");

  const isBusy = status === "loading" || status === "success";
  const needsOrgName = accountType === "lab" || accountType === "department";
  const orgLabel = accountType === "lab" ? "Lab name" : "Department name";

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
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
    <form className="space-y-5" onSubmit={handleSubmit} noValidate aria-busy={isBusy}>
      {formError ? (
        <p
          className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
        >
          {formError}
        </p>
      ) : null}

      <fieldset className="space-y-2">
        <legend className={labelClass}>Account type</legend>
        <div
          role="radiogroup"
          aria-label="Account type"
          className="grid grid-cols-1 gap-3 sm:grid-cols-3"
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
                onClick={() => setAccountType(option.value)}
                className={cn(
                  "flex flex-col gap-1 rounded-lg border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60",
                  selected
                    ? "border-primary bg-secondary"
                    : "border-border bg-card hover:border-brand-secondary",
                )}
              >
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {option.title}
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  {option.caption}
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      {needsOrgName ? (
        <div className="space-y-2">
          <label className={labelClass} htmlFor="org_name">
            {orgLabel}
          </label>
          <input
            id="org_name"
            name="org_name"
            type="text"
            value={orgName}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.org_name)}
            aria-describedby={fieldErrors.org_name ? "org_name-error" : undefined}
            onChange={(event) => setOrgName(event.target.value)}
            className={inputClass}
          />
          {fieldErrors.org_name ? (
            <p className="text-sm text-destructive" id="org_name-error" role="alert">
              {fieldErrors.org_name}
            </p>
          ) : null}
        </div>
      ) : null}

      {accountType === "department" ? (
        <div className="space-y-2">
          <label className={labelClass} htmlFor="institution">
            Institution <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <input
            id="institution"
            name="institution"
            type="text"
            value={institution}
            disabled={isBusy}
            onChange={(event) => setInstitution(event.target.value)}
            className={inputClass}
          />
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label className={labelClass} htmlFor="first_name">
            First name <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <input
            id="first_name"
            name="first_name"
            type="text"
            autoComplete="given-name"
            value={firstName}
            disabled={isBusy}
            onChange={(event) => setFirstName(event.target.value)}
            className={inputClass}
          />
        </div>
        <div className="space-y-2">
          <label className={labelClass} htmlFor="last_name">
            Last name <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <input
            id="last_name"
            name="last_name"
            type="text"
            autoComplete="family-name"
            value={lastName}
            disabled={isBusy}
            onChange={(event) => setLastName(event.target.value)}
            className={inputClass}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label className={labelClass} htmlFor="username">
            Username
          </label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            value={username}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.username)}
            aria-describedby={fieldErrors.username ? "username-error" : undefined}
            onChange={(event) => setUsername(event.target.value)}
            className={inputClass}
          />
          {fieldErrors.username ? (
            <p className="text-sm text-destructive" id="username-error" role="alert">
              {fieldErrors.username}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <label className={labelClass} htmlFor="email">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            onChange={(event) => setEmail(event.target.value)}
            className={inputClass}
          />
          {fieldErrors.email ? (
            <p className="text-sm text-destructive" id="email-error" role="alert">
              {fieldErrors.email}
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label className={labelClass} htmlFor="password">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.password)}
            aria-describedby={fieldErrors.password ? "password-error" : undefined}
            onChange={(event) => setPassword(event.target.value)}
            className={inputClass}
          />
          {fieldErrors.password ? (
            <p className="text-sm text-destructive" id="password-error" role="alert">
              {fieldErrors.password}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <label className={labelClass} htmlFor="password_confirm">
            Confirm password
          </label>
          <input
            id="password_confirm"
            name="password_confirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            disabled={isBusy}
            aria-invalid={Boolean(fieldErrors.password_confirm)}
            aria-describedby={
              fieldErrors.password_confirm ? "password_confirm-error" : undefined
            }
            onChange={(event) => setConfirm(event.target.value)}
            className={inputClass}
          />
          {fieldErrors.password_confirm ? (
            <p
              className="text-sm text-destructive"
              id="password_confirm-error"
              role="alert"
            >
              {fieldErrors.password_confirm}
            </p>
          ) : null}
        </div>
      </div>

      <Button className="w-full" disabled={isBusy} size="lg" type="submit">
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
