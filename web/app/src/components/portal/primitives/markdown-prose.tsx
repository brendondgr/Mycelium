import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A small, dependency-free markdown renderer for the controlled markdown the Mylo
 * Report generator emits: `##` / `###` headings, `-`/`*` bullet lists, blank-line
 * paragraphs, `**bold**`, and `[text](url)` links. It is deliberately NOT a full
 * CommonMark engine — it renders exactly the constructs the backend produces
 * (see `apps.content.briefing_agents`), so we avoid pulling in a markdown
 * dependency for a single, well-scoped surface.
 *
 * Anything it doesn't recognize is rendered as plain text, so an unexpected
 * construct degrades to readable prose rather than breaking.
 */

const LINK_CLASS =
  "text-primary underline underline-offset-2 hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm";

// Matches, in one pass: **bold** or [text](url). Nested content is rendered
// recursively so `**[Title](url)**` yields a bold link. A fresh instance is
// created per `renderInline` call: the regex is stateful (global flag), and
// sharing one across the recursive calls would let an inner call reset the
// outer loop's `lastIndex`, re-matching the same segment forever (a browser
// freeze on any body containing bold or a link).
const inlinePattern = () => /(\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\))/g;

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  const INLINE = inlinePattern();
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[2] !== undefined) {
      nodes.push(
        <strong key={`${keyBase}-b${i}`} className="font-semibold text-[var(--text-primary)]">
          {renderInline(match[2], `${keyBase}-b${i}`)}
        </strong>,
      );
    } else if (match[3] !== undefined) {
      nodes.push(
        <a
          key={`${keyBase}-a${i}`}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className={LINK_CLASS}
        >
          {renderInline(match[3], `${keyBase}-a${i}`)}
        </a>,
      );
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ").trim() });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{2,3})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({
        kind: "heading",
        level: heading[1].length === 2 ? 2 : 3,
        text: heading[2].trim(),
      });
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1].trim());
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
}

export function MarkdownProse({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const blocks = React.useMemo(() => parseBlocks(text || ""), [text]);
  if (blocks.length === 0) return null;

  return (
    <div className={cn("text-[15px] leading-relaxed text-[var(--text-secondary)]", className)}>
      {blocks.map((block, index) => {
        const key = `blk-${index}`;
        if (block.kind === "heading") {
          const Tag = block.level === 2 ? "h2" : "h3";
          return (
            <Tag
              key={key}
              className={cn(
                "font-serif font-semibold text-[var(--text-primary)] first:mt-0",
                block.level === 2 ? "mt-5 mb-2 text-[18px]" : "mt-4 mb-1.5 text-[15px]",
              )}
            >
              {renderInline(block.text, key)}
            </Tag>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={key} className="mt-2 mb-3 list-disc space-y-1 pl-5 first:mt-0 [text-wrap:pretty]">
              {block.items.map((item, i) => (
                <li key={`${key}-li${i}`}>{renderInline(item, `${key}-li${i}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={key} className="mt-3 first:mt-0 [text-wrap:pretty]">
            {renderInline(block.text, key)}
          </p>
        );
      })}
    </div>
  );
}
