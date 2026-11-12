import { authFallback } from "@/lib/auth-fallback";

/** Native-submit target of the sign-up form; see `authFallback`. */
export function POST() {
  return authFallback("/signup");
}
