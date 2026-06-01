import * as React from "react";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

type NavLink = { href: string; label: string };

type MobileNavProps = {
  links: readonly NavLink[];
  loginHref: string;
  ctaHref: string;
  ctaLabel?: string;
};

export function MobileNav({
  links,
  loginHref,
  ctaHref,
  ctaLabel = "Get started",
}: MobileNavProps) {
  const [open, setOpen] = React.useState(false);
  const panelId = React.useId();
  const buttonRef = React.useRef<HTMLButtonElement>(null);

  const close = React.useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  React.useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  return (
    <div className="relative lg:hidden">
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex size-11 items-center justify-center rounded-md border border-border bg-card text-foreground"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <X aria-hidden className="size-5" /> : <Menu aria-hidden className="size-5" />}
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-50 bg-[rgb(46_54_39/35%)]"
          role="presentation"
          onClick={close}
        />
      ) : null}

      <nav
        id={panelId}
        aria-label="Mobile"
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-[min(100%,20rem)] flex-col gap-6 border-l border-border bg-card p-6 shadow-xl transition-transform duration-200 lg:hidden",
          open ? "translate-x-0" : "pointer-events-none translate-x-full",
        )}
        hidden={!open}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[var(--text-primary)]">Menu</p>
          <button
            type="button"
            className="inline-flex size-10 items-center justify-center rounded-md border border-border"
            aria-label="Close menu"
            onClick={close}
          >
            <X aria-hidden className="size-5" />
          </button>
        </div>

        <ul className="flex flex-col gap-1">
          {links.map((link) => (
            <li key={link.href}>
              <a
                className="block rounded-md px-3 py-2.5 text-sm font-medium text-[var(--text-primary)] hover:bg-secondary"
                href={link.href}
                onClick={close}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="mt-auto flex flex-col gap-3 border-t border-border pt-6">
          <a
            className="inline-flex min-h-11 items-center justify-center rounded-full border border-border px-4 text-sm font-medium"
            href={loginHref}
            onClick={close}
          >
            Log in
          </a>
          <a
            className="inline-flex min-h-11 items-center justify-center rounded-full bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-brand-primary-hover"
            href={ctaHref}
            onClick={close}
          >
            {ctaLabel}
          </a>
        </div>
      </nav>
    </div>
  );
}
