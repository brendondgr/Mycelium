"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { login } from "@/lib/auth-client";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

export function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    username?: string;
    password?: string;
  }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitCredentials();
  }

  async function submitCredentials() {
    setFormError(null);

    const nextFieldErrors: { username?: string; password?: string } = {};
    if (!username.trim()) {
      nextFieldErrors.username = "Username is required.";
    }
    if (!password) {
      nextFieldErrors.password = "Password is required.";
    }
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setFieldErrors({});
    setStatus("loading");

    try {
      await login(username.trim(), password);
      setStatus("success");
      router.replace("/app/overview");
      router.refresh();
    } catch (error) {
      setStatus("idle");
      setFormError(
        error instanceof Error
          ? error.message
          : "Sign-in failed. Check your connection and try again.",
      );
    }
  }

  const isBusy = status === "loading" || status === "success";

  return (
    <form
      className="space-y-4"
      method="post"
      action="/login"
      onSubmit={handleSubmit}
      noValidate
      aria-busy={isBusy}
    >
      {formError ? (
        <p
          className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
            className="flex-none"
          >
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          {formError}
        </p>
      ) : null}

      <div className="space-y-1.5">
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
          <p className="text-sm text-destructive" id="username-error" role="alert">
            {fieldErrors.username}
          </p>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className={labelClass} htmlFor="password">
            Password
          </label>
          <span className="text-xs font-medium text-brand-secondary">Forgot?</span>
        </div>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          required
          value={password}
          disabled={isBusy}
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={fieldErrors.password ? "password-error" : undefined}
          onChange={(event) => setPassword(event.target.value)}
          className={fieldClass}
        />
        {fieldErrors.password ? (
          <p className="text-sm text-destructive" id="password-error" role="alert">
            {fieldErrors.password}
          </p>
        ) : null}
      </div>

      <Button
        className="mt-2 w-full rounded-full"
        disabled={isBusy}
        size="lg"
        type="submit"
      >
        {status === "loading"
          ? "Signing in…"
          : status === "success"
            ? "Signed in"
            : "Sign in"}
      </Button>

      <div className="flex items-center gap-3 py-1 text-xs font-medium tracking-wide text-[var(--text-muted)]">
        <span className="h-px flex-1 bg-[var(--divider)]" />
        NEW TO MYCELIUM?
        <span className="h-px flex-1 bg-[var(--divider)]" />
      </div>

      <a
        href="/signup"
        className="block w-full rounded-full border border-border bg-surface px-4 py-3 text-center text-sm font-semibold text-[var(--text-primary)] transition hover:border-brand-secondary hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Create an account
      </a>
    </form>
  );
}
