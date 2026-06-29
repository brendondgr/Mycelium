import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { buildApiUrl, getServerApiBase } from "@/lib/api-url";
import type { AuthUser } from "@/lib/auth-types";

async function parseJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
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
