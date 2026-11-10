"use client";

import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { noteDemoRefusal } from "@/lib/demo";
import { ensureCsrfCookie, readCsrfToken } from "@/lib/auth-client";
import { announcementQuery } from "@/lib/portal/client";
import type {
  AnnouncementSettings,
  AnnouncementTarget,
  AdminLabDetail,
  AdminLabUpdate,
  AdminUserDetail,
  AdminUserUpdate,
  BriefingCategory,
  CollectionBrief,
  CollectionDetail,
  DeptLabRow,
  DiscordCodeResponse,
  DiscordLabCodeResponse,
  DiscordStatus,
  IngestLinkResult,
  InvitationAction,
  LabMember,
  LabProfileData,
  MyDepartment,
  MyLab,
  OrgInvite,
  OrgInviteInput,
  OrgInviteBatchInput,
  OrgInviteBatchResult,
  OrgBilling,
  Project,
  ProjectCapErrorBody,
  ProjectConversation,
  ProjectFocusInput,
  ProjectInvitation,
  ProjectStateInput,
  ProjectStateProposal,
  ReflectionProposal,
  ProjectStatePayload,
  ProjectUpdateInput,
  Reminder,
  ReminderInput,
  ReminderUpdateInput,
  SavedDeadline,
  WatchData,
} from "@/lib/portal/types";

/**
 * CSRF-aware writes for the workspace dashboard. Each ensures the CSRF cookie,
 * sends the token as `X-CSRFToken`, and surfaces the first DRF field error as a
 * friendly message the UI can show. Mirrors the auth client's mutation pattern.
 */

function firstError(body: Record<string, unknown> | null): string | null {
  if (!body) {
    return null;
  }
  for (const value of Object.values(body)) {
    if (typeof value === "string" && value) {
      return value;
    }
    if (Array.isArray(value)) {
      const first = value.find((v) => typeof v === "string" && v);
      if (typeof first === "string") {
        return first;
      }
    }
  }
  return null;
}

/**
 * Thrown when a project create or unarchive 403s because the owning scope
 * (personal/lab/department) is at its plan's project cap. Carries the
 * structured fields the backend sends alongside `detail`, so a caller can show
 * the exact limit ("archive one of your 5 projects or upgrade") instead of a
 * generic error string.
 */
export class ProjectCapReachedError extends Error {
  readonly code = "project_cap_reached" as const;
  readonly scope: ProjectCapErrorBody["scope"];
  readonly cap: number;
  readonly active: number;

  constructor(body: ProjectCapErrorBody) {
    super(body.detail);
    this.name = "ProjectCapReachedError";
    this.scope = body.scope;
    this.cap = body.cap;
    this.active = body.active;
  }
}

function isProjectCapError(body: unknown): body is ProjectCapErrorBody {
  return (
    !!body &&
    typeof body === "object" &&
    (body as Record<string, unknown>).code === "project_cap_reached"
  );
}

async function sendJson<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  url: string,
  body: unknown,
  fallbackMessage: string,
): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let parsed: (T & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as T & Record<string, unknown>;
  } catch {
    parsed = null;
  }

  if (!response.ok) {
    if (isProjectCapError(parsed)) {
      throw new ProjectCapReachedError(parsed);
    }
    noteDemoRefusal(parsed);
    throw new Error(firstError(parsed) ?? fallbackMessage);
  }
  return parsed as T;
}

/**
 * A multipart POST — the same auth and error handling as `sendJson`, minus the
 * `Content-Type` header, which the browser must set itself so the boundary is
 * right.
 */
async function sendForm<T>(
  url: string,
  body: FormData,
  fallbackMessage: string,
): Promise<T> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const response = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}) },
    body,
  });

  let parsed: (T & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as T & Record<string, unknown>;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    noteDemoRefusal(parsed);
    throw new Error(firstError(parsed) ?? fallbackMessage);
  }
  return parsed as T;
}

/** Create a lab; the caller becomes its PI. */
export function createLab(name: string): Promise<MyLab> {
  return sendJson<MyLab>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs"),
    { name },
    "Could not create the lab. Try again.",
  );
}

/** Invite a person to a lab by email or username. */
export function inviteToLab(
  slug: string,
  identifier: string,
  role = "member",
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "invitations"),
    { identifier, role },
    "Could not send the invitation.",
  );
}

