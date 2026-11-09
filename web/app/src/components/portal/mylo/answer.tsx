"use client";

import * as React from "react";
import type { RootContent } from "mdast";

import { parseAnswer } from "@/lib/portal/agent/markdown";
import { splitCitations } from "@/lib/portal/agent/turns";
import type { AgentReference } from "@/lib/portal/agent/types";

import { splitItemTitle } from "./open-ref";

const MathView = React.lazy(() => import("./math"));

type Ctx = { references: AgentReference[]; onCite: (ref: AgentReference) => void };

/**
 * Mylo's text as Markdown: headings, lists, tables, code, quotes, links,
 * math, and `#n` citations as pills. Every node is built here as a React
 * element — HTML the model writes is shown as the text it is, and a link
 * opens only an http(s) or mail address, in a new tab.
 */
export function AnswerText({
  text,
  references,
  onCite,
}: {
  text: string;
  references: AgentReference[];
  onCite: (ref: AgentReference) => void;
}) {
  const tree = React.useMemo(() => parseAnswer(text), [text]);
  const ctx = React.useMemo(() => ({ references, onCite }), [references, onCite]);
  return <div className="ws-mylo-answer">{renderAll(tree.children, ctx)}</div>;
}

function renderAll(nodes: RootContent[], ctx: Ctx): React.ReactNode {
  return nodes.map((node, i) => <React.Fragment key={i}>{render(node, ctx)}</React.Fragment>);
}

const SAFE_LINK = /^(https?:\/\/|mailto:)/i;

function render(node: RootContent, ctx: Ctx): React.ReactNode {
  switch (node.type) {
    case "text":
      return <Cited text={node.value} ctx={ctx} />;
    case "paragraph":
      return <p>{renderAll(node.children, ctx)}</p>;
    case "heading": {
      const Tag = node.depth <= 2 ? "h3" : "h4";
      return <Tag>{renderAll(node.children, ctx)}</Tag>;
    }
    case "strong":
      return <strong>{renderAll(node.children, ctx)}</strong>;
    case "emphasis":
      return <em>{renderAll(node.children, ctx)}</em>;
    case "delete":
      return <del>{renderAll(node.children, ctx)}</del>;
    case "break":
      return <br />;
    case "thematicBreak":
      return <hr />;
    case "inlineCode":
      return <code className="ws-mylo-code-inline">{node.value}</code>;
    case "code":
      return (
        <pre className="ws-mylo-code" tabIndex={0}>
          <code>{node.value}</code>
        </pre>
      );
    case "blockquote":
      return <blockquote>{renderAll(node.children, ctx)}</blockquote>;
    case "list": {
      const items = node.children.map((item, i) => (
        <li key={i} data-task={typeof item.checked === "boolean" || undefined}>
          {typeof item.checked === "boolean" ? (
            <input type="checkbox" checked={item.checked} readOnly disabled aria-label={item.checked ? "Done" : "Not done"} />
          ) : null}
          {item.children.map((child, j) =>
            // a tight list item is its text, not a paragraph of its own
            child.type === "paragraph" && !item.spread ? (
              <React.Fragment key={j}>{renderAll(child.children, ctx)}</React.Fragment>
            ) : (
              <React.Fragment key={j}>{render(child, ctx)}</React.Fragment>
            ),
          )}
        </li>
      ));
      return node.ordered ? <ol start={node.start ?? 1}>{items}</ol> : <ul>{items}</ul>;
    }
    case "table": {
      const [head, ...rows] = node.children;
      const align = (i: number) => node.align?.[i] ?? undefined;
      return (
        <div className="ws-mylo-table" tabIndex={0}>
          <table>
            {head ? (
              <thead>
                <tr>
                  {head.children.map((cell, i) => (
                    <th key={i} scope="col" style={{ textAlign: align(i) }}>
                      {renderAll(cell.children, ctx)}
                    </th>
                  ))}
                </tr>
              </thead>
            ) : null}
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>
                  {row.children.map((cell, i) => (
                    <td key={i} style={{ textAlign: align(i) }}>
                      {renderAll(cell.children, ctx)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    case "link": {
      const label = renderAll(node.children, ctx);
      return SAFE_LINK.test(node.url) ? (
        <a href={node.url} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      ) : (
        label
      );
    }
    case "image":
      // never fetched: a remote picture would tell its host who is reading
      return SAFE_LINK.test(node.url) ? (
        <a href={node.url} target="_blank" rel="noopener noreferrer">
          {node.alt || node.url}
        </a>
      ) : (
        node.alt || null
      );
    case "math":
      return <Formula tex={node.value} display />;
    case "inlineMath":
      return <Formula tex={node.value} display={false} />;
    case "html":
      // shown as written, except the line break models put in table cells
      return /^<br\s*\/?>$/i.test(node.value.trim()) ? <br /> : node.value;
    case "definition":
    case "footnoteDefinition":
    case "yaml":
      return null;
    default:
      if ("children" in node) return renderAll(node.children as RootContent[], ctx);
      if ("value" in node && typeof node.value === "string") return node.value;
      return null;
  }
}

function Formula({ tex, display }: { tex: string; display: boolean }) {
  const source = <code className="ws-mylo-code-inline">{tex}</code>;
  return (
    <React.Suspense fallback={source}>
      <MathView tex={tex} display={display} />
    </React.Suspense>
  );
}

function Cited({ text, ctx }: { text: string; ctx: Ctx }) {
  return (
    <>
      {splitCitations(text).map((part, i) => {
        if (!("cite" in part)) return <React.Fragment key={i}>{part.text}</React.Fragment>;
        const ref = ctx.references.find((r) => r.n === part.cite);
        if (!ref) return <React.Fragment key={i}>{`#${part.cite}`}</React.Fragment>;
        const title = splitItemTitle(ref.title).title;
        return (
          <button
            key={i}
            type="button"
            className="ws-mylo-cite"
            title={title}
            aria-label={`Source ${ref.n}: ${title}`}
            onClick={() => ctx.onCite(ref)}
          >
            {ref.n}
          </button>
        );
      })}
    </>
  );
}
