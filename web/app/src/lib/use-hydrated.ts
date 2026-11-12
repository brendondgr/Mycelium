"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * `false` on the server and while hydrating, `true` once React owns the page.
 *
 * The sign-in, sign-up and password forms are rendered on the server, and their
 * submit handlers only exist after hydration. Until then the browser would
 * submit the form natively, so the auth forms keep their submit button disabled
 * until this turns `true`. A disabled default button also blocks Enter-key
 * submission. As a second guard they post to a `/fallback` route that discards
 * the body, so credentials are never sent in a URL.
 *
 * `useSyncExternalStore` with a server snapshot of `false` is React's own way
 * to tell the hydrating render apart from the ones after it.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
