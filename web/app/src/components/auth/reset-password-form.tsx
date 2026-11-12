"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { confirmPasswordReset, verifyResetToken } from "@/lib/auth-client";

const fieldClass =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

const labelClass =
  "block text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]";

/**
 * Spend an emailed reset link on a new password.
 *
 * The link is checked before the form is shown. Discovering that a link expired
 * only after typing a password twice is a bad enough experience to be worth the
 * extra round trip, and the check is cheap.
 */
export function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";

  // A link with no uid or token is dead before any request is made, so that
  // verdict is the initial state rather than something an effect writes in.
  const [linkState, setLinkState] = useState<"checking" | "live" | "dead">(
    uid && token ? "checking" : "dead",
  );
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");

  useEffect(() => {
    if (!uid || !token) {
      return;
    }
    let cancelled = false;
    void verifyResetToken(uid, token)
      .then((valid) => {
        if (!cancelled) {
          setLinkState(valid ? "live" : "dead");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLinkState("dead");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [uid, token]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setError(null);
    setStatus("loading");
    try {
      await confirmPasswordReset(uid, token, password, confirm);
      setStatus("done");
    } catch (caught) {
      setStatus("idle");
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not reset your password. Try again in a moment.",
      );
    }
  }

  if (linkState === "checking") {
    return (
      <p className="text-sm text-[var(--text-secondary)]" role="status">
        Checking your link…
      </p>
    );
  }

  if (linkState === "dead") {
    return (
      <div className="space-y-4">
        <p
          className="rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-3 text-sm text-destructive"
          role="alert"
        >
          That reset link has expired or was already used. Reset links last an
          hour and work once.
        </p>
        <a
          href="/forgot-password"
          className="block w-full rounded-full bg-primary px-4 py-3 text-center text-sm font-semibold text-primary-foreground transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Ask for a new link
        </a>
      </div>
    );
  }

  if (status === "done") {
    return (
      <div className="space-y-4">
        <p
          className="rounded-xl border border-primary/30 bg-primary/10 px-3.5 py-3 text-sm text-[var(--text-primary)]"
          role="status"
        >
          Your password has been reset. Every other device signed in with the old
          one has been signed out.
        </p>
        <Button
          className="w-full rounded-full"
          size="lg"
          onClick={() => router.replace("/login")}
        >
          Sign in
        </Button>
      </div>
    );
  }

  const busy = status === "loading";

  return (
    <form
      method="post"
      action="/reset-password/fallback"
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
        <label className={labelClass} htmlFor="new-password">
          New password
        </label>
        <input
          id="new-password"
          name="new-password"
          type="password"
          autoComplete="new-password"
          placeholder="••••••••"
          required
          value={password}
          disabled={busy}
          onChange={(event) => setPassword(event.target.value)}
          className={fieldClass}
        />
      </div>

      <div className="space-y-1.5">
        <label className={labelClass} htmlFor="confirm-password">
          Confirm password
        </label>
        <input
          id="confirm-password"
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          placeholder="••••••••"
          required
          value={confirm}
          disabled={busy}
          onChange={(event) => setConfirm(event.target.value)}
          className={fieldClass}
        />
      </div>

      <Button
        className="mt-2 w-full rounded-full"
        disabled={busy}
        size="lg"
        type="submit"
      >
        {busy ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
