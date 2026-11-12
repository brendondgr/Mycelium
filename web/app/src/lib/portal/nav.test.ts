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

describe("navigation follows capabilities", () => {
  const base = { isAdmin: false, hasFeature: () => true, currentDepartment: null };

  it("a lead PI gets the lab settings entry an admin gets", () => {
    const pi = lab({ is_lead: true, capabilities: MANAGER });
    const groups = navGroupsFor({
      ...base,
      scope: { kind: "lab", slug: pi.slug },
      currentLab: pi,
    } as Parameters<typeof navGroupsFor>[0]);
    expect(keys(groups)).toContain("profile");
  });

  it("a plain lab member does not", () => {
    const member = lab({});
    const groups = navGroupsFor({
      ...base,
      scope: { kind: "lab", slug: member.slug },
      currentLab: member,
    } as Parameters<typeof navGroupsFor>[0]);
    expect(keys(groups)).not.toContain("profile");
  });

  it("a department admin gets department settings; a member does not", () => {
    const scope = { kind: "department", id: "d1" };
    const admin = navGroupsFor({
      ...base,
      scope,
      currentLab: null,
      currentDepartment: dept({ role: "admin", capabilities: MANAGER }),
    } as Parameters<typeof navGroupsFor>[0]);
    const member = navGroupsFor({
      ...base,
      scope,
      currentLab: null,
      currentDepartment: dept({}),
    } as Parameters<typeof navGroupsFor>[0]);
    expect(keys(admin)).toContain("profile");
    expect(keys(member)).not.toContain("profile");
  });
});
