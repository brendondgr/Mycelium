# Lab-scoped Saves + Save-to-Lab Dropdown + Reminder Surfacing

**Status:** in progress
**Owner:** this session
**Depends on:** the reminders backend (R0–R9) already merged to `main`.

## Problem (from the user)

> "I am unable to see where users are able to create reminders for themselves or
> for the labs they are a part of."

The reminders **backend** and the **personal** reminder composer already exist, but
the workflow the user expects is missing its front half:

1. The bookmark/save button on feed cards is a **plain personal-only toggle**. It
   should be a **dropdown** that lets the user save an item to **Personal** or to a
   **specific lab they manage** (choosing which, when they manage several).
2. The **saved area** exists only for the personal workspace. The **lab (group)
   workspace** has no saved area at all — so there is nowhere to sit a lab-scoped
   "Set reminder" affordance.
3. From a saved item, the user should be able to set a reminder to their **personal
   Discord DM** or to the **lab channel** configured at Discord setup. The composer
   already supports both targets; it just needs a lab-scoped entry point.

## Current state (verified in code)

- `SavedOpportunity` (`apps/content/models.py:188`) is **user-only**: `user` FK,
  unique `(user, content)`. No lab dimension.
- Save/unsave: `SaveOpportunityView` (`apps/content/views.py:616`) — `POST
  /api/opportunities/save` `{content_id, note}`; `DELETE
  /api/opportunities/save/<content_id>`. Personal only.
- `_save_from_item(user, item, note=)` snapshots display+deadline fields.
- Feed `saved` flag: every opportunity/paper serializer reads
  `context["saved_ids"]` built by `_saved_content_ids(user)`
  (`views.py:150/381/536/910`).
- Saves page: `SavedItemsView` (`views.py:723`) joins each save to the **viewer's**
  `RelevanceScore` for feed-parity `card` payloads; snapshot fallback when pruned.
- Reminders API: `ReminderListCreateView` (`apps/content/reminders_views.py:144`)
  — lab reminders resolve a lab, check access, and `create_subscription` enforces
  **manager** authority; rolling/undated deadlines rejected.
- Frontend save button: `SaveButton` (`opportunity-bits.tsx:172`), a binary toggle,
  used by GrantRow / ConferenceCard / FellowshipRow / SuggestionCard.
- `useSaveOpportunity` (`hooks.ts:271`) → `saveOpportunity(contentId, note)` /
  `unsaveOpportunity(contentId)` (`mutations.ts:418`).
- Reminder composer: `reminder-composer.tsx` already supports scope
  personal/lab + lab `<select>`; wired into personal Saves (`saves-section.tsx`).
- Workspace shell has a **`labScope`** context (`portal-context.tsx:97`,
  `currentLab`); `overview-section.tsx:191` swaps to `LabOverviewSection` when a
  lab is active. **This is the pattern to mirror for Saves.**
- Lab role/authority: `LabMembership.Role` owner/admin/member/viewer + `is_lead`;
  `user_can_manage_lab` (owner/admin/superuser), `user_has_lab_access` (any member).

## Design decisions

- **Who can save to a lab / remove / set a lab reminder:** lab **managers** —
  owner, admin, or PI (`user_can_manage_lab`). Matches the user's "admins or owners"
  and mirrors the reminder authority already enforced by `create_subscription`.
- **Who can view a lab's saved area:** **any lab member** (`user_has_lab_access`).
  A lab's saves are a shared lab resource; only managers get the mutate/remind
  affordances.
- **Lab saved area location:** reuse the existing **Saves** section, made
  lab-aware via `currentLab` — no new route tree. Mirrors the overview swap.
- **Save dropdown scope:** offered on every saveable card (papers included —
  lab-saving a paper is a shared reading pick). Reminders remain offered only for
  dated deadline items (unchanged). When the user manages **no** labs, the control
  stays the current one-click personal toggle (no empty dropdown).
- **Uniqueness:** personal save unique `(user, content)` (personal only); lab save
  unique `(target_lab, content)` — one lab save per item regardless of which
  manager added it. `user` on a lab save records **who** added it.
- **Lab card payloads:** build from the **lab's** `RelevanceScore` (target_lab)
  when present, else the snapshot — same machinery as the personal Saves view.

## Non-goals

- No per-lab feed pages (grants/papers/etc. stay personal + the lab overview
  roll-up). Only the **saved area** becomes lab-scoped.
- No change to reminder delivery/tick logic — it already handles lab reminders.
- No new tier gates beyond what already applies.

---

## Steps (each with its validation)

### Phase A — Backend: lab-scoped saves

**A1. Model.** Add to `SavedOpportunity`:
- `target_lab = FK(accounts.Lab, null=True, blank=True, on_delete=CASCADE, related_name="saved_opportunities")`.
- Update the existing partial unique `content_saved_opportunity_unique_user_content`
  to add condition `target_lab__isnull=True` (personal saves only).
- Add partial unique `content_saved_opportunity_unique_lab_content` on
  `(target_lab, content)` with condition `content__isnull=False, target_lab__isnull=False`.
- Add index `(target_lab, deadline_date)`.
- Docstring: `user` = the saver/actor; a lab save is one where `target_lab` is set.
- **Validate:** `makemigrations content` → one migration; `migrate`; `makemigrations
  --check --dry-run` clean.

