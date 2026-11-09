import { describe, expect, it } from "vitest";

import { parseAnswer, prepareMath } from "./markdown";

const types = (text: string) => parseAnswer(text).children.map((n) => n.type);

describe("parseAnswer", () => {
  it("reads a table, a code block, a heading and a list", () => {
    const text = [
      "## Options",
      "",
      "| Call | Due |",
      "| :-- | --: |",
      "| A | May |",
      "",
      "```python",
      "x = 1",
      "```",
      "",
      "- one",
      "- two",
    ].join("\n");
    expect(types(text)).toEqual(["heading", "table", "code", "list"]);
  });

  it("reads displayed and inline math in every spelling", () => {
    expect(types("\\[\nE = mc^2\n\\]")).toEqual(["math"]);
    expect(types("$$E = mc^2$$")).toEqual(["math"]);
    for (const text of ["Here \\(x^2\\) is.", "Here $x^2$ is.", "Here $$x^2$$ is."]) {
      const para = parseAnswer(text).children[0];
      expect(para.type).toBe("paragraph");
      expect("children" in para && para.children.map((c) => c.type)).toContain("inlineMath");
    }
  });

  it("keeps HTML as text nodes, never as elements", () => {
    const tree = parseAnswer("<script>alert(1)</script>");
    expect(tree.children[0].type).toBe("html");
  });
});

describe("prepareMath", () => {
  it("leaves money alone", () => {
    for (const text of [
      "Awards run $50,000 to $100,000 a year.",
      "It costs $5 or $10.",
      "Between $5-$10 each.",
      "Up to $2M (was $1M).",
    ]) {
      expect(prepareMath(text)).toBe(text);
    }
  });

  it("leaves code alone", () => {
    const text = "Use `$x$` here.\n\n```\n\\(a\\) $b$\n```";
    expect(prepareMath(text)).toBe(text);
  });

  it("keeps a displayed equation inside its list item", () => {
    expect(prepareMath("- item\n\n  \\[ a = b \\]")).toContain("\n  $$\n  a = b\n  $$\n");
  });
});
