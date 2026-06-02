"use client";

import { useEffect } from "react";

/**
 * Removes credentials accidentally submitted via a native GET form fallback so
 * they are not kept in the address bar or browser history.
 */
export function LoginQuerySanitizer() {
  useEffect(() => {
    const url = new URL(window.location.href);
    const sensitive = ["username", "password", "email"];
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
