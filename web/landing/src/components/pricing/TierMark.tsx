/**
 * Botanical growth marks for the pricing tiers.
 *
 * The tier names already describe a progression — a single spore, a lab's
 * connected network, a full canopy — so the marks draw that rather than
 * reaching for another generic icon set. Line art in `currentColor` at a
 * single weight, so they sit quietly next to the price.
 */
type TierMarkProps = {
  id: string;
  className?: string;
};

const strokeProps = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function TierMark({ id, className }: TierMarkProps) {
  if (id === "spore") {
    return (
      <svg viewBox="0 0 40 40" className={className} aria-hidden="true" {...strokeProps}>
        <circle cx="20" cy="12" r="5.5" />
        <path d="M20 17.5v14" />
        <path d="M20 25c-3.6 0-6 1.9-7.6 4.6" />
        <path d="M20 25c3.6 0 6 1.9 7.6 4.6" />
        <circle cx="12.4" cy="29.6" r="1.1" fill="currentColor" stroke="none" />
        <circle cx="27.6" cy="29.6" r="1.1" fill="currentColor" stroke="none" />
      </svg>
    );
  }

  if (id === "canopy") {
    return (
      <svg viewBox="0 0 40 40" className={className} aria-hidden="true" {...strokeProps}>
        <path d="M5.5 18.5C8.5 9 13.8 4.5 20 4.5s11.5 4.5 14.5 14" />
        <path d="M20 9.5v25" />
        <path d="M20 17c-3.4 0-6.2-1.4-8.4-3.6" />
        <path d="M20 17c3.4 0 6.2-1.4 8.4-3.6" />
        <path d="M20 26.5c-4.2 0-7.6 1.8-9.8 4.8" />
        <path d="M20 26.5c4.2 0 7.6 1.8 9.8 4.8" />
        <circle cx="11.6" cy="13.4" r="1.2" fill="currentColor" stroke="none" />
        <circle cx="28.4" cy="13.4" r="1.2" fill="currentColor" stroke="none" />
        <circle cx="20" cy="4.5" r="1.2" fill="currentColor" stroke="none" />
      </svg>
    );
  }

  // "mycelium-lab" and any future mid tier: a small connected network.
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true" {...strokeProps}>
      <path d="M20 13.5 11 27M20 13.5 29 27M11 27h18" />
      <circle cx="20" cy="10" r="4" />
      <circle cx="10.5" cy="28.5" r="3.2" />
      <circle cx="29.5" cy="28.5" r="3.2" />
    </svg>
  );
}
