"use client";

import * as React from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

/**
 * One formula, typeset by KaTeX. Loaded only when an answer has math.
 *
 * The markup set here is KaTeX's own output, not the model's text: KaTeX
 * escapes what it is given, and `trust: false` refuses the commands that
 * could carry a link or raw HTML. A formula KaTeX cannot read is shown as
 * its source.
 */
export default function MathView({ tex, display }: { tex: string; display: boolean }) {
  const html = React.useMemo(() => {
    try {
      return katex.renderToString(tex, {
        displayMode: display,
        throwOnError: false,
        trust: false,
        strict: "ignore",
        maxExpand: 500,
        maxSize: 20,
      });
    } catch {
      return null;
    }
  }, [tex, display]);
  if (html === null) return <code className="ws-mylo-code-inline">{tex}</code>;
  return display ? (
    <div className="ws-mylo-math" dangerouslySetInnerHTML={{ __html: html }} />
  ) : (
    <span dangerouslySetInnerHTML={{ __html: html }} />
  );
}