/** Withdraw a pending invitation a manager sent. */
export function cancelInvitation(slug: string, id: string): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(
      getPublicApiBase(), "auth", "labs", slug, "invitations", id, "cancel",
    ),
    undefined,
    "Could not cancel the invitation.",
  );
}

/** Add an existing user to a lab directly (managers). */
export function addLabMember(
  slug: string,
  username: string,
  role = "member",
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "members"),
    { username, role },
    "Could not add that member.",
  );
}

/** Change a lab member's role (managers). */
export function setLabMemberRole(
  slug: string,
  username: string,
  role: string,
): Promise<unknown> {
  return sendJson(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "members", username),
    { role },
    "Could not change the member's role.",
  );
}

/** Remove a lab member (their seat defers to period end). */
export function removeLabMember(slug: string, username: string): Promise<unknown> {
  return sendJson(
    "DELETE",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "members", username),
    undefined,
    "Could not remove that member.",
  );
}

/** Activate a lab's (inactive) plan — opens the billing period and seats members. */
export function activateLabBilling(slug: string): Promise<OrgBilling> {
  return sendJson<OrgBilling>(
    "POST",
    buildApiUrl(getPublicApiBase(), "labs", slug, "billing", "activate"),
    undefined,
    "Could not activate the plan.",
  );
}

/** Add a direct department member (managers). */
export function addDeptMember(
  id: string,
  username: string,
  role = "member",
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "members"),
    { username, role },
    "Could not add that member.",
  );
}

/** Remove a direct department member (their seat defers to period end). */
export function removeDeptMember(id: string, username: string): Promise<unknown> {
  return sendJson(
    "DELETE",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "members", username),
    undefined,
    "Could not remove that member.",
  );
}

/** Attach an existing (unowned) lab to a department by slug (managers). */
export function attachLabToDept(id: string, slug: string): Promise<DeptLabRow[]> {
  return sendJson<DeptLabRow[]>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "labs"),
    { slug },
    "Could not attach that lab.",
  );
}

/** Create a new lab under a department (managers). */
export function createLabInDept(id: string, name: string): Promise<DeptLabRow[]> {
  return sendJson<DeptLabRow[]>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "labs"),
    { name },
    "Could not create the lab.",
  );
}

/** Detach a lab from a department (managers). */
export function detachLabFromDept(id: string, slug: string): Promise<unknown> {
  return sendJson(
    "DELETE",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "labs", slug),
    undefined,
    "Could not detach that lab.",
  );
}

/** Include or exclude a lab in the department's plan (managers). Returns the
 * refreshed labs list. Including seats the lab's members department-paid;
 * excluding stops the department paying for them (deferred to period end). */
export function setLabPlanInclusion(
  id: string,
  slug: string,
  included: boolean,
): Promise<DeptLabRow[]> {
  return sendJson<DeptLabRow[]>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "labs", slug),
    { included_in_plan: included },
    "Could not update the lab's plan inclusion.",
  );
}

/** Activate a department's (inactive) plan — seats the effective membership. */
export function activateDeptBilling(id: string): Promise<OrgBilling> {
  return sendJson<OrgBilling>(
    "POST",
    buildApiUrl(getPublicApiBase(), "departments", id, "billing", "activate"),
    undefined,
    "Could not activate the plan.",
  );
}

/** Accept, reject, or ignore one of the caller's pending invitations. */
export function respondToInvitation(
  id: string,
  action: InvitationAction,
): Promise<{ id: string; status: string }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "invitations", id, "respond"),
    { action },
    "Could not respond to the invitation.",
  );
}

/**
 * Create a project scoped to a lab (slug), a department (id), or personally
 * (neither) — mutually exclusive, matching the backend. An optional `focus`
 * (areas/keywords/statement/clusters/watch_topics) seeds Mylo's first pass at
 * this project's recommendations. Returns the full created `Project`; on a
 * plan-cap violation the backend 403s with `{code: "project_cap_reached", ...}`,
 * surfaced here as a `ProjectCapReachedError`.
 */
export function createProject(input: {
  name: string;
  labSlug?: string;
  departmentId?: string;
  focus?: ProjectFocusInput;
}): Promise<Project> {
  const body: Record<string, unknown> = { name: input.name };
  if (input.labSlug) body.lab = input.labSlug;
  if (input.departmentId) body.department = input.departmentId;
  if (input.focus) body.focus = input.focus;
  return sendJson<Project>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects"),
    body,
    "Could not create the project.",
  );
}

