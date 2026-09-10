import type {
  AccountDetails,
  AccountUpdate,
  AuthErrorBody,
  AuthUser,
  ComposeClustersInput,
  InviteAccepted,
  InviteDeadReason,
  InvitePreview,
  OnboardingMatchArea,
  OnboardingMatchResult,
  ProfileBasics,
  ProposeClustersInput,
  ProposeClustersResult,
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

export function readCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  // Must match Django's CSRF_COOKIE_NAME (settings.py). Mycelium namespaces its
  // auth cookies so other localhost apps can't overwrite them, so this is the
  // prefixed name — not Django's bare `csrftoken` default.
  const match = document.cookie.match(/(?:^|;\s*)mycelium_csrftoken=([^;]+)/);
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
    onboarding_completed: Boolean(body.onboarding_completed),
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
    onboarding_completed: Boolean(body.onboarding_completed),
  };
}

/** A dead invitation, carrying the reason so the join page can say which. */
export class InviteDeadError extends Error {
  reason: InviteDeadReason;

  constructor(message: string, reason: InviteDeadReason) {
    super(message);
    this.name = "InviteDeadError";
    this.reason = reason;
  }
}

/**
 * Read what an invitation link leads to. Works signed out — the whole point is
 * that the recipient may not have an account yet.
 *
 * Throws `InviteDeadError` for a link that is withdrawn, expired, spent, or
 * simply wrong, so the page can say which rather than shrug.
 */
export async function previewInvite(token: string): Promise<InvitePreview> {
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "invites", token),
    { method: "GET", credentials: "include", cache: "no-store" },
  );
  const body = await parseJson<Record<string, unknown>>(response);

  if (!response.ok) {
    throw new InviteDeadError(
      typeof body?.detail === "string"
        ? body.detail
        : "This invitation link is not valid.",
      (body?.reason as InviteDeadReason) ?? "invalid",
    );
  }
  return body as unknown as InvitePreview;
}

/** Spend an invitation as the signed-in account and join the org. */
export async function acceptInvite(token: string): Promise<InviteAccepted> {
  return postAuth<InviteAccepted>(
    ["invites", token, "accept"],
    {},
    "Could not accept this invitation.",
  );
}

/**
 * POST JSON to an `/api/auth/...` path with a fresh CSRF token, and turn a DRF
 * error body into a thrown Error carrying the field message the user should see.
 *
 * Every account endpoint below answers the same way — `{ field: [message] }` on
 * a refusal — so the handling belongs here rather than repeated nine times.
 */
async function postAuth<T>(
  segments: string[],
  payload: Record<string, unknown>,
  fallback: string,
): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", ...segments),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: JSON.stringify(payload),
    },
  );

  const body = await parseJson<T & Record<string, unknown>>(response);
  if (!response.ok) {
    throw new Error(firstFieldError(body) ?? fallback);
  }
  return body as T;
}

/** Read the signed-in account: name, address, affiliation, verification state. */
export async function getAccount(): Promise<AccountDetails> {
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "account"),
    { method: "GET", credentials: "include", cache: "no-store" },
  );
  const body = await parseJson<AccountDetails>(response);
  if (!response.ok || !body) {
    throw new Error("Could not load your account.");
  }
  return body;
}

/** Save the fields the Account page owns outright (name, affiliation, stage). */
export async function updateAccount(
  payload: AccountUpdate,
): Promise<AccountDetails> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "account"),
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

  const body = await parseJson<AccountDetails & Record<string, unknown>>(
    response,
  );
  if (!response.ok || !body) {
    throw new Error(firstFieldError(body) ?? "Could not save your account.");
  }
  return body;
}

/** Submit the six-digit code; on success the account is activated. */
export async function verifyEmailCode(code: string): Promise<AccountDetails> {
  return postAuth<AccountDetails>(
    ["email", "verify"],
    { code },
    "Could not verify that code. Try again in a moment.",
  );
}

/** Send a fresh code, to the pending new address when one is in flight. */
export async function resendVerificationCode(): Promise<{ email: string }> {
  return postAuth<{ email: string }>(
    ["email", "resend"],
    {},
    "Could not send a new code. Try again in a moment.",
  );
}

/**
 * Start a move to a new address. Nothing changes on the account until the code
 * mailed to that address comes back through `verifyEmailCode`.
 */
export async function changeEmail(
  newEmail: string,
  currentPassword: string,
): Promise<{ pending_email: string }> {
  return postAuth<{ pending_email: string }>(
    ["email", "change"],
    { new_email: newEmail, current_password: currentPassword },
    "Could not change your email. Try again in a moment.",
  );
}

/**
 * Whether an address is free, so sign-up can say so before the form is finished.
 * Gated on the invite code, so it is only answerable to a genuine sign-up.
 */
export async function checkEmailAvailable(
  email: string,
  accessCode: string,
): Promise<boolean> {
  const result = await postAuth<{ available: boolean }>(
    ["email", "check"],
    { email, access_code: accessCode },
    "Could not check that email.",
  );
  return Boolean(result.available);
}

/**
 * Step one of a password change: mail a confirmation code to the account's own
 * address. Refused without the current password, so a borrowed browser cannot
 * be used to fire codes at the owner's inbox.
 */
