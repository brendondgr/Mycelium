import { describe, expect, it } from "vitest";

import { authFallback } from "./auth-fallback";
import { POST as loginFallback } from "../app/login/fallback/route";
import { POST as resetFallback } from "../app/reset-password/fallback/route";

describe("auth form fallback", () => {
  it("answers a native submit with a 303 back to the form, carrying nothing", () => {
    const response = authFallback("/login");
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/login?nojs=1");
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });

  it("never echoes the submitted fields or the reset token", async () => {
    const login = loginFallback();
    expect(login.headers.get("Location")).toBe("/login?nojs=1");
    expect(await login.text()).toBe("");

    const reset = resetFallback();
    expect(reset.headers.get("Location")).toBe("/reset-password?nojs=1");
  });
});