/** Archive a project — keeps its stored recommendations but stops new search
 * work and frees a slot against the owner's plan cap. Never deletes it. */
export function archiveProject(id: string): Promise<Project> {
  return sendJson<Project>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "archive"),
    undefined,
    "Could not archive the project.",
  );
}

/**
 * Restore an archived project. Re-checks the owning scope's plan cap; if
 * restoring would exceed it, the backend 403s with `{code:
 * "project_cap_reached", ...}`, surfaced here as a `ProjectCapReachedError`.
 */
export function unarchiveProject(id: string): Promise<Project> {
  return sendJson<Project>(
    "DELETE",
    buildApiUrl(getPublicApiBase(), "projects", id, "archive"),
    undefined,
    "Could not unarchive the project.",
  );
}

/** Update which of papers/grants/fellowships/conferences Mylo tracks for a
 * project (owner or lab manager only). */
export function updateProjectCategories(
  id: string,
  categories: BriefingCategory[],
): Promise<Project> {
  return sendJson<Project>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "projects", id),
    { watch_categories: categories },
    "Could not update this project's watch settings.",
  );
}

/**
 * Update a project's fundamentals — name, description, status, progress, watch
 * categories, focus — in one PATCH (its owner or a lab owner/admin/PI only).
 * Only the keys present are touched; an empty string or `null` clears a display
 * field rather than storing a blank one.
 */
export function updateProject(
  id: string,
  patch: ProjectUpdateInput,
): Promise<Project> {
  return sendJson<Project>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "projects", id),
    patch,
    "Could not save this project.",
  );
}

/**
 * Point a channel Mylo has heard at this project, or stop. A hint only raises
 * the project's score in that channel; it never decides on its own.
 */
export function setChannelHint(
  projectId: string,
  placeId: string,
  on: boolean,
): Promise<ProjectConversation> {
  return sendJson<ProjectConversation>(
    "POST",
    buildApiUrl(getPublicApiBase(), "ambient", "projects", projectId, "channel-hints"),
    { place_id: placeId, on },
    "Could not update that channel.",
  );
}

/**
 * "This was about a different project." `null` means it was not about a
 * project at all. The answer outranks Mylo's, and is kept as a labelled example.
 */
export function correctAttribution(
  refId: number,
  projectId: string | null,
): Promise<{ id: number; project: string | null; observations_updated: number }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "ambient", "attributions", String(refId), "correct"),
    { project: projectId },
    "Could not save that correction.",
  );
}

/**
 * Edit a project's state (its editors only).
 *
 * A **merge**, not a replace: send only the half or the field that changed. The
 * wizard, the document extractor and the state panel each write the part they
 * know about, and a PATCH carrying only `fast` leaves the research identity
 * alone.
 */
export function updateProjectState(
  id: string,
  patch: ProjectStateInput,
): Promise<ProjectStatePayload> {
  return sendJson<ProjectStatePayload>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "projects", id, "state"),
    patch,
    "Could not save this project's state.",
  );
}

/**
 * Read a project's state out of a document. **Proposes; saves nothing.**
 *
 * The reply's fields are all marked `inferred`; applying them is a separate
 * `updateProjectState` call the reader triggers. Sent as multipart because the
 * usual case is a PDF, and the backend reuses the résumé path's own size limit
 * and "no readable text" error rather than answering those questions twice.
 */
export async function extractProjectState(
  id: string,
  file: File,
): Promise<ProjectStateProposal> {
  const body = new FormData();
  body.append("file", file);
  return sendForm<ProjectStateProposal>(
    buildApiUrl(getPublicApiBase(), "projects", id, "state", "extract"),
    body,
    "Could not read that document.",
  );
}

/**
 * Accept or reject one of Mylo's proposals.
 *
 * Accepting is the only thing that applies it: nothing else in the product
 * writes a proposal into a project's state, which is what keeps "a stated field
 * changes only by user action" true rather than merely intended.
 */
export function decideReflection(
  id: string,
  action: "accept" | "reject",
): Promise<ReflectionProposal> {
  return sendJson<ReflectionProposal>(
    "POST",
    buildApiUrl(getPublicApiBase(), "reflections", id, "action"),
    { action },
    "Could not record that decision.",
  );
}

