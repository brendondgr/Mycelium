import * as React from "react";

import { cn } from "@/lib/utils";

type IconButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Accessible label — icon-only buttons need one. */
  label: string;
};

/**
 * A square, rounded icon button for header/toolbar actions (notifications, theme
 * toggle). Always carries an accessible name and a visible focus ring.
 */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ label, className, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        aria-label={label}
        title={label}
        className={cn(
          "relative inline-flex h-[38px] w-[38px] items-center justify-center rounded-[11px] border border-border bg-surface-alt text-[var(--text-secondary)] transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
