import type {
  AuthErrorBody,
  AuthUser,
  RegisterInput,
} from "@/lib/auth-types";
import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";

/** Pull the first human-readable message out of a DRF error body. */
function firstFieldError(body: Record<string, unknown> | null): string | null {
  if (!body) {
    return null;
  }
  for (const value of Object.values(body)) {
    if (typeof value === "string" && value) {
      return value;
    }
    if (Array.isArray(value)) {
      const first = value.find((v) => typeof v === "string" && v);
      if (typeof first === "string") {
        return first;
      }
    }
  }
  return null;
}

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

export async function register(input: RegisterInput): Promise<AuthUser> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "register"),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: JSON.stringify(input),
    },
  );

  const body = await parseJson<AuthUser & Record<string, unknown>>(response);

  if (!response.ok) {
    const message =
      firstFieldError(body) ??
      (response.status === 403
        ? "Sign-up was blocked. Refresh the page and try again."
        : "Sign-up failed. Check your details and try again.");
    throw new Error(message);
  }

  if (!body?.id) {
    throw new Error("Sign-up failed. Unexpected response from the server.");
  }

  return {
    id: body.id,
    username: body.username,
    email: body.email,
    is_staff: body.is_staff,
    is_superuser: body.is_superuser,
  };
}

export type OnboardingInterests = {
  version: number;
  areas: string[];
  statement?: string;
  keywords?: string[];
};

export type OnboardingPayload = {
  academic_title?: string;
  institution?: string;
  interests: OnboardingInterests;
};

/** Mark the signed-in user's email verified (scaffold; non-blocking). */
export async function verifyEmail(): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "verify-email"),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
    },
  );

  if (!response.ok) {
    throw new Error("Could not verify your email. Try again in a moment.");
  }
}

/** Persist onboarding answers onto the caller's own profile (one PATCH). */
export async function saveOnboarding(payload: OnboardingPayload): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "profile", "me"),
    {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    const body = await parseJson<Record<string, unknown>>(response);
    throw new Error(
      firstFieldError(body) ??
        "Could not save your onboarding answers. Try again.",
    );
  }
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
