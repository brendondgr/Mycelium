import { describe, expect, it } from "vitest";

import {
  canManageLab,
  grantableDeptRoles,
  grantableLabRoles,
  outranksDeptMember,
  outranksLabMember,
} from "./nav";

describe("a lead PI holds every admin right", () => {
  const pi = { role: "member" as const, is_lead: true };

  it("manages the lab", () => {
    expect(canManageLab(pi)).toBe(true);
  });

  it("grants what an admin grants, and never admin", () => {
    expect(grantableLabRoles(pi)).toEqual(["member", "viewer"]);
  });

  it("acts on members but not on admins or other leads", () => {
    expect(outranksLabMember(pi, { role: "member" })).toBe(true);
    expect(outranksLabMember(pi, { role: "admin" })).toBe(false);
    expect(outranksLabMember(pi, { role: "member", is_lead: true })).toBe(false);
  });

  it("is not outranked by an admin", () => {
    expect(outranksLabMember({ role: "admin", is_lead: false }, { role: "member", is_lead: true })).toBe(
      false,
    );
  });
});

describe("department authority runs downward", () => {
  const head = { is_owner: true, role: "owner" };
  const admin = { is_owner: false, role: "admin" };

  it("only the head grants admin", () => {
    expect(grantableDeptRoles(head)).toEqual(["admin", "member", "viewer"]);
    expect(grantableDeptRoles(admin)).toEqual(["member", "viewer"]);
  });

  it("an admin cannot act on another admin or the head", () => {
    expect(outranksDeptMember(admin, { role: "admin" })).toBe(false);
    expect(outranksDeptMember(admin, { role: "owner", is_head: true })).toBe(false);
    expect(outranksDeptMember(admin, { role: "member" })).toBe(true);
  });

  it("a stray owner row is not a second head", () => {
    const stray = { is_owner: false, role: "owner" };
    expect(grantableDeptRoles(stray)).toEqual(["member", "viewer"]);
    expect(outranksDeptMember(head, { role: "owner" })).toBe(true);
  });
});
