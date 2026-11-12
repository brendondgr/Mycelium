import { authFallback } from "@/lib/auth-fallback";

/**
 * Native-submit target of the reset-password form; see `authFallback`. The
 * reset link's own query string is dropped on purpose: it carries the token.
 */
export function POST() {
  return authFallback("/reset-password");
}
