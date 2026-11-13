import { describe, expect, it } from "vitest";

import { CAPABILITY, can, holding, type Capability } from "./capabilities";
import { navGroupsFor } from "./nav";
import type { MyDepartment, MyLab } from "./types";

/** The admin preset, as `/api/auth/me/` sends it for an admin or a lead PI. */
const MANAGER: Capability[] = Object.values(CAPABILITY).filter(
  (c) => c !== CAPABILITY.TRANSFER,
);

function lab(overrides: Partial<MyLab>): MyLab {
  return {
    slug: "soil",
    name: "Soil Lab",
    role: "member",
    is_lead: false,
    department: null,
    has_logo: false,
    logo_version: null,
    capabilities: [CAPABILITY.PEOPLE_VIEW],
    grantable_roles: ["viewer"],
    ...overrides,
  };
}

function dept(overrides: Partial<MyDepartment>): MyDepartment {
  return {
    id: "d1",
    name: "Earth Sciences",
    institution: "",
    role: "member",
    is_owner: false,
    can_manage: false,
    capabilities: [CAPABILITY.PEOPLE_VIEW],
    grantable_roles: ["viewer"],
    ...overrides,
  };
}

function keys(groups: ReturnType<typeof navGroupsFor>): string[] {
  return groups.flatMap((g) => g.items.map((i) => i.key));
}

describe("can() reads the server's list, never the role", () => {
  it("holds what the list names", () => {
    const pi = lab({ is_lead: true, capabilities: MANAGER });
    expect(can(pi, CAPABILITY.SERVERS_MANAGE)).toBe(true);
    expect(can(pi, CAPABILITY.TRANSFER)).toBe(false);
  });

  it("an owner role with no capabilities can do nothing", () => {
    expect(can(lab({ role: "owner", capabilities: [] }), CAPABILITY.PROFILE_EDIT)).toBe(
      false,
    );
  });

  it("no org, no right", () => {
    expect(can(null, CAPABILITY.PEOPLE_VIEW)).toBe(false);
    expect(can(undefined, CAPABILITY.PEOPLE_VIEW)).toBe(false);
  });

  it("filters a list of orgs", () => {
    const labs = [lab({ slug: "a" }), lab({ slug: "b", capabilities: MANAGER })];
    expect(labs.filter(holding(CAPABILITY.BILLING_MANAGE)).map((l) => l.slug)).toEqual([
      "b",
    ]);
  });
});

describe("the workspace navigation holds no settings pages", () => {
  const base = { isAdmin: false, hasFeature: () => true, currentLab: null, currentDepartment: null };

  it("every scope gets one Settings entry and none of the old settings entries", () => {
    const pi = lab({ is_lead: true, capabilities: MANAGER });
    for (const ctx of [
      { ...base, scope: { kind: "personal" } },
      { ...base, scope: { kind: "lab", slug: pi.slug }, currentLab: pi },
      {
        ...base,
        scope: { kind: "department", id: "d1" },
        currentDepartment: dept({ role: "admin", capabilities: MANAGER }),
      },
    ]) {
      const k = keys(navGroupsFor(ctx as Parameters<typeof navGroupsFor>[0]));
      expect(k.filter((key) => key === "settings")).toHaveLength(1);
      expect(k).not.toContain("profile");
      expect(k).not.toContain("account");
      expect(k).not.toContain("mylo");
    }
  });

  it("a department's Members replaces its separate Labs entry", () => {
    const k = keys(
      navGroupsFor({
        ...base,
        scope: { kind: "department", id: "d1" },
        currentDepartment: dept({}),
      } as Parameters<typeof navGroupsFor>[0]),
    );
    expect(k).toContain("members");
    expect(k).not.toContain("labs");
  });

  it("a department has the four feeds beside Opportunities", () => {
    const groups = navGroupsFor({
      ...base,
      hasFeature: () => false,
      scope: { kind: "department", id: "d1" },
      currentDepartment: dept({}),
    } as Parameters<typeof navGroupsFor>[0]);
    const research = groups.find((g) => g.label === "Research");
    expect(research?.items.map((item) => item.key)).toEqual([
      "papers",
      "opportunities",
      "fellowships",
      "conferences",
      "projects",
    ]);
    // The department-level calls stay their own page in the Workspace group.
    expect(keys(groups)).toContain("deptOpportunities");
  });

  it("Settings sits in its own group at the foot", () => {
    const groups = navGroupsFor({
      ...base,
      scope: { kind: "personal" },
    } as Parameters<typeof navGroupsFor>[0]);
    expect(groups[groups.length - 1].label).toBe("Settings");
  });
});