/** "Still true" — a confirmation, which is a different act from an edit. */
export function confirmProjectState(id: string): Promise<ProjectStatePayload> {
  return sendJson<ProjectStatePayload>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "state", "confirm"),
    {},
    "Could not confirm this project's state.",
  );
}

/** Update a project's research focus (owner or lab manager only) — re-seeds
 * Mylo's recommendations for it in the background. */
export function updateProjectFocus(
  id: string,
  focus: ProjectFocusInput,
): Promise<Project> {
  return sendJson<Project>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "projects", id),
    { focus },
    "Could not update this project's focus.",
  );
}

/** The caller joins a lab/department project they are eligible for. */
export function joinProject(id: string): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "join"),
    undefined,
    "Could not join the project.",
  );
}

/** The caller leaves a project they belong to. */
export function leaveProject(id: string): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "leave"),
    undefined,
    "Could not leave the project.",
  );
}

/**
 * A lab owner/admin/PI puts one of the lab's own members straight onto one of
 * the lab's projects — the "no invitation needed" path, since that person can
 * already see the lab's work. Anyone else goes through `inviteToProject`.
 */
export function addProjectMember(
  id: string,
  username: string,
): Promise<Project> {
  return sendJson<Project>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "members"),
    { username },
    "Could not add the member.",
  );
}

/** Remove someone from a project (its editor only). */
export function removeProjectMember(
  id: string,
  username: string,
): Promise<void> {
  return sendJson<void>(
    "DELETE",
    buildApiUrl(getPublicApiBase(), "projects", id, "members", username),
    undefined,
    "Could not remove the member.",
  );
}

/**
 * Invite someone to a project by username or email. The invitation grants that
 * one project on accept and never lab membership, so it is the right path for
 * an outside collaborator. Targets an existing Mycelium account only.
 */
export function inviteToProject(
  id: string,
  identifier: string,
  message?: string,
): Promise<ProjectInvitation> {
  return sendJson<ProjectInvitation>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "invitations"),
    message ? { identifier, message } : { identifier },
    "Could not send the invitation.",
  );
}

/** Withdraw a pending project invitation. */
export function cancelProjectInvitation(
  id: string,
  invitationId: string,
): Promise<{ id: string; status: string }> {
  return sendJson(
    "POST",
    buildApiUrl(
      getPublicApiBase(),
      "projects",
      id,
      "invitations",
      invitationId,
      "cancel",
    ),
    undefined,
    "Could not cancel the invitation.",
  );
}

/** Accept, reject, or ignore a project invitation addressed to the caller. */
export function respondProjectInvitation(
  invitationId: string,
  action: InvitationAction,
): Promise<{ id: string; status: string }> {
  return sendJson(
    "POST",
    buildApiUrl(
      getPublicApiBase(),
      "project-invitations",
      invitationId,
      "respond",
    ),
    { action },
    "Could not answer the invitation.",
  );
}

/**
 * Share a piece of content (usually one of Mylo's picks) into a project's
 * team feed. A non-participant gets a 403, which the caller surfaces via the
 * project's `is_member` flag rather than by parsing this error.
 */
export function shareToProject(
  id: string,
  contentId: string,
  note?: string,
): Promise<{ share_id: string; content_id: string }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "shares"),
    note ? { content_item: contentId, note } : { content_item: contentId },
    "Could not share this to the project.",
  );
}

/**
 * Resolve a pasted DOI/article link into a project share. A resolvable-but-
 * abstract-less paper still comes back 201 with `embed_status: "no_abstract"`.
 * An unresolvable link 422s with `{ detail }`; `sendJson`'s generic error
 * handling already surfaces a top-level `detail` string (same path as a DRF
 * field error), so that friendly reason reaches the caller untouched.
 */
export function ingestProjectLink(
  id: string,
  rawInput: string,
  note?: string,
): Promise<IngestLinkResult> {
  return sendJson<IngestLinkResult>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "ingest-link"),
    note ? { raw_input: rawInput, note } : { raw_input: rawInput },
    "Couldn't resolve that link. Try a different DOI or URL.",
  );
}

/** Record that the caller viewed a project feed item (fire-and-forget). */
export function markProjectItemSeen(
  id: string,
  contentId: string,
): Promise<{ content_id: string; first_seen_via: string; seen_by_count: number }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "items", contentId, "seen"),
    undefined,
    "Could not record that view.",
  );
}

/** Engagement actions the events endpoint accepts for a project content item. */
export type ProjectEventAction =
  | "view"
  | "save"
  | "share"
  | "thumbs_up"
  | "thumbs_down"
  | "dismiss"
  | "open_external";

