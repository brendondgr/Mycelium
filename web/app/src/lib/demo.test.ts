import { describe, expect, it } from "vitest";

import { canonicalPath, isDemoPath, toDemoPath } from "./demo";

describe("demo paths", () => {
  it("maps workspace links into the demo and back", () => {
    expect(toDemoPath("/app/grants?ws=coastal-ocean-lab")).toBe("/demo/grants?ws=coastal-ocean-lab");
    expect(toDemoPath("/app")).toBe("/demo");
    expect(toDemoPath("/app#x")).toBe("/demo#x");
    expect(canonicalPath("/demo/projects/abc")).toBe("/app/projects/abc");
    expect(canonicalPath("/app/overview")).toBe("/app/overview");
  });

  it("leaves everything else alone", () => {
    expect(toDemoPath("/signup")).toBe("/signup");
    expect(toDemoPath("/apple")).toBe("/apple");
    expect(toDemoPath("https://example.org/app/x")).toBe("https://example.org/app/x");
    expect(toDemoPath("/demo/grants")).toBe("/demo/grants");
    expect(isDemoPath("/demonstration")).toBe(false);
    expect(canonicalPath("/demonstration")).toBe("/demonstration");
  });
});
