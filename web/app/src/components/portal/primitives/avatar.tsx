import { cn } from "@/lib/utils";

// Three brand fills, chosen deterministically so the same person keeps the same
// color across the dashboard without sending color from the backend.
const COLORS = ["var(--primary)", "var(--brand-secondary)", "var(--accent)"];

function pickColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  return COLORS[Math.abs(hash) % COLORS.length];
}

type AvatarProps = {
  initials: string;
  /** Stable seed for the color (e.g. username). Defaults to the initials. */
  seed?: string;
  size?: number;
  className?: string;
  title?: string;
};

/** A round initials avatar with a deterministic brand fill. */
export function Avatar({ initials, seed, size = 32, className, title }: AvatarProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-[#fffdf8]",
        className,
      )}
      style={{
        width: size,
        height: size,
        background: pickColor(seed ?? initials),
        fontSize: Math.round(size * 0.36),
      }}
    >
      {initials}
    </span>
  );
}
