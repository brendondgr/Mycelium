"use client";

import * as React from "react";

import { ArrowRightIcon } from "@/components/portal/icons";
import { VerdictBadge } from "@/components/portal/primitives/verdict-badge";
import type { Verdict } from "@/lib/portal/types";
import {
  ReportEntry,
  ReportFlag,
  splitRationale,
} from "@/components/portal/primitives/report-entry";
import { formatIsoDate } from "@/components/portal/sections/opportunity-bits";
import { cn } from "@/lib/utils";

/**
 * A small, dependency-free renderer for the controlled markdown the Mylo Report
 * generator emits: `##` / `###` / `####` headings, `N.` numbered items with their
 * explanation on the following line, `-`/`*` bullet lists, blank-line paragraphs,
 * `**bold**`, and `[text](url)` links. It is deliberately NOT a full CommonMark
 * engine — it renders exactly the constructs the backend produces (see
 * `apps.content.briefing_sections`, which documents the grammar), so we avoid
 * pulling in a markdown dependency for a single, well-scoped surface.
 *
 * It renders the same **document** the PDF does, in the app's own materials. Both
 * carry the report's hierarchy — part, category, focus theme — and both present a
 * ranked item through the one entry shape described in `report-entry.tsx`: rank and
 * title, the insight, the note, and a meta rail carrying the verdict chip, the
 * flags, and the link out, with the item's dates in a strip beneath. The PDF's
 * `_entry_row` draws the same four zones in the same order — the two renderers
 * differ in materials, not in document.
 *
 * Anything it doesn't recognize is rendered as plain text, so an unexpected
 * construct — including a report written before this grammar existed — degrades to
 * readable prose rather than breaking.
 */

const LINK_CLASS =
  "text-primary underline underline-offset-2 hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm";

// Rounded containers, not highlighter stripes — the same shape the PDF's chips use.
const NEW_CHIP_CLASS =
  "inline-block rounded-full border border-brand-accent px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-accent";

// Matches, in one pass: **bold**, [text](url), or a verdict word. Nested
// content is rendered recursively so `**[Title](url)**` yields a bold link. A fresh
// instance is created per `renderInline` call: the regex is stateful (global flag),
// and sharing one across the recursive calls would let an inner call reset the
// outer loop's `lastIndex`, re-matching the same segment forever (a browser
// freeze on any body containing bold or a link).
const inlinePattern = () =>
  /(\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)|\b(Read|Skim|File)\b)/g;

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
        <VerdictBadge
          key={`${keyBase}-m${i}`}
          verdict={match[5].toLowerCase() as Verdict}
          size="sm"
        />,
      );
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type OrderedItem = {
  marker: string;
  text: string;
  note: string;
  isNew: boolean;
  verdict: Verdict | null;
  deadline: string;
};

type Block =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "list"; items: string[] }
  /** `noun` is the category heading this ranking sits under, singularised — it is
   * what the rail's link says ("Open grant"), and it is the only thing in the
   * entry that knows what kind of item it is describing. */
  | { kind: "ordered"; items: OrderedItem[]; noun: string }
  | { kind: "paragraph"; text: string };

const HEADING = /^(#{2,4})\s+(.*)$/;
const BULLET = /^[-*]\s+(.*)$/;
// A ranked item: `1. **[Title](url)** — **NEW** · Read`.
const ORDERED = /^(\d{1,3})[.)]\s+(.*)$/;

// The three signals a ranked item's title line carries. Each is pulled out and
// given its own element, so the title is a title — left inline they were a run of
// punctuation between the reader and the thing they were scanning for.
const NEW_SIGNAL = /\*\*NEW\*\*/i;
const VERDICT_SIGNAL = /\b(Read|Skim|File)\b/;
const DEADLINE_SIGNAL = /\bdeadline\s+(\d{4}-\d{2}-\d{2})\b/i;
// Whatever separators the removed signals leave stranded at the end of the line.
const TRAILING_SEPARATORS = /[\s·•—–-]+$/;

/**
 * Split a ranked item's title line into its title and its signals.
 *
 * Order-independent, because the line is model-written as often as it is
 * generated: each signal is matched wherever it sits, removed, and the separators
 * it leaves behind are cleaned off the tail. Mirrors `_split_item_line` in
 * `apps/content/daily_report_pdf.py` — the two renderers read one grammar.
 */
function splitItemLine(line: string): Omit<OrderedItem, "marker" | "note"> {
  const isNew = NEW_SIGNAL.test(line);
  let rest = line.replace(NEW_SIGNAL, "");

  const matched = VERDICT_SIGNAL.exec(rest);
  const verdict = matched ? (matched[1].toLowerCase() as Verdict) : null;
  rest = rest.replace(VERDICT_SIGNAL, "");

  const due = DEADLINE_SIGNAL.exec(rest);
  const deadline = due ? due[1] : "";
  rest = rest.replace(DEADLINE_SIGNAL, "");

  // Collapse the separator runs the removals opened up mid-line, then trim.
  rest = rest.replace(/\s*·\s*(?=[·•—–-]|\s*$)/g, " ");
  return {
    text: rest.replace(TRAILING_SEPARATORS, "").trim(),
    isNew,
    verdict,
    deadline,
  };
}

