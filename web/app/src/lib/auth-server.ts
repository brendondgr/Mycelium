import { cookies } from "next/headers";

import type { AuthUser } from "@/lib/auth-types";

const DEFAULT_INTERNAL_API = "http://127.0.0.1:8000/api";

function getServerApiBase(): string {
  const base =
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    DEFAULT_INTERNAL_API;
  return base.replace(/\/$/, "");
}

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

  const response = await fetch(`${getServerApiBase()}/auth/me/`, {
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