/** Record an engagement event for a project content item. */
export function recordProjectEvent(
  id: string,
  contentId: string,
  action: ProjectEventAction,
): Promise<{ content_id: string; action: string; weight: number }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "events"),
    { content_item: contentId, action },
    "Could not record that action.",
  );
}

/** Create a shared reading list (collection) within a project. */
export function createCollection(
  id: string,
  name: string,
  description?: string,
): Promise<CollectionDetail> {
  return sendJson<CollectionDetail>(
    "POST",
    buildApiUrl(getPublicApiBase(), "projects", id, "collections"),
    description ? { name, description } : { name },
    "Could not create the list.",
  );
}

/** Rename, re-describe, or archive/unarchive a collection. */
export function updateCollection(
  id: string,
  collectionId: string,
  patch: Partial<Pick<CollectionBrief, "name" | "description" | "is_archived">>,
): Promise<CollectionDetail> {
  return sendJson<CollectionDetail>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "projects", id, "collections", collectionId),
    patch,
    "Could not update the list.",
  );
}

/**
 * Add a content item to a collection. The backend returns 201 for a newly
 * added item and 200 if it was already in the list — both are success.
 */
export function addToCollection(
  id: string,
  collectionId: string,
  contentId: string,
  note?: string,
): Promise<CollectionDetail> {
  return sendJson<CollectionDetail>(
    "POST",
    buildApiUrl(
      getPublicApiBase(),
      "projects",
      id,
      "collections",
      collectionId,
      "items",
    ),
    note ? { content_item: contentId, note } : { content_item: contentId },
    "Could not add this to the list.",
  );
}

/** Remove a content item from a collection. */
export async function removeFromCollection(
  id: string,
  collectionId: string,
  contentId: string,
): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(
    buildApiUrl(
      getPublicApiBase(),
      "projects",
      id,
      "collections",
      collectionId,
      "items",
      contentId,
    ),
    {
      method: "DELETE",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
    },
  );
  if (!response.ok) {
    throw new Error("Could not remove this from the list.");
  }
}

/** Dismiss a member suggestion so it stops surfacing. */
export function dismissSuggestion(
  id: string,
): Promise<{ id: string; dismissed: boolean }> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "suggestions", id, "dismiss"),
    undefined,
    "Could not dismiss this suggestion.",
  );
}

/** Update a lab's collective purpose & goals. */
export function updateLabProfile(
  slug: string,
  payload: Partial<
    Pick<
      LabProfileData,
      | "statement"
      | "areas"
      | "funding_needs"
      | "strategic_needs"
      | "interests"
      | "institution_type"
      | "country"
    >
  >,
): Promise<LabProfileData> {
  return sendJson<LabProfileData>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "profile"),
    payload,
    "Could not save the lab's purpose and goals.",
  );
}

// ---------------------------------------------------------------------------
// Roster management
// ---------------------------------------------------------------------------
//
// The backend has had these for a while; nothing in the app called them, so a
// PI had no way to remove anyone. Authority runs strictly downward server-side
// (only the PI creates admins, ownership moves by transfer alone), and the UI
// mirrors that by hiding what it cannot do rather than offering a control that
// will 403.

/**
 * Hand the lab to another member; you become an admin.
 *
 * One call rather than two role edits, because the in-between state — two
 * owners, or none — is not one a lab should sit in. It cannot be undone from
 * this side: an admin cannot grant ownership, so only the new owner can hand it
 * back.
 */
export async function transferLabOwnership(
  slug: string,
  username: string,
): Promise<LabMember> {
  return sendJson<LabMember>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "transfer-ownership"),
    { username },
    "Could not transfer the lab.",
  );
}

/** The logo endpoint's write response (also the flags on `MyLab`). */
export type LabLogoResult = { has_logo: boolean; logo_version: number | null };

/** Upload (or replace) a lab's logo — multipart so the file rides along. */
export async function uploadLabLogo(
  slug: string,
  file: File,
): Promise<LabLogoResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "logo"),
    {
      method: "POST",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
      body: form,
    },
  );
  let parsed: (LabLogoResult & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as LabLogoResult & Record<string, unknown>;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    throw new Error(
      firstError(parsed) ?? "Could not upload the logo. Use a PNG, JPG, or SVG under 2 MB.",
    );
  }
  return parsed as LabLogoResult;
}

