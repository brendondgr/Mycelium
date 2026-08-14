import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A small, dependency-free markdown renderer for the controlled markdown the Mylo
 * Report generator emits: `##` / `###` / `####` headings, `N.` numbered items with
 * their explanation on the following line, `-`/`*` bullet lists, blank-line
 * paragraphs, `**bold**`, and `[text](url)` links. It is deliberately NOT a full
 * CommonMark engine — it renders exactly the constructs the backend produces
 * (see `apps.content.briefing_sections`, which documents the grammar), so we avoid
 * pulling in a markdown dependency for a single, well-scoped surface.
 *
 * The two facts a reader scans a ranked list for — whether an item is new, and how
 * well it matches — are lifted out of the run of text as chips, the same way the
 * PDF report renders them. The report is one document with two renderers; they are
 * not allowed to disagree about what stands out.
 *
 * Anything it doesn't recognize is rendered as plain text, so an unexpected
 * construct degrades to readable prose rather than breaking.
 */

const LINK_CLASS =
  "text-primary underline underline-offset-2 hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm";

// Rounded containers, not highlighter stripes — the same shape the PDF's chips use.
const MATCH_CHIP_CLASS =
  "inline-block rounded-full bg-primary/12 px-2 py-0.5 text-[13px] font-semibold text-primary";
const NEW_CHIP_CLASS =
  "inline-block rounded-full border border-brand-accent px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-accent";

// Matches, in one pass: **bold**, [text](url), or an `88% match` signal. Nested
// content is rendered recursively so `**[Title](url)**` yields a bold link. A fresh
// instance is created per `renderInline` call: the regex is stateful (global flag),
// and sharing one across the recursive calls would let an inner call reset the
// outer loop's `lastIndex`, re-matching the same segment forever (a browser
// freeze on any body containing bold or a link).
const inlinePattern = () =>
  /(\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)|(\d{1,3})%\s+match\b)/g;

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  const INLINE = inlinePattern();
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[2] !== undefined) {
      // `**NEW**` is the report's entrant marker, not emphasis for its own sake.
      if (match[2].trim() === "NEW") {
        nodes.push(
          <span key={`${keyBase}-n${i}`} className={NEW_CHIP_CLASS}>
            New
          </span>,
        );
      } else {
        nodes.push(
          <strong key={`${keyBase}-b${i}`} className="font-semibold text-[var(--text-primary)]">
            {renderInline(match[2], `${keyBase}-b${i}`)}
          </strong>,
        );
      }
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
    } else if (match[5] !== undefined) {
      nodes.push(
        <span key={`${keyBase}-m${i}`} className={MATCH_CHIP_CLASS}>
          {match[5]}% match
        </span>,
      );
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type OrderedItem = { marker: string; text: string; note: string };

type Block =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "ordered"; items: OrderedItem[] }
  | { kind: "paragraph"; text: string };

const HEADING = /^(#{2,4})\s+(.*)$/;
const BULLET = /^[-*]\s+(.*)$/;
// A ranked item: `1. **[Title](url)** — **NEW** · 88% match`.
const ORDERED = /^(\d{1,3})[.)]\s+(.*)$/;

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let ordered: OrderedItem[] = [];

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
  const flushOrdered = () => {
    if (ordered.length) {
      blocks.push({ kind: "ordered", items: ordered });
      ordered = [];
    }
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushOrdered();
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      // A blank line does not close an ordered list: the generator separates its
      // ranked items with one, and closing here would split a single ranking into
      // a run of one-item lists.
      flushParagraph();
      flushList();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      flushAll();
      blocks.push({
        kind: "heading",
        level: heading[1].length as 2 | 3 | 4,
        text: heading[2].trim(),
      });
      continue;
    }
    const numbered = ORDERED.exec(line);
    if (numbered) {
      flushParagraph();
      flushList();
      ordered.push({ marker: numbered[1], text: numbered[2].trim(), note: "" });
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      flushAll();
      list.push(bullet[1].trim());
      continue;
    }
    if (ordered.length) {
      // The line after a ranked item is that item's explanation, so it stays
      // attached to it rather than becoming a paragraph that outlives the list.
      const current = ordered[ordered.length - 1];
      current.note = current.note ? `${current.note} ${line}` : line;
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushAll();
  return blocks;
}

// A focus theme (`####`) is a pill, and it is *larger* than the entries under it —
// set smaller, a heading reads as a caption on the item that follows it.
const HEADING_CLASS: Record<2 | 3 | 4, string> = {
  2: "mt-6 mb-2 text-[18px] font-serif font-semibold text-[var(--text-primary)]",
  3: "mt-5 mb-1.5 text-[15px] font-serif font-semibold text-[var(--text-primary)]",
  4: "mt-5 mb-2.5 inline-block rounded-full border border-border bg-surface-alt px-3 py-1 text-[15px] font-semibold text-brand-primary-hover",
};

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
          const Tag = block.level === 2 ? "h2" : block.level === 3 ? "h3" : "h4";
          return (
            <Tag key={key} className={cn(HEADING_CLASS[block.level], "first:mt-0")}>
              {renderInline(block.text, key)}
            </Tag>
          );
        }
        if (block.kind === "ordered") {
          return (
            <ol key={key} className="mt-3 mb-3 list-none space-y-3 first:mt-0">
              {block.items.map((item, i) => (
                <li key={`${key}-oi${i}`} className="flex gap-2.5">
                  <span className="shrink-0 pt-px font-serif font-semibold tabular-nums text-[var(--text-muted)]">
                    {item.marker}.
                  </span>
                  <span className="min-w-0 [text-wrap:pretty]">
                    <span className="block">{renderInline(item.text, `${key}-oi${i}`)}</span>
                    {item.note ? (
                      <span className="mt-0.5 block text-[var(--text-secondary)]">
                        {renderInline(item.note, `${key}-on${i}`)}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
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
