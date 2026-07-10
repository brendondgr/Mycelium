/**
 * An API request that returned a non-OK HTTP status. Carrying the status lets
 * callers (and React Query's retry policy) tell a client error — an expired or
 * clobbered session (401/403), a bad request (400) — apart from a transient
 * server/network blip (5xx), which is the only class worth retrying.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True for a 4xx client error — retrying it just hammers the server. */
export function isClientError(error: unknown): boolean {
  return (
    error instanceof ApiError && error.status >= 400 && error.status < 500
  );
}