/** "Papers" -> "paper". The report's four category headings are all plain plurals. */
function sectionNoun(heading: string): string {
  const label = heading.trim().toLowerCase();
  return label.endsWith("s") ? label.slice(0, -1) : label;
}

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let ordered: OrderedItem[] = [];
  // The `###` category currently open — Papers / Grants / Fellowships /
  // Conferences. A ranking inherits it so its link can say "Open grant" rather
  // than a generic "Open". A `####` focus theme does not change it.
  let noun = "item";

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
      blocks.push({ kind: "ordered", items: ordered, noun });
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
      const level = heading[1].length as 2 | 3 | 4;
      const text = heading[2].trim();
      if (level === 3) noun = sectionNoun(text);
      blocks.push({ kind: "heading", level, text });
      continue;
    }
    const numbered = ORDERED.exec(line);
    if (numbered) {
      flushParagraph();
      flushList();
      ordered.push({
        marker: numbered[1],
        note: "",
        ...splitItemLine(numbered[2].trim()),
      });
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

/**
 * The report's three heading levels, in the order the document nests them: a part
 * (the reader's own section, or a project), a category within it, and a focus
 * theme within that. Each is visibly a step down from the one above, and the theme
 * is a pill because a theme is a label rather than a sentence.
 *
 * A neutral pill rather than `ClusterBadge`: that badge keys its colour on a
 * cluster **id**, and the report body carries only the label. A badge that looked
 * like a cluster badge but coloured a cluster differently from the same cluster on
 * the feed would be worse than no colour at all.
 */
const HEADING_CLASS: Record<2 | 3 | 4, string> = {
  2: "mt-7 mb-3 border-b border-[var(--divider)] pb-1.5 font-serif text-[19px] font-semibold text-[var(--text-primary)]",
  3: "mt-5 mb-1 font-serif text-[15px] font-semibold text-[var(--text-primary)]",
  4: "mt-4 mb-1 inline-block rounded-full border border-border bg-surface-alt px-3 py-1 text-[14px] font-semibold text-brand-primary-hover",
};

/**
 * The item's own URL, when its whole title is one link (`**[Title](url)**`).
 *
 * Only that shape. A title with a link buried inside it is not a title that
 * *is* a link, and following it from a "Open paper" control at the other end of
 * the entry would take the reader somewhere the title never offered.
 */
const WHOLE_TITLE_LINK = /^\*{0,2}\[([^\]]+)\]\(([^)\s]+)\)\*{0,2}$/;

/** `[label, url]` when the whole title is one link; `["", ""]` otherwise. */
function titleLink(text: string): [string, string] {
  const found = WHOLE_TITLE_LINK.exec(text.trim());
  return found ? [found[1], found[2]] : ["", ""];
}

/**
 * One ranked entry, in the report's shared four-zone shape (`report-entry.tsx`).
 *
 * The rationale is split: its first sentence becomes the insight — the ruled quote
 * that says why this is in front of the reader — and the rest becomes the note.
 * The date leaves the title line entirely for the strip beneath the entry, where a
 * deadline is reference rather than an alarm. That line was at its worst on
 * conferences, where a red `Deadline 2026-09-15` sat directly under a venue title
 * without ever saying which of the venue's rounds it meant.
 */
function OrderedEntry({
  item,
  keyBase,
  noun,
}: {
  item: OrderedItem;
  keyBase: string;
  /** The category's singular noun, for the rail's link ("Open conference"). */
  noun: string;
}) {
  const [label, url] = titleLink(item.text);
  const { insight, note } = splitRationale(item.note);

  // A linked title, set as a title. The old entry rendered it in link green with
  // an underline, which made the loudest thing in every row the fact that it was
  // clickable rather than what it said — and the rail already carries an explicit
  // way out. Here the title reads as a title and stays clickable, underlining only
  // on hover.
  const title = url ? (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-sm text-[var(--text-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
    </a>
  ) : (
    renderInline(item.text, `${keyBase}-t`)
  );

  return (
    <li>
      <ReportEntry
        /* The `<ol>` carries the ordering for assistive tech (and is given the
           right `start`, since a theme group restarts the element but not the
           ranking), so the visible number is presentation. */
        rank={`${item.marker}.`}
        title={title}
        insight={insight ? renderInline(insight, `${keyBase}-i`) : null}
        note={note ? renderInline(note, `${keyBase}-n`) : null}
        /* Renders nothing when the item carries no verdict, which is the honest
           answer rather than a fabricated one. */
        rail={<VerdictBadge verdict={item.verdict} />}
        flags={item.isNew ? <ReportFlag tone="new">New</ReportFlag> : null}
        link={
          url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-1 text-[12px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            >
              Open {noun}
              <ArrowRightIcon
                size={12}
                aria-hidden="true"
                className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
              />
            </a>
          ) : null
        }
        deadlines={
          item.deadline ? [{ date: formatIsoDate(item.deadline) }] : []
        }
      />
    </li>
  );
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
          const Tag = block.level === 2 ? "h2" : block.level === 3 ? "h3" : "h4";
          return (
            <Tag key={key} className={cn(HEADING_CLASS[block.level], "first:mt-0")}>
              {renderInline(block.text, key)}
            </Tag>
          );
        }
        if (block.kind === "ordered") {
          return (
            <ol
              key={key}
              start={Number(block.items[0].marker) || 1}
              className="mt-1 mb-2 list-none first:mt-0"
            >
              {block.items.map((item, i) => (
                <OrderedEntry
                  key={`${key}-oi${i}`}
                  item={item}
                  keyBase={`${key}-oi${i}`}
                  noun={block.noun}
                />
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
