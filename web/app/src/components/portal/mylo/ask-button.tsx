"use client";

import type { AgentAnchor } from "@/lib/portal/agent/types";
import { useChatAvailability } from "@/lib/portal/hooks";

import { askMylo } from "./events";

/**
 * "Ask Mylo" about one thing (S-15): a small round button with Mylo's painted
 * head in a ring, the same 30 px target as the card's other tools. It sends
 * `mycelium:ask-mylo` and knows nothing about the panel. Not drawn when this
 * person may not chat — the launcher says why, once.
 *
 * It is a button, not the decorative mark beside "Mylo's reason": it has a
 * ring, a focus ring, a name, and it never fades with the card's other tools.
 */
export function AskMyloButton({
  anchor,
  title,
  size = "card",
}: {
  anchor: AgentAnchor;
  title: string;
  /** `head`: a little larger, for a page head beside the title. */
  size?: "card" | "head";
}) {
  const availability = useChatAvailability();
  if (availability.state !== "allowed") return null;
  return (
    <button
      type="button"
      className="ws-mylo-ask"
      data-size={size}
      aria-label={`Ask Mylo about ${title}`}
      title="Ask Mylo"
      onClick={(event) => {
        event.stopPropagation();
        let href: string | undefined;
        if (anchor.kind === "item") {
          const url = new URL(window.location.href);
          url.searchParams.set("item", anchor.key);
          href = `${url.pathname}${url.search}`;
        }
        askMylo({ anchor, title, href });
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- static mascot art */}
      <img
        src="/mylo-portrait-64.webp"
        srcSet="/mylo-portrait-64.webp 1x, /mylo-portrait-128.webp 2x"
        alt=""
        width={size === "head" ? 26 : 22}
        height={size === "head" ? 26 : 22}
        draggable={false}
      />
    </button>
  );
}
