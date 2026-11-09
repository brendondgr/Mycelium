/**
 * Mylo's answer text as a Markdown tree (CommonMark + GFM tables, task lists,
 * strikethrough, autolinks) with math. Parsing only: the panel draws the tree
 * as React nodes, so nothing the model writes is ever read as HTML.
 *
 * Math is written three ways by models: `\( … \)` and `\[ … \]`, `$$ … $$`,
 * and `$ … $`. The parser itself only takes double dollars, because a single
 * dollar is far more often money in a grant ("$50,000 to $100,000");
 * `prepareMath` rewrites the other forms to double dollars and leaves money
 * alone.
 */

import type { Root } from "mdast";
import { fromMarkdown } from "mdast-util-from-markdown";
import { gfmFromMarkdown } from "mdast-util-gfm";
import { mathFromMarkdown } from "mdast-util-math";
import { gfm } from "micromark-extension-gfm";
import { math } from "micromark-extension-math";

export function parseAnswer(text: string): Root {
  return fromMarkdown(prepareMath(text.trim()), {
    extensions: [gfm({ singleTilde: false }), math({ singleDollarTextMath: false })],
    mdastExtensions: [gfmFromMarkdown(), mathFromMarkdown()],
  });
}

const FENCE = /^\s*(```|~~~)/;
const MATHISH = /[\\^_={}]/;

/** Rewrite `\(…\)`, `\[…\]`, one-line `$$…$$` and `$…$` to what the parser takes. */
export function prepareMath(text: string): string {
  // Code fences pass through untouched.
  const out: string[] = [];
  let chunk: string[] = [];
  let fence: string | null = null;
  const flush = () => {
    if (chunk.length) out.push(outsideFences(chunk.join("\n")));
    chunk = [];
  };
  for (const line of text.split("\n")) {
    const m = FENCE.exec(line);
    if (fence) {
      out.push(line);
      if (m && m[1] === fence) fence = null;
    } else if (m) {
      flush();
      fence = m[1];
      out.push(line);
    } else {
      chunk.push(line);
    }
  }
  flush();
  return out.join("\n");
}

function outsideFences(text: string): string {
  // Inline code spans pass through untouched.
  return text
    .split(/(`+[^`\n]*`+)/)
    .map((part, i) => (i % 2 ? part : rewrite(part)))
    .join("");
}

function display(indent: string, body: string): string {
  const lines = body
    .trim()
    .split("\n")
    .map((l) => indent + l.trim())
    .filter((l) => l.trim());
  return `\n${indent}$$\n${lines.join("\n")}\n${indent}$$\n`;
}

const oneLine = (body: string) => body.trim().replace(/\s*\n\s*/g, " ");

function rewrite(text: string): string {
  return (
    text
      // \[ … \] alone on its lines is a displayed equation
      .replace(/^([ \t]*)\\\[([\s\S]+?)\\\][ \t]*$/gm, (_, indent: string, body: string) =>
        display(indent, body),
      )
      // $$ … $$ on one line of its own, the same
      .replace(/^([ \t]*)\$\$([^$\n]+)\$\$[ \t]*$/gm, (_, indent: string, body: string) =>
        display(indent, body),
      )
      // \[ … \] in the middle of a line, and \( … \)
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, body: string) => `$$${oneLine(body)}$$`)
      .replace(/\\\(([\s\S]+?)\\\)/g, (_, body: string) => `$$${oneLine(body)}$$`)
      // $ … $, unless it reads as money
      .replace(
        /(?<![\\$\w])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?![\w$])/g,
        (all: string, body: string) =>
          /^\d/.test(body) && !MATHISH.test(body) ? all : `$$${body}$$`,
      )
  );
}