/** Clear a lab's logo. */
export async function deleteLabLogo(slug: string): Promise<LabLogoResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "logo"),
    {
      method: "DELETE",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
    },
  );
  if (!response.ok) {
    throw new Error("Could not remove the logo.");
  }
  return (await response.json()) as LabLogoResult;
}

/** Update what Mylo watches for a lab. */
export function updateLabWatch(
  slug: string,
  payload: Partial<WatchData>,
): Promise<WatchData> {
  return sendJson<WatchData>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "watch"),
    payload,
    "Could not save the lab's watch settings.",
  );
}

/** The draft a lab synthesis returns for the review step (nothing is saved). */
export type LabSynthesisResult = {
  statement: string;
  areas: string[];
  keywords: string[];
};

/**
 * Draft a lab's statement/areas/keywords from the PI's description plus source
 * material — dropped files (parsed to text server-side) and pasted profile links
 * (imported best-effort). Sent as multipart so files ride along.
 */
export async function synthesizeLabProfile(
  slug: string,
  input: {
    description: string;
    areas: string[];
    links: string[];
    files: File[];
  },
): Promise<LabSynthesisResult> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();

  const form = new FormData();
  form.append("description", input.description);
  form.append("areas", JSON.stringify(input.areas));
  form.append("links", input.links.join("\n"));
  for (const file of input.files) {
    form.append("files", file);
  }

  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "intake", "synthesize"),
    {
      method: "POST",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
      body: form,
    },
  );

  let parsed: (LabSynthesisResult & Record<string, unknown>) | null = null;
  try {
    parsed = (await response.json()) as LabSynthesisResult &
      Record<string, unknown>;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    throw new Error(
      firstError(parsed) ??
        "Could not synthesize the lab profile. You can fill it in manually.",
    );
  }
  return parsed as LabSynthesisResult;
}

/**
 * Save a bookmarkable item to the caller's personal workspace, or — when
 * `labSlug` is given — to that lab's shared saves (managers only, enforced
 * server-side).
 */
export function saveOpportunity(
  contentId: string,
  note?: string,
  labSlug?: string,
): Promise<SavedDeadline> {
  const body: Record<string, string> = { content_id: contentId };
  if (note) body.note = note;
  if (labSlug) body.lab_slug = labSlug;
  return sendJson<SavedDeadline>(
    "POST",
    buildApiUrl(getPublicApiBase(), "opportunities", "save"),
    body,
    "Could not save this item.",
  );
}

/** Remove a personal save, or a lab save when `labSlug` is given (managers only). */
export async function unsaveOpportunity(
  contentId: string,
  labSlug?: string,
): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const base = buildApiUrl(
    getPublicApiBase(),
    "opportunities",
    "save",
    contentId,
  );
  const url = labSlug ? `${base}?lab=${encodeURIComponent(labSlug)}` : base;
  const response = await fetch(url, {
    method: "DELETE",
    credentials: "include",
    headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
  });
  if (!response.ok && response.status !== 404) {
    throw new Error("Could not remove this save.");
  }
}

/**
 * Ignore an item: stop surfacing it on this reader's feeds. Personal only —
 * there is no lab scope, because an ignore is a fact about the reader.
 */
export function ignoreItem(contentId: string): Promise<void> {
  return sendJson<void>(
    "POST",
    buildApiUrl(getPublicApiBase(), "opportunities", "ignore"),
    { content_id: contentId },
    "Could not ignore this item.",
  );
}

/** Undo an ignore, putting the item back on the reader's feeds. */
export async function unignoreItem(contentId: string): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const response = await fetch(
    buildApiUrl(getPublicApiBase(), "opportunities", "ignore", contentId),
    {
      method: "DELETE",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
    },
  );
  // A 404 means it is already not ignored, which is the state the caller wanted.
  if (!response.ok && response.status !== 404) {
    throw new Error("Could not restore this item.");
  }
}

/** Create a deadline reminder (personal or lab) from a saved/opportunity item. */
export function createReminder(input: ReminderInput): Promise<Reminder> {
  return sendJson<Reminder>(
    "POST",
    buildApiUrl(getPublicApiBase(), "reminders"),
    input,
    "Could not create the reminder.",
  );
}

