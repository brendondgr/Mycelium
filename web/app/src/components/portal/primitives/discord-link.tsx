"use client";

import * as React from "react";

import {
  recordDiscordLinkClick,
  type DiscordLinkSurface,
} from "@/lib/portal/mutations";
import type { DiscordThreadLink } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * Discord's mark, drawn as the official glyph and coloured Blurple, as the brand
 * guidelines ask. Decorative: the link's accessible name says "in Discord".
 */
export function DiscordMark({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={cn("shrink-0", className)}
    >
      <path
        fill="#5865F2"
        d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"
      />
    </svg>
  );
}

function channelLabel(link: Pick<DiscordThreadLink, "channel_name">, fallback: string) {
  const name = (link.channel_name || fallback || "").replace(/^#/, "");
  return name ? `#${name}` : "Discord";
}

/**
 * Every link into Discord on the web (plan D17): the Discord logo, the channel
 * name, and a new tab. When a lab is bound in several servers, the link opens the
 * first and a small menu lists the rest.
 */
export function DiscordLink({
  links,
  fallbackChannel = "",
  what = "thread",
  surface,
  className,
}: {
  /** Oldest server first; the first is the main link. */
  links: DiscordThreadLink[];
  /** Shown when a link carries no channel name (e.g. "grants"). */
  fallbackChannel?: string;
  /** What the link opens, for its accessible name: "thread" or "channel". */
  what?: "thread" | "channel";
  /** Where the link sits; when set, an opened thread is counted (Phase 8). */
  surface?: DiscordLinkSurface;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const menuId = React.useId();
  if (links.length === 0) return null;
  const [first, ...rest] = links;
  const counted = (url: string) =>
    surface && what === "thread" ? () => recordDiscordLinkClick(url, surface) : undefined;
  const label = channelLabel(first, fallbackChannel);
  return (
    <span className={cn("relative inline-flex items-center gap-1", className)}>
      <a
        href={first.thread_url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={counted(first.thread_url)}
        aria-label={`Open ${label} ${what} in Discord${rest.length ? ` (${first.guild_name})` : ""} (new tab)`}
        className="inline-flex min-h-[28px] items-center gap-1.5 rounded-full px-1 text-[13px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <DiscordMark size={15} />
        <span>{label}</span>
        <ExternalGlyph />
      </a>
      {rest.length ? (
        <>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={menuId}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex min-h-[28px] items-center rounded-full px-1.5 text-[12px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            +{rest.length}
            <span className="sr-only"> more servers</span>
          </button>
          {open ? (
            <ul
              id={menuId}
              className="absolute right-0 top-full z-20 mt-1 min-w-[220px] rounded-xl border border-border bg-surface p-1.5 shadow-lg"
            >
              {rest.map((link) => (
                <li key={link.thread_url}>
                  <a
                    href={link.thread_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={counted(link.thread_url)}
                    aria-label={`Open ${channelLabel(link, fallbackChannel)} ${what} in Discord (${link.guild_name}) (new tab)`}
                    className="flex min-h-[36px] items-center gap-2 rounded-lg px-2 text-[13px] text-[var(--text-primary)] hover:bg-surface-alt"
                  >
                    <DiscordMark size={14} />
                    <span className="truncate">{link.guild_name || "Server"}</span>
                    <span className="text-[var(--text-secondary)]">
                      {channelLabel(link, fallbackChannel)}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </span>
  );
}

function ExternalGlyph() {
  return (
    <svg
      aria-hidden="true"
      width={11}
      height={11}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 4h6v6" />
      <path d="M10 14 20 4" />
      <path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

/** A Discord URL inside rendered Markdown (the report's one-line-per-kind). */
export function isDiscordUrl(href: string | undefined): boolean {
  return Boolean(href && /^https:\/\/(?:www\.)?discord\.com\/channels\//.test(href));
}
