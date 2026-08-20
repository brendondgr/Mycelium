import * as React from "react";

import { ArrowRightIcon } from "@/components/portal/icons";
import type { SourceLink } from "@/lib/portal/types";

/**
 * Per-source attribution + licence line for a card's footer — the provenance
 * the open-collector migration added that Pivot never carried (plan Phase 9:
 * every opportunity now exposes `source`/`license`/`license_url`/
 * `source_links`). Renders nothing when the item carries none of the three —
 * a pre-migration snapshot row or an area with no licence data — so no card
 * grows an empty footer line.
 *
 * Deliberately muted and small: this is provenance, not a call to action —
 * the outbound "View conference"/"View opportunity" link stays the visually
 * dominant one on the card.
 */
export function SourceFooter({
  license,
  licenseUrl,
  sourceLinks,
  source,
}: {
  license: string;
  licenseUrl: string;
  sourceLinks: SourceLink[];
  /** Raw provider id ("grants:nsf", "conf:ccf_deadlines") — the fallback
   * credit line when `sourceLinks` has nothing to link out to, so a card is
   * never left crediting no one at all. */
  source: string;
}) {
  const hasLinks = sourceLinks.length > 0;
  if (!license && !hasLinks && !source) return null;

  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-[var(--text-muted)]">
      {license ? (
        licenseUrl ? (
          <a
            href={licenseUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-[var(--text-secondary)] hover:underline"
          >
            {license}
          </a>
        ) : (
          <span>{license}</span>
        )
      ) : null}
      {license && (hasLinks || source) ? <span aria-hidden="true">·</span> : null}
      {hasLinks ? (
        <span>
          Source{sourceLinks.length > 1 ? "s" : ""}:{" "}
          {sourceLinks.map((link, index) => (
            <React.Fragment key={`${link.source}-${index}`}>
              {index > 0 ? ", " : ""}
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-[var(--text-secondary)] hover:underline"
              >
                {link.source}
              </a>
            </React.Fragment>
          ))}
        </span>
      ) : source ? (
        <span>via {source}</span>
      ) : null}
    </p>
  );
}

/**
 * The card's closing row: who the listing came from on the left, and the
 * outbound "View …" button justified right.
 *
 * The link used to sit on its own line under the credit line, which read as an
 * afterthought two rows deep in muted text. Pairing them puts the one action a
 * reader takes off the card on the same baseline as the provenance that earns
 * it — and keeps the button visually dominant while the credit stays muted.
 *
 * Renders whenever there is an action, even for an area (fellowships) whose
 * rows carry no licence or source links at all, so the button is never lost
 * with the empty footer.
 */
export function SourceRow({
  license,
  licenseUrl,
  sourceLinks,
  source,
  action,
}: {
  license: string;
  licenseUrl: string;
  sourceLinks: SourceLink[];
  source: string;
  /** The outbound link button. Omitted when the item has no URL. */
  action?: React.ReactNode;
}) {
  const footer = (
    <SourceFooter
      license={license}
      licenseUrl={licenseUrl}
      sourceLinks={sourceLinks}
      source={source}
    />
  );
  if (!action) return footer;
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-[var(--divider)] pt-3">
      {/* `SourceFooter` carries its own top margin for the standalone case;
          inside the row the flex baseline does the spacing. */}
      <div className="min-w-0 flex-1 [&>p]:mt-0">{footer}</div>
      <div className="shrink-0">{action}</div>
    </div>
  );
}

/**
 * The card's one outbound action, as a real button rather than a text link.
 *
 * It used to be an underlined phrase on its own line, which read as a footnote
 * to the footnote above it. Sharing a row with the provenance and carrying a
 * button's shape makes it what it is: the single thing a reader leaves the card
 * to do.
 */
export function ViewLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group inline-flex items-center gap-1.5 rounded-full border border-[color-mix(in_srgb,var(--primary)_40%,transparent)] bg-[color-mix(in_srgb,var(--primary)_8%,transparent)] px-3.5 py-1.5 text-sm font-semibold text-primary transition-colors hover:border-primary hover:bg-[color-mix(in_srgb,var(--primary)_16%,transparent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
      <ArrowRightIcon
        size={14}
        aria-hidden="true"
        className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
      />
    </a>
  );
}
