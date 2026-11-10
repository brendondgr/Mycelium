"use client";

/**
 * Whether the workspace is showing the public demo, and the demo-aware forms
 * of the two ways the app navigates.
 *
 * The server knows it is a demo request (the proxy's header), fetches `/me`
 * through `/api/demo/`, and that payload's `demo` block arrives here as the
 * provider's value — so the server render and the browser agree on every href.
 * Outside the demo the value is `null` and both hooks are the identity.
 */

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { toDemoPath } from "@/lib/demo";
import type { DemoInfo, DemoRefusal } from "@/lib/auth-types";

type DemoState = DemoInfo & {
  /** Mylo answered (or refused): what the visitor may still ask. */
  setBudget: (questionsLeft: number, refusal?: DemoRefusal | null) => void;
};

const DemoContext = createContext<DemoState | null>(null);

export function DemoProvider({
  demo,
  children,
}: {
  demo: DemoInfo | null | undefined;
  children: React.ReactNode;
}) {
  const [budget, setBudgetState] = useState(() => ({
    questions_left: demo?.questions_left ?? 0,
    refusal: demo?.refusal ?? null,
  }));
  const setBudget = useCallback(
    (questionsLeft: number, refusal: DemoRefusal | null = null) =>
      setBudgetState({ questions_left: questionsLeft, refusal }),
    [],
  );
  const value = useMemo<DemoState | null>(
    () => (demo ? { ...demo, ...budget, setBudget } : null),
    [demo, budget, setBudget],
  );
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

/** The demo's state, or `null` outside the demo. */
export function useDemo(): DemoState | null {
  return useContext(DemoContext);
}

/** Maps an `/app/…` href to the demo's `/demo/…` while in the demo. */
export function useAppHref(): (href: string) => string {
  const demo = useContext(DemoContext) !== null;
  return useCallback((href: string) => (demo ? toDemoPath(href) : href), [demo]);
}

/** `useRouter()` whose `push` / `replace` / `prefetch` keep the visitor in the demo. */
export function useAppRouter() {
  const router = useRouter();
  const appHref = useAppHref();
  return useMemo(
    () => ({
      ...router,
      push: (href: string, options?: Parameters<typeof router.push>[1]) =>
        router.push(appHref(href), options),
      replace: (href: string, options?: Parameters<typeof router.replace>[1]) =>
        router.replace(appHref(href), options),
      prefetch: (href: string, options?: Parameters<typeof router.prefetch>[1]) =>
        router.prefetch(appHref(href), options),
    }),
    [router, appHref],
  );
}
