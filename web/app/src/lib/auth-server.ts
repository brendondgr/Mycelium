import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { buildApiUrl, getServerApiBase } from "@/lib/api-url";
import type { AuthUser, SignupPolicy } from "@/lib/auth-types";

async function parseJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/**
 * The instance's sign-up policy, read on the server so the page renders the
 * right form on first paint. If the API cannot be reached the form falls back to
 * asking for a code, which is the strictest form that can still succeed.
 */
export async function getSignupPolicy(): Promise<SignupPolicy> {
  const fallback: SignupPolicy = { mode: "code", verify_email: true, domains: [] };
  try {
    const response = await fetch(
      buildApiUrl(getServerApiBase(), "auth", "signup-policy"),
      { cache: "no-store" },
    );
    if (!response.ok) {
      return fallback;
    }
    return (await parseJson<SignupPolicy>(response)) ?? fallback;
  } catch {
    return fallback;
  }
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  if (!cookieHeader) {
    return null;
  }

  const response = await fetch(buildApiUrl(getServerApiBase(), "auth", "me"), {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    return null;
  }

  const body = await parseJson<AuthUser>(response);
  if (!body?.id) {
    return null;
  }

  return body;
}

/**
 * Gate a workspace page on a signed-in, fully onboarded user.
 *
 * Anonymous visitors are sent to `/login`; signed-in users who have not finished
 * onboarding are forced to `/app/onboarding` and cannot reach workspace pages
 * until they complete it. Every authenticated page under `/app` (except the
 * onboarding flow itself) should call this instead of `getCurrentUser`.
 */
export async function requireOnboardedUser(): Promise<AuthUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  if (!user.onboarding_completed) {
    redirect("/app/onboarding");
  }
  return user;
}
