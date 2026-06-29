import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The line-art icon vocabulary used across the dashboard, ported from the design
 * proposal. Every icon is a 24×24 stroke icon that inherits `currentColor`, so
 * callers control color/size with text utilities or `size`. Kept in one file so
 * sections share exactly one visual language.
 */
export type IconProps = React.SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, className, children, strokeWidth = 1.7, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("shrink-0", className)}
      {...props}
    >
      {children}
    </svg>
  );
}

/** Mylo's spore mark, line-art. Dots inherit `currentColor` via fill. */
export function MyloGlyph({ size = 20, className, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      aria-hidden="true"
      className={cn("shrink-0", className)}
      {...props}
    >
      <circle cx="12" cy="13" r="2.4" />
      <path d="M12 10.6V5M12 5l-2.4-1.4M12 5l2.4-1.4M10.4 14.2 6.6 17M13.6 14.2 17.4 17" />
      <circle cx="6.6" cy="17" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="17.4" cy="17" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="12" cy="3.6" r="1.3" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Small mushroom node (lab marker in the switcher, "why it matters"). */
export function SporeNode({ size = 16, className, ...props }: IconProps) {
  return (
    <Svg size={size} strokeWidth={1.6} className={className} {...props}>
      <circle cx="12" cy="13" r="2" />
      <path d="M12 11V7M12 7l-2-1.2M12 7l2-1.2M10.5 14.5 8 17M13.5 14.5 16 17" />
    </Svg>
  );
}

export function GridIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="7" height="7" rx="1.6" />
      <rect x="13" y="4" width="7" height="7" rx="1.6" />
      <rect x="4" y="13" width="7" height="7" rx="1.6" />
      <rect x="13" y="13" width="7" height="7" rx="1.6" />
    </Svg>
  );
}

export function ReportIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <rect x="4" y="5" width="16" height="15" rx="2.5" />
      <path d="M4 9.5h16M8.5 3v4M15.5 3v4M8 14h8M8 17h5" />
    </Svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <rect x="4" y="5" width="16" height="15" rx="2.5" />
      <path d="M4 9.5h16M8.5 3v4M15.5 3v4" />
    </Svg>
  );
}

export function SparkleIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <path d="M12 3l2.3 6.1L20.5 11l-6.2 1.9L12 19l-2.3-6.1L3.5 11l6.2-1.9z" />
    </Svg>
  );
}

export function FolderIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <path d="M4 7a2 2 0 012-2h3.5l2 2H18a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2z" />
    </Svg>
  );
}

export function TargetIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </Svg>
  );
}

export function MembersIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c0-3 2.7-5 5.5-5s5.5 2 5.5 5" />
      <circle cx="17.5" cy="8.5" r="2.3" />
      <path d="M16.5 14c2.8 0 4.5 2 4.5 5" />
    </Svg>
  );
}

export function DocumentIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M14 3v4h4" />
      <path d="M9.5 12h5M9.5 15.5h5" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M20 6L9 17l-5-5" />
    </Svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.8} {...props}>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4-4" />
    </Svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 16V11a6 6 0 1112 0v5l1.6 2H4.4z" />
      <path d="M10 21h4" />
    </Svg>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
    </Svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M20 14a8 8 0 11-9.8-9.8A6.5 6.5 0 0020 14z" />
    </Svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M6 9l6 6 6-6" />
    </Svg>
  );
}

export function ChevronUpIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2.2} {...props}>
      <path d="M6 15l6-6 6 6" />
    </Svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M9 6l6 6-6 6" />
    </Svg>
  );
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M15 6l-6 6 6 6" />
    </Svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Svg>
  );
}

export function BankIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.7} {...props}>
      <path d="M12 3v18M6 7l6-4 6 4M5 11h14" />
    </Svg>
  );
}

export function AlertTriangleIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4M12 16.5h.01" />
    </Svg>
  );
}

export function BookmarkIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.6} {...props}>
      <path d="M7 3h10v18l-5-3-5 3z" />
    </Svg>
  );
}

export function LinkIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.8} {...props}>
      <path d="M9 15l6-6M11 7l1-1a3.5 3.5 0 015 5l-1 1M13 17l-1 1a3.5 3.5 0 01-5-5l1-1" />
    </Svg>
  );
}

export function EditIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.8} {...props}>
      <path d="M4 20h4l10-10-4-4L4 16z" />
    </Svg>
  );
}

export function ListIcon(props: IconProps) {
  return (
    <Svg strokeWidth={1.8} {...props}>
      <path d="M5 6h14M5 11h14M5 16h9" />
    </Svg>
  );
}
