import * as React from "react";

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
