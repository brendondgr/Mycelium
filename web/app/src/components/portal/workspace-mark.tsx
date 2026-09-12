"use client";

import { labLogoUrl } from "@/lib/portal/client";
import {
  workspaceHue,
  workspaceInitials,
  type Workspace,
} from "@/lib/portal/workspace";
import { cn } from "@/lib/utils";

/**
 * A workspace's visual mark, shared by the rail, the sheet, the palette and the
 * sidebar so one workspace looks the same everywhere.
 *
 * A lab with an uploaded logo shows it. Everything else shows tinted initials —
 * from a hue drawn out of the eight cluster accents, which are deliberately
 * clear of the semantic green/gold/terracotta so a workspace mark can never be
 * mistaken for a fit or urgency signal.
 */
export function WorkspaceMark({
  workspace,
  size = 24,
  radius,
  className,
}: {
  workspace: Workspace;
  size?: number;
  radius?: number;
  className?: string;
}) {
  const logo =
    workspace.lab && workspace.lab.logo_version !== null
      ? labLogoUrl(workspace.lab.slug, workspace.lab.logo_version)
      : null;

  const style: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: radius ?? Math.round(size * 0.3),
    fontSize: Math.max(9, Math.round(size * 0.42)),
  };

  if (logo) {
    return (
      // A user-supplied logo served from our own API; a plain img is right here.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logo}
        alt=""
        aria-hidden
        className={cn("shrink-0 object-cover", className)}
        style={style}
      />
    );
  }

  const personal = workspace.kind === "personal";
  return (
    <span
      aria-hidden
      className={cn(
        "inline-grid shrink-0 place-items-center font-serif font-semibold leading-none text-[#fffdf8]",
        className,
      )}
      style={{
        ...style,
        background: personal
          ? "var(--brand-panel)"
          : workspaceHue(workspace.key),
        color: personal ? "var(--brand-panel-foreground)" : "#fffdf8",
      }}
    >
      {workspaceInitials(workspace.name)}
    </span>
  );
}
