import { authFallback } from "@/lib/auth-fallback";

/** Native-submit target of the sign-in form; see `authFallback`. */
export function POST() {
  return authFallback("/login");
}
