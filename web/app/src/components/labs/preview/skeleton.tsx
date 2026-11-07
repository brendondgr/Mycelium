"use client";

/**
 * Placeholder layouts shown while a page "loads".
 *
 * Each one is the shape of the page it stands in for — same head, same
 * toolbar, same columns, cards of the same height — so when the content
 * arrives nothing moves; it only fades in where the placeholders were. The
 * shimmer is decoration and stops under reduced motion or "Motion: None".
 */

function Bar({ w, h = 12, className = "" }: { w: string; h?: number; className?: string }) {
  return <span className={`lx-skel ${className}`} style={{ width: w, height: h }} />;
}

function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="lx-item lx-card lx-skel-card" aria-hidden="true">
      <span className="lx-skel-row">
        <Bar w="92px" h={20} className="lx-skel-pill" />
        <Bar w="70px" />
      </span>
      <Bar w="82%" h={16} />
      {Array.from({ length: lines }, (_, i) => (
        <Bar key={i} w={i === lines - 1 ? "54%" : "96%"} />
      ))}
      <span className="lx-skel-row">
        <Bar w="22px" h={22} className="lx-skel-round" />
        <Bar w="120px" />
      </span>
    </div>
  );
}

function HeadSkeleton({ tools = false }: { tools?: boolean }) {
  return (
    <div className="lx-page-head" aria-hidden="true">
      <div className="lx-skel-stack">
        <Bar w="180px" h={30} />
        <Bar w="320px" />
      </div>
      {tools ? (
        <span className="lx-skel-row">
          <Bar w="120px" h={32} className="lx-skel-pill" />
          <Bar w="90px" h={32} className="lx-skel-pill" />
        </span>
      ) : null}
    </div>
  );
}

function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="lx-panel-box lx-skel-panel" aria-hidden="true">
      <Bar w="40%" h={18} />
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="lx-skel-stack">
          <Bar w="88%" />
          <Bar w="62%" />
        </span>
      ))}
    </div>
  );
}

export function PageSkeleton({ kind, reader }: { kind: string; reader?: boolean }) {
  const label = <span className="lx-sr">Loading…</span>;

  if (kind === "overview") {
    return (
      <div role="status" className="lx-skeleton">
        {label}
        <HeadSkeleton tools />
        <div className="lx-note lx-skel-note" aria-hidden="true">
          <Bar w="44px" h={44} className="lx-skel-round" />
          <span className="lx-skel-stack lx-grow">
            <Bar w="94%" />
            <Bar w="70%" />
          </span>
        </div>
        <div className="lx-split">
          <div className="lx-split-main">
            <PanelSkeleton rows={4} />
            <PanelSkeleton rows={5} />
          </div>
          <div className="lx-split-side">
            <PanelSkeleton rows={3} />
            <PanelSkeleton rows={4} />
          </div>
        </div>
      </div>
    );
  }

  if (kind === "search") {
    return (
      <div role="status" className="lx-skeleton lx-skel-search">
        {label}
        <span className="lx-skel-stack lx-skel-center" aria-hidden="true">
          <Bar w="320px" h={34} />
          <Bar w="min(640px, 100%)" h={46} className="lx-skel-pill" />
        </span>
        <div className="lx-feed-items">
          <CardSkeleton lines={2} />
          <CardSkeleton lines={2} />
        </div>
      </div>
    );
  }

  if (kind === "feed") {
    return (
      <div role="status" className="lx-skeleton">
        {label}
        <HeadSkeleton />
        <span className="lx-skel-row lx-skel-toolbar" aria-hidden="true">
          <Bar w="100%" h={38} className="lx-skel-pill" />
          <Bar w="130px" h={38} className="lx-skel-pill" />
        </span>
        <span className="lx-skel-row lx-skel-toolbar" aria-hidden="true">
          {["70px", "84px", "76px", "100px", "72px"].map((w, i) => (
            <Bar key={i} w={w} h={28} className="lx-skel-pill" />
          ))}
        </span>
        <div className="lx-feed-wrap" data-reader={reader || undefined}>
          <div className="lx-feed-items">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
          {reader ? (
            <div className="lx-reading-pane lx-panel-box lx-skel-panel" aria-hidden="true">
              <Bar w="110px" h={20} className="lx-skel-pill" />
              <Bar w="86%" h={24} />
              <Bar w="60%" h={24} />
              <Bar w="100%" h={120} />
              <Bar w="40%" />
              <Bar w="90%" />
              <Bar w="74%" />
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  if (kind === "settings") {
    return (
      <div role="status" className="lx-skeleton">
        {label}
        <HeadSkeleton />
        <div className="lx-settings-grid">
          <span className="lx-skel-stack" aria-hidden="true">
            {Array.from({ length: 7 }, (_, i) => (
              <Bar key={i} w={i % 4 === 0 ? "40%" : "86%"} h={i % 4 === 0 ? 10 : 30} />
            ))}
          </span>
          <PanelSkeleton rows={4} />
        </div>
      </div>
    );
  }

  return (
    <div role="status" className="lx-skeleton">
      {label}
      <HeadSkeleton />
      <PanelSkeleton rows={4} />
    </div>
  );
}
