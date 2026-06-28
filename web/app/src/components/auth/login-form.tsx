"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { login } from "@/lib/auth-client";

const landingUrl =
  process.env.NEXT_PUBLIC_LANDING_URL ?? "http://localhost:11050";

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
      router.replace("/app");
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
      className="space-y-5"
      method="post"
      action="/login"
      onSubmit={handleSubmit}
      noValidate
      aria-busy={isBusy}
    >
      {formError ? (
        <p
          className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
        >
          {formError}
        </p>
      ) : null}

      <div className="space-y-2">
        <label
          className="text-sm font-medium text-[var(--text-primary)]"
          htmlFor="username"
        >
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
          className="min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        />
        {fieldErrors.username ? (
          <p className="text-sm text-destructive" id="username-error" role="alert">
            {fieldErrors.username}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <label
          className="text-sm font-medium text-[var(--text-primary)]"
          htmlFor="password"
        >
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          disabled={isBusy}
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={fieldErrors.password ? "password-error" : undefined}
          onChange={(event) => setPassword(event.target.value)}
          className="min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        />
        {fieldErrors.password ? (
          <p className="text-sm text-destructive" id="password-error" role="alert">
            {fieldErrors.password}
          </p>
        ) : null}
      </div>

      <Button
        className="w-full"
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

      <p className="text-center text-sm text-[var(--text-secondary)]">
        New to Mycelium?{" "}
        <a
          className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="/signup"
        >
          Create an account
        </a>
      </p>

      <p className="text-center text-sm text-[var(--text-muted)]">
        <a
          className="underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href={landingUrl}
        >
          Back to the public site
        </a>
      </p>
    </form>
  );
}
