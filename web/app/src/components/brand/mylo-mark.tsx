import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Mylo — the mushroom scout mascot. A brand illustration with its own fixed
 * palette (not theme tokens); size it via `className` on the wrapper.
 */
export function MyloMark({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block leading-none", className)}
      {...props}
    >
      <svg
        viewBox="0 0 100 112"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="block h-full w-full"
      >
        <g stroke="#C9A35A" strokeWidth="1.4" opacity=".55">
          <path d="M50 96 C42 102 34 101 26 107" />
          <path d="M50 96 C58 102 67 101 76 106" />
          <path d="M50 96 C50 103 50 106 50 110" />
        </g>
        <g fill="#C9A35A" opacity=".75">
          <circle cx="26" cy="107" r="2" />
          <circle cx="76" cy="106" r="2" />
          <circle cx="50" cy="110" r="2" />
        </g>
        <path
          d="M37 60 Q35 93 50 93 Q65 93 63 60 Z"
          fill="#FBF6EC"
          stroke="#E2D6BE"
          strokeWidth="1.2"
        />
        <ellipse cx="50" cy="60" rx="27" ry="5" fill="#7E552F" />
        <path
          d="M23 58 Q23 29 50 29 Q77 29 77 58 Q77 61 73 61 L27 61 Q23 61 23 58 Z"
          fill="#A6713E"
        />
        <circle cx="39" cy="46" r="4" fill="#F1E4CE" />
        <circle cx="57" cy="43" r="5.2" fill="#F1E4CE" />
        <circle cx="65" cy="53" r="3" fill="#F1E4CE" />
        <circle cx="46" cy="52" r="2.4" fill="#F1E4CE" />
        <circle cx="44.5" cy="73" r="2.7" fill="#2E3627" />
        <circle cx="55.5" cy="73" r="2.7" fill="#2E3627" />
        <circle cx="45.3" cy="72.2" r=".8" fill="#fff" />
        <circle cx="56.3" cy="72.2" r=".8" fill="#fff" />
        <circle cx="39" cy="78" r="2.6" fill="#E7C49B" opacity=".75" />
        <circle cx="61" cy="78" r="2.6" fill="#E7C49B" opacity=".75" />
        <path
          d="M46 79 Q50 82.5 54 79"
          stroke="#2E3627"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}
