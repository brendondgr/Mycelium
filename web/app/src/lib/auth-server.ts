import { cookies } from "next/headers";

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
