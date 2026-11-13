import { describe, expect, it } from "vitest";

import { CAPABILITY, type Capability } from "./capabilities";
import {
  legacySettingsPath,
  parseSettingsPath,
  settingsHomeFor,
  settingsPagesFor,
  settingsPath,
  type SettingsContext,
} from "./settings";

/** The presets `/api/auth/me/` sends (apps/accounts/capabilities.py). */
const ALL = Object.values(CAPABILITY) as Capability[];
const MANAGER = ALL.filter((c) => c !== CAPABILITY.TRANSFER);
const READER: Capability[] = [CAPABILITY.PEOPLE_VIEW];
const ROLES: Record<string, Capability[]> = {
  owner: ALL,
  admin: MANAGER,
  lead: MANAGER,
  member: READER,
  viewer: READER,
};

const LAB: SettingsContext = { kind: "lab", slug: "soil" };
const DEPT: SettingsContext = { kind: "department", id: "4ae6f674-189f-424b-ae00-843d102a79f8" };
const ON = { billingOn: true };

function pages(context: SettingsContext, caps: Capability[], options = ON) {
  return settingsPagesFor(context, { capabilities: caps }, options);
}

function keys(context: SettingsContext, caps: Capability[], options = ON) {
  return pages(context, caps, options).map((p) => p.key);
}

describe("each role sees exactly the pages its capabilities allow", () => {
  it("a lab, role by role", () => {
    const all = ["general", "people", "projects", "servers", "announcements", "plan", "membership"];
    expect(keys(LAB, ROLES.owner)).toEqual([...all, "transfer"]);
    expect(keys(LAB, ROLES.admin)).toEqual(all);
    expect(keys(LAB, ROLES.lead)).toEqual(all);
    for (const role of ["member", "viewer"]) {
      expect(keys(LAB, ROLES[role])).toEqual(["general", "people", "plan", "membership"]);
    }
  });

  it("a department, role by role", () => {
    const all = [
      "general",
      "labs",
      "people",
      "projects",
      "servers",
      "announcements",
      "plan",
      "membership",
    ];
    expect(keys(DEPT, ROLES.owner)).toEqual([...all, "transfer"]);
    expect(keys(DEPT, ROLES.admin)).toEqual(all);
    for (const role of ["member", "viewer"]) {
      expect(keys(DEPT, ROLES[role])).toEqual(["general", "labs", "people", "plan", "membership"]);
    }
  });

  it("a stranger gets nothing", () => {
    expect(keys(LAB, [])).toEqual([]);
    expect(settingsPagesFor(DEPT, null, ON)).toEqual([]);
  });

  it("a member who manages nothing can still find their role and leave", () => {
    expect(keys(LAB, ROLES.member)).toContain("membership");
  });

  it("the plan is not listed when the instance runs without billing", () => {
    expect(keys(LAB, ROLES.owner, { billingOn: false })).not.toContain("plan");
  });

  it("You lists every personal page, Appearance included", () => {
    expect(keys({ kind: "you" }, [])).toEqual([
      "account",
      "profile",
      "mylo",
      "collaboration",
      "delivery",
      "appearance",
      "subscription",
    ]);
  });
});

describe("a page you may read but not change says why", () => {
  it("a member's lab General is read-only with the reason", () => {
    const general = pages(LAB, ROLES.member).find((p) => p.key === "general")!;
    expect(general.readOnly).toBe(true);
    expect(general.reason).toMatch(/PI, owners and admins/);
  });

  it("an admin's is editable", () => {
    const general = pages(LAB, ROLES.admin).find((p) => p.key === "general")!;
    expect(general).toMatchObject({ readOnly: false, reason: null });
  });

  it("a department member reads the plan but cannot change it", () => {
    const plan = pages(DEPT, ROLES.member).find((p) => p.key === "plan")!;
    expect(plan.readOnly).toBe(true);
    expect(plan.reason).toMatch(/department head/);
  });

  it("the read-only state follows the capability, not the role", () => {
    // An admin preset minus billing: the plan turns read-only on its own.
    const caps = MANAGER.filter((c) => c !== CAPABILITY.BILLING_MANAGE);
    expect(pages(LAB, caps).find((p) => p.key === "plan")!.readOnly).toBe(true);
    expect(pages(LAB, caps).find((p) => p.key === "general")!.readOnly).toBe(false);
  });
});

describe("the context is in the path", () => {
  it("round-trips every context", () => {
    for (const context of [{ kind: "you" } as SettingsContext, LAB, DEPT]) {
      const parsed = parseSettingsPath(settingsPath(context, "membership"));
      expect(parsed).toEqual({ context, page: "membership" });
    }
  });

  it("a path naming only the context has no page; a bare path has no context", () => {
    expect(parseSettingsPath("/app/settings/lab/soil")).toEqual({ context: LAB, page: null });
    expect(parseSettingsPath("/app/settings")).toBeNull();
    expect(parseSettingsPath("/app/settings/lab")).toBeNull();
    expect(parseSettingsPath("/app/profile")).toBeNull();
  });

  it("entering Settings from a workspace opens that workspace's context", () => {
    expect(settingsHomeFor({ kind: "lab", slug: "soil" })).toBe("/app/settings/lab/soil/general");
    expect(settingsHomeFor({ kind: "department", id: "d1" })).toBe(
      "/app/settings/department/d1/general",
    );
    expect(settingsHomeFor({ kind: "personal" })).toBe("/app/settings/you/account");
  });
});

describe("the old settings routes redirect", () => {
  it("each lands on its page", () => {
    expect(legacySettingsPath("account")).toBe("/app/settings/you/account");
    expect(legacySettingsPath("profile")).toBe("/app/settings/you/profile");
    expect(legacySettingsPath("mylo")).toBe("/app/settings/you/mylo");
    expect(legacySettingsPath("billing")).toBe("/app/settings/you/subscription");
    expect(legacySettingsPath("department", { id: "d1" })).toBe(
      "/app/settings/department/d1/general",
    );
  });

  it("an old ?ws= picks the org once: a slug is a lab, a UUID a department", () => {
    expect(legacySettingsPath("profile", { ws: "soil" })).toBe("/app/settings/lab/soil/general");
    expect(legacySettingsPath("profile", { ws: DEPT.kind === "department" ? DEPT.id : "" })).toBe(
      `/app/settings/department/${(DEPT as { id: string }).id}/general`,
    );
    expect(legacySettingsPath("billing", { ws: "soil" })).toBe("/app/settings/lab/soil/plan");
    expect(legacySettingsPath("profile", { ws: "__personal__" })).toBe("/app/settings/you/profile");
  });

  it("a Discord or Slack return to the old Profile keeps its outcome on Delivery", () => {
    expect(legacySettingsPath("profile", { returned: { discord: "linked" } })).toBe(
      "/app/settings/you/delivery?discord=linked",
    );
    expect(legacySettingsPath("profile", { returned: { slack: "installed", discord: null } })).toBe(
      "/app/settings/you/delivery?slack=installed",
    );
  });
});
