"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { acceptInvite, InviteDeadError, previewInvite } from "@/lib/auth-client";
import type { InviteDeadReason, InvitePreview } from "@/lib/auth-types";

/** What to say about a link that will never work again. */
const DEAD_HEADINGS: Record<InviteDeadReason, string> = {
  invalid: "This link is not an invitation",
  revoked: "This invitation was withdrawn",
  expired: "This invitation has expired",
  exhausted: "This invitation is used up",
  wrong_email: "This invitation is for someone else",
};

type State =
  | { phase: "loading" }
  | { phase: "dead"; reason: InviteDeadReason; detail: string }
  | { phase: "ready"; invite: InvitePreview }
  | { phase: "joined"; invite: InvitePreview };

export function JoinInvitation({
  token,
  signedIn,
}: {
  token: string;
  signedIn: boolean;
}) {
  const router = useRouter();
  const [state, setState] = useState<State>({ phase: "loading" });
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void previewInvite(token)
      .then((invite) => {
        if (!cancelled) {
          setState({ phase: "ready", invite });
        }
      })
      .catch((cause) => {
        if (cancelled) {
          return;
        }
        setState({
          phase: "dead",
          reason: cause instanceof InviteDeadError ? cause.reason : "invalid",
          detail:
            cause instanceof Error
              ? cause.message
              : "This invitation link is not valid.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onAccept(invite: InvitePreview) {
    setError(null);
    setAccepting(true);
    try {
      await acceptInvite(token);
      setState({ phase: "joined", invite });
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not accept this invitation.",
      );
    } finally {
      setAccepting(false);
    }
  }

  if (state.phase === "loading") {
    return (
      <p className="text-sm text-[var(--text-secondary)]">
        Checking your invitation…
      </p>
    );
  }

  if (state.phase === "dead") {
    return (
      <div>
        <h1 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
          {DEAD_HEADINGS[state.reason]}
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">{state.detail}</p>
        <p className="mt-6 text-sm text-[var(--text-secondary)]">
          Ask whoever invited you for a new link, or{" "}
          <a
            className="font-medium text-primary underline underline-offset-2"
            href="/login"
          >
            sign in
          </a>{" "}
          if you already have an account.
        </p>
      </div>
    );
  }

  const { invite } = state;

  if (state.phase === "joined") {
    return (
      <div>
        <h1 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
          You are in
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          You joined {invite.org_name} with the {invite.role} role.
        </p>
        <Button asChild className="mt-6 w-full rounded-full" size="lg">
          <a href="/app/overview">Go to your workspace</a>
        </Button>
      </div>
    );
  }

  // An email invitation is spendable by one address. Someone signed in as
  // anybody else is told so here rather than after a refused accept.
  const wrongAccount = signedIn && invite.email_matches === false;

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        {invite.org_kind === "lab" ? "Lab invitation" : "Department invitation"}
      </p>
      <h1 className="mt-1.5 font-serif text-3xl font-semibold text-[var(--text-primary)]">
        Join {invite.org_name}
      </h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">
        {invite.invited_by
          ? `${invite.invited_by} invited you`
          : "You have been invited"}{" "}
        to join with the {invite.role} role.
      </p>

      {invite.message ? (
        <p className="mt-4 border-l-2 border-primary/40 pl-3 text-sm italic text-[var(--text-secondary)]">
          {invite.message}
        </p>
      ) : null}

      {error ? (
        <p
          className="mt-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {wrongAccount ? (
        <div className="mt-6">
          <p className="text-sm text-[var(--text-secondary)]">
            This invitation was sent to {invite.email}, and you are signed in as{" "}
            {invite.signed_in_as}. Sign in with the invited address to accept it.
          </p>
          <Button asChild className="mt-4 w-full rounded-full" size="lg">
            <a href={`/login?next=/join/${token}`}>Sign in as someone else</a>
          </Button>
        </div>
      ) : signedIn ? (
        <Button
          className="mt-6 w-full rounded-full"
          size="lg"
          disabled={accepting}
          onClick={() => void onAccept(invite)}
        >
          {accepting ? "Joining…" : `Join ${invite.org_name}`}
        </Button>
      ) : (
        <div className="mt-6 space-y-3">
          <Button asChild className="w-full rounded-full" size="lg">
            <a href={`/signup?invite=${token}`}>Create an account & join</a>
          </Button>
          <p className="text-center text-sm text-[var(--text-secondary)]">
            Already have an account?{" "}
            <a
              className="font-medium text-primary underline-offset-2 hover:underline"
              href={`/login?next=/join/${token}`}
            >
              Sign in
            </a>
          </p>
        </div>
      )}
    </div>
  );
}
