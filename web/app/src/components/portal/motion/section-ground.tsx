"use client";

import * as React from "react";

/**
 * A quiet botanical ground behind the workspace, keyed to the section you are
 * in — the public site's motif idea, dialled down for a surface people work in
 * all day.
 *
 * Three things keep it on the right side of the line the style guide draws
 * ("the interface should carry the work; do not let the motif compete"):
 *
 *   - It is *fixed* behind the scroll container, not repeated per section, so
 *     it never tiles down a long feed and never moves while you read.
 *   - It is roughly a third of the strength of the marketing version, drawn
 *     only in the outer margins, and masked away from the middle of the page
 *     where the cards and their text actually live.
 *   - Each area gets its own growth, so Papers and Grants are distinguishable
 *     at a glance the way the marketing pages are — but a section with no entry
 *     here simply renders nothing rather than falling back to a default.
 *
 * Purely decorative: `aria-hidden`, no pointer events, and nothing here encodes
 * information that is not already in the page.
 */

type Growth = "roots" | "vine" | "canopy" | "spores";

/** Which growth belongs to which workspace area. */
const BY_SECTION: Record<string, Growth> = {
  "research-papers": "roots",
  suggested: "roots",
  grants: "spores",
  fellowships: "vine",
  conferences: "canopy",
  saves: "spores",
  overview: "vine",
  daily: "canopy",
};

/** Pull the area name out of `/app/<area>` (and `/app/labs/<slug>/<area>`). */
export function areaFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  const afterApp = parts[0] === "app" ? parts.slice(1) : parts;
  if (afterApp[0] === "labs" && afterApp.length >= 3) return afterApp[2];
  return afterApp[0] ?? "";
}

function Art({ growth }: { growth: Growth }) {
  if (growth === "roots") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 400"
        preserveAspectRatio="xMidYMin meet"
        fill="none"
      >
        <g className="portal-ground-line">
          <path d="M120 -20 C 120 60, 100 90, 98 140 C 96 190, 78 210, 70 264" />
          <path d="M70 264 C 100 200, 130 190, 152 236" strokeWidth={1} />
          <path d="M1080 -20 C 1082 62, 1102 88, 1106 138 C 1110 188, 1094 212, 1088 266" />
          <path d="M1088 266 C 1058 202, 1030 190, 1010 232" strokeWidth={1} />
        </g>
        <g className="portal-ground-node">
          <circle cx="70" cy="264" r="3" />
          <circle cx="152" cy="236" r="2.2" />
          <circle cx="1088" cy="266" r="3" />
          <circle cx="1010" cy="232" r="2.2" />
        </g>
      </svg>
    );
  }

  if (growth === "vine") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 900"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
      >
        <defs>
          <path id="portal-leaf" d="M0 0 C 7 -9, 22 -9, 29 0 C 22 9, 7 9, 0 0 Z" />
        </defs>
        <g className="portal-ground-line">
          <path d="M78 -40 C 30 140, 110 320, 62 500 C 20 660, 96 780, 60 960" />
          <path d="M1128 -40 C 1176 140, 1096 320, 1144 500 C 1186 660, 1110 780, 1146 960" />
        </g>
        <g className="portal-ground-leaf">
          <use href="#portal-leaf" transform="translate(66 90) rotate(-34)" />
          <use href="#portal-leaf" transform="translate(52 300) rotate(196) scale(0.86)" />
          <use href="#portal-leaf" transform="translate(74 520) rotate(-22) scale(0.92)" />
          <use href="#portal-leaf" transform="translate(48 740) rotate(190) scale(0.8)" />
          <use href="#portal-leaf" transform="translate(1134 90) rotate(214)" />
          <use href="#portal-leaf" transform="translate(1148 300) rotate(-16) scale(0.86)" />
          <use href="#portal-leaf" transform="translate(1126 520) rotate(202) scale(0.92)" />
          <use href="#portal-leaf" transform="translate(1152 740) rotate(-10) scale(0.8)" />
        </g>
      </svg>
    );
  }

  if (growth === "canopy") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 300"
        preserveAspectRatio="xMidYMin meet"
        fill="none"
      >
        <defs>
          <path id="portal-canopy-leaf" d="M0 0 C 6 -9, 21 -9, 27 0 C 21 9, 6 9, 0 0 Z" />
        </defs>
        <g className="portal-ground-line">
          <path d="M-30 -10 C 90 22, 172 66, 236 140" />
          <path d="M1230 -10 C 1110 22, 1028 66, 964 140" />
        </g>
        <g className="portal-ground-leaf">
          <use href="#portal-canopy-leaf" transform="translate(44 0) rotate(26) scale(0.86)" />
          <use href="#portal-canopy-leaf" transform="translate(118 40) rotate(50) scale(0.76)" />
          <use href="#portal-canopy-leaf" transform="translate(186 96) rotate(66) scale(0.7)" />
          <use href="#portal-canopy-leaf" transform="translate(1156 0) rotate(154) scale(0.86)" />
          <use href="#portal-canopy-leaf" transform="translate(1082 40) rotate(130) scale(0.76)" />
          <use href="#portal-canopy-leaf" transform="translate(1014 96) rotate(114) scale(0.7)" />
        </g>
      </svg>
    );
  }

  return (
    <svg
      className="portal-ground-art"
      viewBox="0 0 1200 900"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
    >
      <g className="portal-ground-node">
        <circle cx="64" cy="120" r="4" />
        <circle cx="128" cy="316" r="2.6" />
        <circle cx="52" cy="520" r="3.4" />
        <circle cx="116" cy="742" r="2.4" />
        <circle cx="1140" cy="150" r="3.6" />
        <circle cx="1074" cy="352" r="2.4" />
        <circle cx="1152" cy="566" r="4" />
        <circle cx="1088" cy="786" r="2.8" />
      </g>
    </svg>
  );
}

export function PortalGround({ pathname }: { pathname: string }) {
  const growth = BY_SECTION[areaFromPath(pathname)];
  if (!growth) return null;
  return (
    <div className="portal-ground" aria-hidden="true">
      <Art growth={growth} />
    </div>
  );
}
