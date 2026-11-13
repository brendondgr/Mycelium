/**
 * What the caller may do in a lab or a department — read, never derived.
 *
 * The server decides (`apps/accounts/capabilities.py`) and sends each org's
 * capabilities on `/api/auth/me/`, on every `MyLab` row and on every
 * `MyDepartment` row. The app asks `can(org, capability)` of that list and
 * never re-derives a right from a role, so a drawn control and the API that
 * backs it cannot disagree. The roles a caller may grant arrive the same way
 * (`grantable_roles`), and each roster row says whether the caller may act on
 * it (`can_act`).
 */

export const CAPABILITY = {
  PROFILE_EDIT: "org.profile.edit",
  PEOPLE_VIEW: "org.people.view",
  PEOPLE_MANAGE: "org.people.manage",
  INVITES_ISSUE: "org.invites.issue",
  PROJECTS_POLICY: "org.projects.policy",
  PROJECTS_OVERSEE: "org.projects.oversee",
  SERVERS_MANAGE: "org.servers.manage",
  ANNOUNCEMENTS_MANAGE: "org.announcements.manage",
  MYLO_POLICY: "org.mylo.policy",
  BILLING_MANAGE: "org.billing.manage",
  TRANSFER: "org.transfer",
} as const;

export type Capability = (typeof CAPABILITY)[keyof typeof CAPABILITY];

/** Anything that carries the caller's capabilities: a lab or department row. */
export type HasCapabilities = { capabilities?: readonly Capability[] | null };

/** Whether the caller holds `capability` in `org`. No org, no right. */
export function can(
  org: HasCapabilities | null | undefined,
  capability: Capability,
): boolean {
  return Boolean(org?.capabilities?.includes(capability));
}

/** A filter for `labs.filter(holding(CAPABILITY.X))`. */
export function holding(capability: Capability) {
  return (org: HasCapabilities) => can(org, capability);
}
