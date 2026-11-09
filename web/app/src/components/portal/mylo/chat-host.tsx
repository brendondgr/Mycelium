"use client";

import { usePathname } from "next/navigation";
import * as React from "react";

import { Portal } from "@/components/portal/feed/reader";
import { usePortal } from "@/components/portal/portal-context";
import { fetchThreads, type NewThread } from "@/lib/portal/agent/client";
import type { AgentThread } from "@/lib/portal/agent/types";
import { useChatAvailability } from "@/lib/portal/hooks";
import { projectIdFromPathname } from "@/lib/portal/routes";

import { ChatPanel, type PanelView, type Session } from "./chat-panel";
import { ASK_MYLO_EVENT, type AskMyloRequest } from "./events";
import { Launcher } from "./launcher";

const LAST_THREAD_KEY = "mycelium_mylo_last_thread";

function readLast(): string | null {
  try {
    return window.localStorage.getItem(LAST_THREAD_KEY);
  } catch {
    return null;
  }
}

function writeLast(id: string | null) {
  try {
    if (id) window.localStorage.setItem(LAST_THREAD_KEY, id);
    else window.localStorage.removeItem(LAST_THREAD_KEY);
  } catch {
    // a per-viewer convenience only
  }
}

const WIDE = "(min-width: 980px)";

function useWide(): boolean {
  return React.useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia(WIDE);
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia(WIDE).matches,
    () => true,
  );
}

let sessionCounter = 0;
const nextKey = () => (sessionCounter += 1);

/**
 * Mounted once in the workspace shell. Owns the one panel and the launcher;
 * opens on `mycelium:ask-mylo` from any Mylo-face button. When chat is not
 * available the buttons are not drawn and the launcher opens the "Not
 * allowed" state, so the reason is said once.
 */
export function ChatHost() {
  const availability = useChatAvailability();
  const pathname = usePathname();
  const { scope } = usePortal();
  const wide = useWide();
  const [open, setOpen] = React.useState(false);
  const [view, setView] = React.useState<PanelView>("chat");
  const [session, setSession] = React.useState<Session | null>(null);
  const panelRef = React.useRef<HTMLElement | null>(null);
  const inputRef = React.useRef<HTMLTextAreaElement | null>(null);
  const launcherRef = React.useRef<HTMLButtonElement | null>(null);
  const returnTo = React.useRef<HTMLElement | null>(null);

  /** A new conversation starts in the page's scope: the project, or the workspace. */
  const scopeDraft = React.useCallback((): NewThread => {
    const projectId = projectIdFromPathname(pathname);
    if (projectId) return { scope: "project", ref: projectId };
    if (scope.kind === "lab") return { scope: "lab", ref: scope.slug };
    if (scope.kind === "department") return { scope: "department", ref: scope.id };
    return { scope: "personal" };
  }, [pathname, scope]);

  const show = React.useCallback((next: Session) => {
    if (!returnTo.current) returnTo.current = document.activeElement as HTMLElement | null;
    setSession(next);
    setView("chat");
    setOpen(true);
  }, []);

  const adopt = React.useCallback((thread: AgentThread) => {
    writeLast(thread.id);
    setSession((s) => (s ? { ...s, threadId: thread.id, resolving: false } : s));
  }, []);

  // A Mylo-face button: reopen the conversation already about that thing, or
  // start one (stored only when the first question is sent).
  React.useEffect(() => {
    const onAsk = (event: Event) => {
      const request = (event as CustomEvent<AskMyloRequest>).detail;
      const { anchor } = request;
      returnTo.current = document.activeElement as HTMLElement | null;
      if (
        session?.about &&
        session.about.anchor.kind === anchor.kind &&
        session.about.anchor.key === anchor.key
      ) {
        setView("chat");
        setOpen(true);
        return;
      }
      const key = nextKey();
      const draft: NewThread = { ...scopeDraft(), anchor };
      show({ key, threadId: null, draft, about: request, resolving: true });
      fetchThreads({ anchor })
        .catch(() => [] as AgentThread[])
        .then((threads) => {
          const found = threads[0];
          setSession((s) => {
            if (!s || s.key !== key) return s; // the person moved on
            return found
              ? { key: nextKey(), threadId: found.id, draft, about: request }
              : { ...s, resolving: false };
          });
          if (found) writeLast(found.id);
        });
    };
    window.addEventListener(ASK_MYLO_EVENT, onAsk);
    return () => window.removeEventListener(ASK_MYLO_EVENT, onAsk);
  }, [scopeDraft, session, show]);

  const openLauncher = () => {
    returnTo.current = launcherRef.current;
    if (session) {
      setView("chat");
      setOpen(true);
      return;
    }
    const last = readLast();
    show({ key: nextKey(), threadId: last, draft: scopeDraft(), about: null });
  };

  const newChat = () => {
    setSession({ key: nextKey(), threadId: null, draft: scopeDraft(), about: null });
    setView("chat");
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const pick = (thread: AgentThread) => {
    writeLast(thread.id);
    setSession({
      key: nextKey(),
      threadId: thread.id,
      draft: { scope: thread.scope, ref: thread.scope_ref, anchor: thread.anchor },
      about: null,
    });
    setView("chat");
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const close = React.useCallback(() => {
    setOpen(false);
    const back = returnTo.current;
    returnTo.current = null;
    // the launcher comes back on close; give it focus once it is drawn
    requestAnimationFrame(() => {
      const target = back && back.isConnected ? back : launcherRef.current;
      target?.focus({ preventScroll: true });
    });
  }, []);

  // Focus the composer when the panel opens.
  React.useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      if (inputRef.current && !inputRef.current.disabled) inputRef.current.focus();
      else panelRef.current?.focus();
    }, 30);
    return () => window.clearTimeout(t);
  }, [open, session?.key]);

  const hasSession = session !== null;

  // On a wide screen the open panel is a column of the page, not a cover: the
  // shell gives up the panel's width (`.ws-shell` in workspace.css).
  React.useEffect(() => {
    if (!open || !wide || !hasSession) return;
    const root = document.documentElement;
    root.setAttribute("data-mylo-open", "");
    return () => root.removeAttribute("data-mylo-open");
  }, [open, wide, hasSession]);

  // The launcher reopens whatever was open last.
  React.useEffect(() => {
    if (!open || !session?.threadId) return;
    writeLast(session.threadId);
  }, [open, session?.threadId]);

  if (availability.state === "absent") return null;

  return (
    <>
      <Launcher ref={launcherRef} hidden={open} onOpen={openLauncher} />
      {session ? (
        <Portal>
          <ChatPanel
            open={open}
            wide={wide}
            session={session}
            view={view}
            availability={availability}
            onClose={close}
            onNewChat={newChat}
            onShowHistory={(on) => setView(on ? "history" : "chat")}
            onPick={pick}
            onCreated={adopt}
            panelRef={panelRef}
            inputRef={inputRef}
          />
        </Portal>
      ) : null}
    </>
  );
}
