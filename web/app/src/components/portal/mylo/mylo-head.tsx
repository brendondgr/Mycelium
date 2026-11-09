/**
 * Mylo's painted head (`public/mylo-portrait-*.webp`) — never the SVG rig.
 * Decorative: whatever it sits beside carries the words. `working` lets it
 * float gently; it stays still under reduced motion and Motion: None.
 */
export function MyloHead({ size = 24, working = false }: { size?: number; working?: boolean }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static mascot art
    <img
      src={size > 40 ? "/mylo-portrait-128.webp" : "/mylo-portrait-64.webp"}
      srcSet={size > 40 ? "/mylo-portrait-128.webp 1x, /mylo-portrait-256.webp 2x" : "/mylo-portrait-64.webp 1x, /mylo-portrait-128.webp 2x"}
      alt=""
      width={size}
      height={size}
      className="ws-mylo-head"
      data-working={working || undefined}
      draggable={false}
    />
  );
}