/** Edit an existing reminder: lead times, channel, mentions, snooze, or state. */
export function updateReminder(
  id: string,
  input: ReminderUpdateInput,
): Promise<Reminder> {
  return sendJson<Reminder>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "reminders", id),
    input,
    "Could not update this reminder.",
  );
}

/**
 * Stop a reminder the caller owns (personal) or manages (lab).
 *
 * The default is the server's soft cancel — the row stays, so "why did this stop
 * reminding me?" keeps an answer. `purge` destroys it for good, which is how the
 * reminders page clears out finished rows.
 */
export async function deleteReminder(
  id: string,
  options: { purge?: boolean } = {},
): Promise<void> {
  await ensureCsrfCookie();
  const csrfToken = readCsrfToken();
  const base = buildApiUrl(getPublicApiBase(), "reminders", id);
  const response = await fetch(
    options.purge ? `${base}?purge=1` : base,
    {
      method: "DELETE",
      credentials: "include",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : undefined,
    },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error("Could not remove this reminder.");
  }
}

/** Mark a bell notification read or dismissed. */
export function actOnNotification(
  id: string,
  action: "read" | "dismiss",
): Promise<unknown> {
  return sendJson(
    "POST",
    buildApiUrl(getPublicApiBase(), "notifications", id, "action"),
    { action },
    "Could not update the notification.",
  );
}

/** Disconnect the caller's Discord identity (revokes tokens, deletes the link). */
export function disconnectDiscord(): Promise<{ detail: string }> {
  return sendJson<{ detail: string }>(
    "POST",
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "disconnect"),
    undefined,
    "Could not disconnect Discord. Try again.",
  );
}

/** Re-run the DM reachability probe ("Test" button) → the refreshed link status. */
export function testDiscordDm(): Promise<DiscordStatus> {
  return sendJson<DiscordStatus>(
    "POST",
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "probe"),
    undefined,
    "Could not test the connection. Try again.",
  );
}

/** Toggle the daily "Mylo Report" PDF DM for the caller → the refreshed status. */
export function setDiscordDailyReport(optOut: boolean): Promise<DiscordStatus> {
  return sendJson<DiscordStatus>(
    "POST",
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "daily-report"),
    { opt_out: optOut },
    "Could not update your daily report setting. Try again.",
  );
}

/** Issue a one-time Path B activation code to redeem from Discord with /activate code:. */
export function issueActivationCode(): Promise<DiscordCodeResponse> {
  return sendJson<DiscordCodeResponse>(
    "POST",
    buildApiUrl(getPublicApiBase(), "integrations", "discord", "code"),
    undefined,
    "Could not generate an activation code. Try again.",
  );
}

/** Issue a 10-digit lab activation code (Path C) to redeem with /activate-lab code:. */
export function issueLabActivationCode(
  slug: string,
): Promise<DiscordLabCodeResponse> {
  const url = buildApiUrl(getPublicApiBase(), "integrations", "discord", "lab-code");
  return sendJson<DiscordLabCodeResponse>(
    "POST",
    `${url}?lab=${encodeURIComponent(slug)}`,
    undefined,
    "Could not generate a lab activation code. Try again.",
  );
}

/** A one-time department code, redeemed with `/activate-department` in Discord. */
export function issueDeptActivationCode(
  id: string,
): Promise<DiscordLabCodeResponse> {
  const url = buildApiUrl(
    getPublicApiBase(),
    "integrations",
    "discord",
    "department-code",
  );
  return sendJson<DiscordLabCodeResponse>(
    "POST",
    `${url}?department=${encodeURIComponent(id)}`,
    undefined,
    "Could not generate a department activation code. Try again.",
  );
}

/** Update a user's plan and/or watch quota (staff/superuser only). */
export function updateAdminUser(
  id: number,
  patch: AdminUserUpdate,
): Promise<AdminUserDetail> {
  return sendJson<AdminUserDetail>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "admin", "users", String(id)),
    patch,
    "Could not update this user.",
  );
}

/** Update a lab's subscription (staff/superuser only). */
export function updateAdminLab(
  slug: string,
  patch: AdminLabUpdate,
): Promise<AdminLabDetail> {
  return sendJson<AdminLabDetail>(
    "PATCH",
    buildApiUrl(getPublicApiBase(), "admin", "labs", slug),
    patch,
    "Could not update this lab's plan.",
  );
}

/**
 * Create a department; the caller becomes its head. Verified accounts only.
 * Its institution is the caller's verified one — set by the backend, not sent.
 */