**A2. Save/unsave service + view.** `_save_from_item(user, item, *, note,
target_lab=None)` → parametrize `update_or_create` key on `content` + (`user` for
personal, `target_lab` for lab; the other stays the actor/null). `SaveOpportunityView.post`
reads optional `lab_slug`: resolve lab, `user_can_manage_lab` else 403, save to lab.
`SaveOpportunityView.delete` reads optional `?lab=<slug>`: lab unsave requires
manage; else personal unsave (unchanged default).
- **Validate:** unit tests — personal save unchanged; manager can lab-save; non-manager
  403; lab unsave manager-only; personal + lab save of same item coexist.

**A3. Lab saves list.** `LabSavedItemsView` → `GET /api/labs/<slug>/saves/`,
`user_has_lab_access` else 403. Mirror `SavedItemsView` but filter
`target_lab=lab` and resolve cards from the **lab's** `RelevanceScore`
(`target_lab=lab`), snapshot fallback. Add `saved_by` (username) + `can_manage`
(the viewer's authority) to the envelope so the UI can gate affordances.
- **Validate:** member sees the lab's saves with cards/snapshots; non-member 403;
  `can_manage` true for owner/admin, false for member.

**A4. Feed `saved_labs`.** Add `_saved_lab_slugs_by_content(user)` →
`{content_id: [lab_slug,...]}` for labs the user **manages** that have saved the item.
Add a `saved_labs` `SerializerMethodField` to the opportunity/paper serializers
reading `context["saved_labs"]`. Thread the context into the feed views alongside
`saved_ids`.
- **Validate:** a grant lab-saved by a managed lab reports `saved_labs:["slug"]` in
  the grants feed; personal-only save reports `[]`; one query, no N+1 (assert query
  count stable).

### Phase B — Frontend: dropdown + lab saved area

**B1. Types + client + hooks.** Add `saved_labs: string[]` to `OpportunityBase`
(+ `Suggestion`, `SearchResultItem`). `saveOpportunity(contentId, note?, labSlug?)`
(POST adds `lab_slug`); `unsaveOpportunity(contentId, labSlug?)` (DELETE adds
`?lab=`). `useSaveOpportunity` variants take `labSlug`. Add `fetchLabSaves(slug)`
+ `useLabSaves(slug)` (invalidated by the save mutations); a `LabSavesResponse`
type (`items`, `can_manage`).
- **Validate:** `tsc --noEmit` clean.

**B2. Save-scope control.** Replace `SaveButton` usage with a `SaveMenu`:
- 0 managed labs → current one-click personal toggle (unchanged look).
- ≥1 managed lab → a bookmark button + caret; menu lists **Personal** and each
  managed lab, each showing a check when already saved (personal from `saved`, lab
  from `saved_labs`). Selecting toggles that scope. Keyboard + `aria` menu semantics,
  outside-click close, reduced-motion safe.
- **Validate:** build; DOM/interaction reasoning (no browser in worktree — see
  memory `preview-pinned-to-main-checkout`), tsc + eslint clean.

**B3. Lab-aware Saves section.** `SavesSection` reads `currentLab`:
- personal scope → today's behavior.
- lab scope → `useLabSaves(slug)`; render the same cards; "Remind me" shown only
  when `can_manage`, opening `ReminderComposer` with new props `lockedScope="lab"`
  + `lockedLabSlug={slug}` (composer hides the scope/lab pickers when locked).
  Unsave affordance manager-only. Empty/loading/error/permission states.
- **Validate:** build + tsc + eslint; verify the composer POSTs
  `scope:"lab", lab_slug` when locked.

**B4. Composer lock props.** `ReminderComposer` accepts `lockedScope?` /
`lockedLabSlug?`; when set it fixes scope=lab + lab and hides those fields.
- **Validate:** personal path unchanged; locked path pre-fills + submits lab reminder.

### Phase C — Validate, document, commit, merge

**C1.** Backend: `uv run --project web/backend pytest web/backend` green; `ruff
check` clean; `makemigrations --check --dry-run` clean.
**C2.** Frontend: hardlink node_modules into the worktree; `tsc --noEmit`, `eslint`,
`next build` clean.
**C3.** Update `docs/changelog.md` (schema in `docs/skills/global.md`) and
`docs/repo-map.md` (new lab-saves endpoint + `saved_labs`).
**C4.** Commit (no push).
**C5.** Merge current `main` into the branch, resolve conflicts, re-verify, then
fast-forward `main` from the primary checkout `/home/bdgr/Agents/Mycelium` with
`--ff-only` (preserve any other session's uncommitted files).

## Risks / watch-items

- **Uniqueness migration** on an existing table: the personal partial unique gets a
  new condition — Django drops+recreates it; safe on an empty/dev DB, note for prod.
- **`saved_labs` query cost** across every feed — compute once per request as a dict,
  never per-card.
- **Tier gating:** feeds already run through tier gates; the save endpoints are not
  scheduled pipelines, so no new tier interaction expected — confirm tests don't
  silently skip (entitle a Spore user where a pipeline is involved).
- **Card resolution for lab saves** depends on a lab `RelevanceScore` existing; when
  absent, snapshot fallback must still render (papers especially).
