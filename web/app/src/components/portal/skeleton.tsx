"use client";

/**
 * Placeholder layouts shown while a page's first data loads (ported from the
 * `/labs` playground).
 *
 * Each one is the shape of the page it stands in for — same head, same
 * toolbar, same columns, cards of the same height — so when the content
 * arrives nothing moves; it only fades in where the placeholders were. The
 * shimmer is decoration and stops under reduced motion or "Motion: None".
 */

export function Bar({ w, h = 12, className = "" }: { w: string; h?: number; className?: string }) {
  return <span className={`ws-skel ${className}`} style={{ width: w, height: h }} />;
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="ws-item ws-skel-card" aria-hidden="true">
      <span className="ws-skel-row">
        <Bar w="92px" h={20} className="ws-skel-pill" />
        <Bar w="70px" />
      </span>
      <Bar w="82%" h={16} />
      {Array.from({ length: lines }, (_, i) => (
        <Bar key={i} w={i === lines - 1 ? "54%" : "96%"} />
      ))}
      <span className="ws-skel-row">
        <Bar w="22px" h={22} className="ws-skel-round" />
        <Bar w="120px" />
      </span>
    </div>
  );
}

function HeadSkeleton({ tools = false }: { tools?: boolean }) {
  return (
    <div className="ws-page-head" aria-hidden="true">
      <div className="ws-skel-stack">
        <Bar w="180px" h={30} />
        <Bar w="320px" />
      </div>
      {tools ? (
        <span className="ws-skel-row">
          <Bar w="120px" h={32} className="ws-skel-pill" />
          <Bar w="90px" h={32} className="ws-skel-pill" />
        </span>
      ) : null}
    </div>
  );
}

export function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="ws-panel-box ws-skel-panel" aria-hidden="true">
      <Bar w="40%" h={18} />
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="ws-skel-stack">
          <Bar w="88%" />
          <Bar w="62%" />
        </span>
      ))}
    </div>
  );
}

export function PageSkeleton({ kind, reader }: { kind: string; reader?: boolean }) {
  const label = <span className="ws-sr">Loading…</span>;

  if (kind === "overview") {
    return (
      <div role="status" className="ws-skeleton">
        {label}
        <HeadSkeleton tools />
        <div className="ws-note ws-skel-note" aria-hidden="true">
          <Bar w="44px" h={44} className="ws-skel-round" />
          <span className="ws-skel-stack ws-grow">
            <Bar w="94%" />
            <Bar w="70%" />
          </span>
        </div>
        <div className="ws-split">
          <div className="ws-split-main">
            <PanelSkeleton rows={4} />
            <PanelSkeleton rows={5} />
          </div>
          <div className="ws-split-side">
            <PanelSkeleton rows={3} />
            <PanelSkeleton rows={4} />
          </div>
        </div>
      </div>
    );
  }

  if (kind === "search") {
    return (
      <div role="status" className="ws-skeleton ws-skel-search">
        {label}
        <span className="ws-skel-stack ws-skel-center" aria-hidden="true">
          <Bar w="320px" h={34} />
          <Bar w="min(640px, 100%)" h={46} className="ws-skel-pill" />
        </span>
        <div className="ws-feed-items">
          <CardSkeleton lines={2} />
          <CardSkeleton lines={2} />
        </div>
      </div>
    );
  }

  if (kind === "feed") {
    return (
      <div role="status" className="ws-skeleton">
        {label}
        <HeadSkeleton />
        <span className="ws-skel-row ws-skel-toolbar" aria-hidden="true">
          <Bar w="100%" h={38} className="ws-skel-pill" />
          <Bar w="130px" h={38} className="ws-skel-pill" />
        </span>
        <span className="ws-skel-row ws-skel-toolbar" aria-hidden="true">
          {["70px", "84px", "76px", "100px", "72px"].map((w, i) => (
            <Bar key={i} w={w} h={28} className="ws-skel-pill" />
          ))}
        </span>
        <div className="ws-feed-wrap" data-reader={reader || undefined}>
          <div className="ws-feed-items">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
          {reader ? (
            <div className="ws-reading-pane ws-panel-box ws-skel-panel" aria-hidden="true">
              <Bar w="110px" h={20} className="ws-skel-pill" />
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
      <div role="status" className="ws-skeleton">
        {label}
        <HeadSkeleton />
        <div className="ws-settings-grid">
          <span className="ws-skel-stack" aria-hidden="true">
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
    <div role="status" className="ws-skeleton">
      {label}
      <HeadSkeleton />
      <PanelSkeleton rows={4} />
    </div>
  );
}

/** A feed's card list alone, for a feed whose head and toolbar are already drawn. */
export function FeedListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div role="status" className="ws-skeleton">
      <span className="ws-sr">Loading…</span>
      <div className="ws-feed-items">
        {Array.from({ length: count }, (_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

/** A few placeholder lines inside a panel that is already on the page. */
export function LinesSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" className="ws-skel-stack">
      <span className="ws-sr">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="ws-skel-stack" aria-hidden="true">
          <Bar w="88%" />
          <Bar w="62%" />
        </span>
      ))}
    </div>
  );
}