export function createDepartment(name: string): Promise<MyDepartment> {
  return sendJson<MyDepartment>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments"),
    { name },
    "Could not create the department. Try again.",
  );
}

/** Create a lab's join invitation — an emailed one, or a share link. */
export function createLabInvite(
  slug: string,
  input: OrgInviteInput,
): Promise<OrgInvite> {
  return sendJson<OrgInvite>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "invites"),
    input,
    "Could not create the invitation.",
  );
}

/** Create a department's join invitation. */
export function createDeptInvite(
  id: string,
  input: OrgInviteInput,
): Promise<OrgInvite> {
  return sendJson<OrgInvite>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "invites"),
    input,
    "Could not create the invitation.",
  );
}

/** Invite several people into a lab by email in one submission. */
export function createLabInvites(
  slug: string,
  input: OrgInviteBatchInput,
): Promise<OrgInviteBatchResult> {
  return sendJson<OrgInviteBatchResult>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "labs", slug, "invites"),
    input,
    "Could not send the invitations.",
  );
}

/** Invite several people into a department by email in one submission. */
export function createDeptInvites(
  id: string,
  input: OrgInviteBatchInput,
): Promise<OrgInviteBatchResult> {
  return sendJson<OrgInviteBatchResult>(
    "POST",
    buildApiUrl(getPublicApiBase(), "auth", "departments", id, "invites"),
    input,
    "Could not send the invitations.",
  );
}

/** Withdraw one of a lab's invitations. */
export function revokeLabInvite(
  slug: string,
  inviteId: string,
): Promise<OrgInvite> {
  return sendJson<OrgInvite>(
    "POST",
    buildApiUrl(
      getPublicApiBase(),
      "auth",
      "labs",
      slug,
      "invites",
      inviteId,
      "revoke",
    ),
    undefined,
    "Could not withdraw the invitation.",
  );
}

/** Withdraw one of a department's invitations. */
export function revokeDeptInvite(
  id: string,
  inviteId: string,
): Promise<OrgInvite> {
  return sendJson<OrgInvite>(
    "POST",
    buildApiUrl(
      getPublicApiBase(),
      "auth",
      "departments",
      id,
      "invites",
      inviteId,
      "revoke",
    ),
    undefined,
    "Could not withdraw the invitation.",
  );
}


/** Save a lab's or department's announcement settings (managers only). */
export function saveAnnouncementSettings(
  target: AnnouncementTarget,
  patch: Partial<AnnouncementSettings>,
): Promise<AnnouncementSettings> {
  return sendJson<AnnouncementSettings>(
    "PUT",
    `${buildApiUrl(getPublicApiBase(), "announcements", "settings")}${announcementQuery(target)}`,
    patch,
    "Could not save the announcement settings.",
  );
}

/** Post a clearly labelled test thread in each forum. */
export function sendAnnouncementTest(
  target: AnnouncementTarget,
): Promise<{ results: { guild_name: string; purpose: string; channel_name: string; ok: boolean }[] }> {
  return sendJson(
    "POST",
    `${buildApiUrl(getPublicApiBase(), "announcements", "test")}${announcementQuery(target)}`,
    undefined,
    "Could not send a test post.",
  );
}

/** Where a web link into a Discord thread was opened from (Phase 8 measurement). */
export type DiscordLinkSurface =
  | "announced"
  | "closing_soon"
  | "card"
  | "search"
  | "dept_page";

/**
 * Count one opened thread link. Best effort and fire-and-forget: `keepalive`
 * lets it finish after the new tab takes focus, and a failure is swallowed so a
 * link never waits on, or breaks over, measurement.
 */
export function recordDiscordLinkClick(
  threadUrl: string,
  surface: DiscordLinkSurface,
): void {
  const csrfToken = readCsrfToken();
  void fetch(buildApiUrl(getPublicApiBase(), "announcements", "link-click"), {
    method: "POST",
    credentials: "include",
    keepalive: true,
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    body: JSON.stringify({ thread_url: threadUrl, surface }),
  }).catch(() => undefined);
}

/** "Create them for me" for one server binding. */
export function createAnnouncementChannels(
  bindingId: number,
): Promise<{ ok: boolean; message: string }> {
  return sendJson(
    "POST",
    `${buildApiUrl(getPublicApiBase(), "announcements", "create-channels")}?binding=${bindingId}`,
    undefined,
    "Could not create the forums.",
  );
}
