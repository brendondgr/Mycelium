import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { buildApiUrl, getServerApiBase } from "@/lib/api-url";
import { DEMO_HEADER, toDemoPath } from "@/lib/demo";
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

/** Whether this server render is a `/demo/*` request (set by `src/proxy.ts`). */
export async function isDemoRequest(): Promise<boolean> {
  return (await headers()).get(DEMO_HEADER) === "1";
}

/** `redirect()` that keeps a demo visitor in the demo. */
export async function appRedirect(href: string): Promise<never> {
  redirect((await isDemoRequest()) ? toDemoPath(href) : href);
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();
  const demo = await isDemoRequest();

  // The demo is nobody's session: the backend's demo door answers as the
  // demo viewer whatever cookies come with it.
  if (!cookieHeader && !demo) {
    return null;
  }

  const base = demo ? `${getServerApiBase()}/demo` : getServerApiBase();
  const response = await fetch(buildApiUrl(base, "auth", "me"), {
    headers: cookieHeader ? { Cookie: cookieHeader } : {},
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
 *
 * In the demo there is no one to sign in: a demo the operator has switched off
 * (or never built) is simply not found.
 */
export async function requireOnboardedUser(): Promise<AuthUser> {
  const user = await getCurrentUser();
  if (!user) {
    if (await isDemoRequest()) {
      notFound();
    }
    redirect("/login");
  }
  if (!user.onboarding_completed) {
    redirect("/app/onboarding");
  }
  return user;
}
