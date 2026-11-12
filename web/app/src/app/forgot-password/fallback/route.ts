import { authFallback } from "@/lib/auth-fallback";

/** Native-submit target of the forgot-password form; see `authFallback`. */
export function POST() {
  return authFallback("/forgot-password");
}
