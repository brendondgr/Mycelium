"use client";

import { useEffect } from "react";

/**
 * Removes form fields from the address bar if a browser ever put them there.
 *
 * Defence in depth only. The auth forms post (`method="post"`) to a fallback
 * route and keep their submit button disabled until the page has hydrated, so a
 * native GET submit should no longer happen. This runs after hydration, by
 * which point such a URL would already have reached the server log; it only
 * keeps the values out of the address bar and history.
 */
export function LoginQuerySanitizer() {
  useEffect(() => {
    const url = new URL(window.location.href);
    const sensitive = [
      "username",
      "password",
      "password_confirm",
      "email",
      "access_code",
      "first_name",
      "last_name",
      "new-password",
      "confirm-password",
    ];
    let changed = false;

    for (const key of sensitive) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        changed = true;
      }
    }

    if (changed) {
      const next = url.search ? `${url.pathname}${url.search}` : url.pathname;
      window.history.replaceState(window.history.state, "", next);
    }
  }, []);

  return null;
}
