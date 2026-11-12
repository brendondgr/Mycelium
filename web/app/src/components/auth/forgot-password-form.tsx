"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { requestPasswordReset } from "@/lib/auth-client";
import { useHydrated } from "@/lib/use-hydrated";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

/**
 * Ask for a reset link.
 *
 * The confirmation deliberately does not say whether the address is registered.
 * The backend answers identically either way so the endpoint cannot be walked to
 * find out who has an account, and a screen that said "no such account" would
 * hand back exactly what the API withholds.
 */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "sent">("idle");
  const hydrated = useHydrated();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) {
      setError("Enter the email address on your account.");
      return;
    }
    setError(null);
    setStatus("loading");
    try {
      await requestPasswordReset(email.trim());
      setStatus("sent");
    } catch (caught) {
      setStatus("idle");
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not send a reset link. Try again in a moment.",
      );
    }
  }

  if (status === "sent") {
    return (
      <div className="space-y-4">
        <p
          className="rounded-xl border border-primary/30 bg-primary/10 px-3.5 py-3 text-sm text-[var(--text-primary)]"
          role="status"
        >
          If that email belongs to a Mycelium account, a reset link is on its
          way. It expires in an hour.
        </p>
        <p className="text-sm text-[var(--text-secondary)]">
          Nothing in your inbox after a few minutes? Check the spam folder, then
          try again.
        </p>
        <a
          href="/login"
          className="block w-full rounded-full border border-border bg-surface px-4 py-3 text-center text-sm font-semibold text-[var(--text-primary)] transition hover:border-brand-secondary hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Back to sign in
        </a>
      </div>
    );
  }

  return (
    <form
      method="post"
      action="/forgot-password/fallback"
      className="space-y-4"
      onSubmit={submit}
      noValidate
    >
      {error ? (
        <p
          className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div className="space-y-1.5">
        <label className={labelClass} htmlFor="reset-email">
          Email
        </label>
        <input
          id="reset-email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@university.edu"
          required
          value={email}
          disabled={status === "loading"}
          onChange={(event) => setEmail(event.target.value)}
          className={fieldClass}
        />
      </div>

      <Button
        className="mt-2 w-full rounded-full"
        disabled={!hydrated || status === "loading"}
        size="lg"
        type="submit"
      >
        {status === "loading" ? "Sending…" : "Send reset link"}
      </Button>

      <a
        href="/login"
        className="block text-center text-sm font-medium text-brand-secondary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Back to sign in
      </a>
    </form>
  );
}
