import type {
  AuthErrorBody,
  AuthUser,
  ProfileBasics,
  RegisterInput,
  ResearchInterests,
  SynthesizeInput,
  SynthesizeResult,
  WatchPreference,
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

/** Build an editable research draft from one source and/or a résumé upload. */
export async function synthesizeProfile(
  input: SynthesizeInput,
): Promise<SynthesizeResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const form = new FormData();
  if (input.source) {
    form.append("source", input.source);
  }
  if (input.identifier) {
    form.append("identifier", input.identifier);
  }
  if (input.resume) {
    form.append("resume", input.resume);
  }

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "intake", "synthesize"),
    {
      method: "POST",
      credentials: "include",
      // No Content-Type: the browser sets the multipart boundary itself.
      headers: { ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}) },
      body: form,
    },
  );

  const body = await parseJson<SynthesizeResult & Record<string, unknown>>(
    response,
  );

  if (!response.ok) {
    throw new Error(
      firstFieldError(body) ??
        "Could not build your research profile. Check the id or file and try again.",
    );
  }
  if (!body?.interests) {
    throw new Error("Unexpected response while building your profile.");
  }
  return { draft: body.draft, interests: body.interests };
}

/** Persist person-global profile basics (role + institution). */
export async function saveProfileBasics(payload: ProfileBasics): Promise<void> {
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
      firstFieldError(body) ?? "Could not save your profile. Try again.",
    );
  }
}

/** Validate and save research interests onto the caller's own profile. */
export async function confirmInterests(
  interests: ResearchInterests,
): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "intake", "confirm"),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: JSON.stringify({ interests }),
    },
  );

  if (!response.ok) {
    const body = await parseJson<Record<string, unknown>>(response);
    throw new Error(
      firstFieldError(body) ?? "Could not save your research interests.",
    );
  }
}

/** Read what Milo keeps an eye on for the caller (own only). */
export async function getWatch(): Promise<WatchPreference> {
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "watch", "me"),
    { method: "GET", credentials: "include", cache: "no-store" },
  );
  const body = await parseJson<WatchPreference>(response);
  if (!response.ok || !body) {
    throw new Error("Could not load your watch settings.");
  }
  return body;
}

/** Save what Milo keeps an eye on for the caller (own only). */
export async function saveWatch(
  payload: WatchPreference,
): Promise<WatchPreference> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "watch", "me"),
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

  const body = await parseJson<WatchPreference & Record<string, unknown>>(
    response,
  );
  if (!response.ok || !body) {
    throw new Error(
      firstFieldError(body) ?? "Could not save your watch settings.",
    );
  }
  return body;
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
