import { describe, expect, it } from "vitest";

import { isSafeLink } from "./safe-link";

describe("isSafeLink", () => {
  it("allows http(s) and mailto", () => {
    expect(isSafeLink("https://example.org/a")).toBe(true);
    expect(isSafeLink("http://example.org")).toBe(true);
    expect(isSafeLink("mailto:a@example.org")).toBe(true);
  });

  it("refuses script and data schemes, however they are cased or padded", () => {
    expect(isSafeLink("javascript:alert(1)")).toBe(false);
    expect(isSafeLink(" JavaScript:alert(1)")).toBe(false);
    expect(isSafeLink("data:text/html,<script>")).toBe(false);
    expect(isSafeLink("vbscript:x")).toBe(false);
    expect(isSafeLink("//evil.example")).toBe(false);
    expect(isSafeLink("")).toBe(false);
    expect(isSafeLink(undefined)).toBe(false);
  });
});