export async function requestPasswordChange(
  currentPassword: string,
): Promise<string> {
  const body = await postAuth<{ detail: string }>(
    ["password", "change", "request"],
    { current_password: currentPassword },
    "Could not send a confirmation code. Try again in a moment.",
  );
  return body.detail;
}

/**
 * Step two: spend the emailed code on the new password. This session stays
 * signed in; every other one dies with the old password hash.
 */
export async function changePassword(
  currentPassword: string,
  code: string,
  newPassword: string,
  newPasswordConfirm: string,
): Promise<void> {
  await postAuth(
    ["password", "change"],
    {
      current_password: currentPassword,
      code,
      new_password: newPassword,
      new_password_confirm: newPasswordConfirm,
    },
    "Could not change your password. Try again in a moment.",
  );
}

/**
 * Ask for a reset link. The answer is the same whether or not the address is
 * registered, so callers must not treat success as proof an account exists.
 */
export async function requestPasswordReset(email: string): Promise<string> {
  const body = await postAuth<{ detail: string }>(
    ["password", "reset"],
    { email },
    "Could not send a reset link. Try again in a moment.",
  );
  return body.detail;
}

/** Whether a reset link is still live, checked before showing the form. */
export async function verifyResetToken(
  uid: string,
  token: string,
): Promise<boolean> {
  const body = await postAuth<{ valid: boolean }>(
    ["password", "reset", "verify"],
    { uid, token },
    "Could not check that reset link.",
  );
  return Boolean(body.valid);
}

/** Spend a reset link on a new password. */
export async function confirmPasswordReset(
  uid: string,
  token: string,
  password: string,
  passwordConfirm: string,
): Promise<void> {
  await postAuth(
    ["password", "reset", "confirm"],
    { uid, token, password, password_confirm: passwordConfirm },
    "Could not reset your password. Try again in a moment.",
  );
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

/**
 * Propose (or re-sort) interest clusters for the "Organize your interests" step.
 * Two modes on one endpoint, chosen by which fields the caller populates:
 *   - Propose: `{ areas[, keywords, statement] }` groups the areas into named
 *     clusters — LLM grouping with a geometric fallback.
 *   - Sort: `{ clusters, unsorted }` routes the `unsorted` areas into the given
 *     clusters, preserving their ids — the "sort these" affordance.
 * Same response shape either way: the resulting clusters, a watch-topic seed
 * derived from them, and which strategy produced the grouping.
 */
export async function proposeClusters(
  input: ProposeClustersInput,
): Promise<ProposeClustersResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "intake", "clusters"),
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

  const body = await parseJson<ProposeClustersResult & Record<string, unknown>>(
    response,
  );
  if (!response.ok || !body?.clusters) {
    throw new Error(
      firstFieldError(body) ?? "Could not organize your interests. Try again.",
    );
  }
  return {
    clusters: body.clusters,
    areas: body.areas ?? body.clusters.flatMap((cluster) => cluster.areas),
    watch_topics: body.watch_topics ?? [],
    source: body.source ?? "single",
  };
}

/**
 * Build theme→sub-topic clusters from a free-text description (the "Build
 * clusters with Mylo" box). The instruction plus the caller's current profile
 * are sent to the same `intake/clusters` endpoint in its "instruct" mode; Mylo
 * refines the current grouping (persisting themes keep their ids) and may invent
 * concrete sub-topics, so the result's `areas` is a widened union the returned
 * clusters partition — the caller replaces its area list with it.
 */
export async function composeClusters(
  input: ComposeClustersInput,
): Promise<ProposeClustersResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "intake", "clusters"),
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

  const body = await parseJson<ProposeClustersResult & Record<string, unknown>>(
    response,
  );
  if (!response.ok || !body?.clusters) {
    throw new Error(
      firstFieldError(body) ?? "Could not build your clusters. Try again.",
    );
  }
  return {
    clusters: body.clusters,
    areas: body.areas ?? body.clusters.flatMap((cluster) => cluster.areas),
    watch_topics: body.watch_topics ?? [],
    source: body.source ?? "llm",
  };
}

/** Read what Mylo keeps an eye on for the caller (own only). */
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

/** Save what Mylo keeps an eye on for the caller (own only). */
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

/**
 * Match one area (papers/grants/fellowships/conferences) for the signed-in user
 * over the already-scraped corpus, persisting their scores. Drives the live
 * post-onboarding match window — the caller runs the opted-in areas in turn.
 *
 * A slow area must never freeze the flow, so the request is bounded by
 * ``timeoutMs`` (default 60s); on timeout the fetch is aborted and this rejects,
 * and the caller marks that area failed and moves on.
 */
export async function runOnboardingMatch(
  area: OnboardingMatchArea,
  { timeoutMs = 60_000 }: { timeoutMs?: number } = {},
): Promise<OnboardingMatchResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(
      buildApiUrl(getPublicApiBase(), "onboarding", "match"),
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        },
        body: JSON.stringify({ area }),
        signal: controller.signal,
      },
    );
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Matching ${area} took too long.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }

  const body = await parseJson<OnboardingMatchResult & Record<string, unknown>>(
    response,
  );
  if (!response.ok || !body) {
    throw new Error(firstFieldError(body) ?? `Could not match ${area}.`);
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
