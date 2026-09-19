"use client";

import { useQuery } from "@tanstack/react-query";

import { getAccount } from "@/lib/auth-client";
import type { AccountDetails } from "@/lib/auth-types";
import { cn } from "@/lib/utils";

type InstitutionState = Pick<
  AccountDetails,
  "institution" | "institution_verified" | "institution_from_email"
>;

/**
 * The reader's institution — shown, never asked for.
 *
 * An institution is proved by a verified email: the backend derives it from the
 * address's domain against the affiliation directory and refuses a typed one
 * (`apps/accounts/institution.py`). So this is a read-only line that says where
 * the name came from and, when there is none, what would put one here. The
 * same institution scopes who can be suggested as a collaborator, which is why
 * the copy mentions finding people.
 *
 * Pass `account` when the caller already holds it; otherwise the account is
 * fetched (and refetched on mount, so it is current straight after a code is
 * entered).
 */
export function InstitutionFromEmail({
  id,
  account,
  labelledBy,
  className,
}: {
  id?: string;
  account?: InstitutionState | null;
  /** The id of the visible label this line belongs to. */
  labelledBy?: string;
  className?: string;
}) {
  const query = useQuery({
    queryKey: ["auth", "account"],
    queryFn: getAccount,
    enabled: account === undefined,
    staleTime: 0,
  });
  const state = account === undefined ? query.data : account;
  const failed = account === undefined && query.isError;

  let name: string;
  let caption: string;
  let muted = false;
  if (failed) {
    name = "Couldn't load your institution";
    caption = "It comes from your verified email. Reload to try again.";
    muted = true;
  } else if (!state) {
    name = "Checking your email…";
    caption = "Your institution comes from your verified email address.";
    muted = true;
  } else if (state.institution_verified && state.institution) {
    name = state.institution;
    caption =
      "From your verified email. To change it, change your email to an address at your new institution.";
  } else if (state.institution_from_email) {
    name = state.institution_from_email;
    caption = "Shown once you confirm your email address.";
    muted = true;
  } else {
    name = "No institution";
    caption =
      "Your email isn't at an institution we recognise. Use your institution's address to show it here and to find people there.";
    muted = true;
  }

  return (
    <div
      id={id}
      role="group"
      aria-labelledby={labelledBy}
      aria-live="polite"
      className={cn(
        "rounded-xl border border-border bg-surface px-3.5 py-2.5",
        className,
      )}
    >
      <p
        className={cn(
          "text-sm",
          muted
            ? "text-[var(--text-secondary)]"
            : "font-medium text-[var(--text-primary)]",
        )}
      >
        {name}
      </p>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">{caption}</p>
    </div>
  );
}
