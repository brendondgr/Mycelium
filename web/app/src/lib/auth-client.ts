import type { AuthErrorBody, AuthUser } from "@/lib/auth-types";
import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";

function readCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function parseJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function ensureCsrfCookie(): Promise<void> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "auth", "csrf"), {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Could not prepare sign-in. Try again in a moment.");
  }
}

export async function login(
  username: string,
  password: string,
): Promise<AuthUser> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(buildApiUrl(getPublicApiBase(), "auth", "login"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: JSON.stringify({ username, password }),
  });

  const body = await parseJson<AuthUser & AuthErrorBody>(response);

  if (!response.ok) {
    const message =
      body?.non_field_errors?.[0] ??
      body?.detail ??
      (response.status === 403
        ? "Sign-in was blocked. Refresh the page and try again."
        : response.status === 400
          ? "Enter both username and password."
          : response.status === 401
            ? "Invalid username or password."
            : "Sign-in failed. Check your connection and try again.");
    throw new Error(message);
  }

  if (!body?.id) {
    throw new Error("Sign-in failed. Unexpected response from the server.");
  }

  return {
    id: body.id,
    username: body.username,
    email: body.email,
    is_staff: body.is_staff,
    is_superuser: body.is_superuser,
  };
}

export async function logout(): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(buildApiUrl(getPublicApiBase(), "auth", "logout"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
  });

  if (!response.ok && response.status !== 204) {
    throw new Error("Could not sign out. Try again.");
  }
}
