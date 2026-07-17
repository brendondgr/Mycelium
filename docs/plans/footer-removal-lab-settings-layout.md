# Plan — Remove API-health footer + reorganize Lab Settings layout

## Objective

Two contained frontend changes in `web/app/`:

1. Remove the app's bottom status footer (the "API healthy / preview" bar) entirely.
2. Re-lay the manager-only **Lab settings** surface into a two-column layout matching
   the requested whiteboard:
   - **Left column** (narrow, stacked): Logo upload → Invite members → Mylo Discord → Projects.
   - **Right column** (wide, stacked): Purpose & Goals (+ Focus areas) on top; Members (as a
     tile grid) below.

## Assumptions

- The whiteboard reorders the *existing* Lab-settings cards; no new data or endpoints.
- Only the **Lab settings** view (`lab-settings-section.tsx`) gets the two-column layout.
  The "Manage lab" view in `labs-section.tsx` (`LabDetail`) keeps its current single-column
  stack — it is a different surface and not in scope.
- `LabSettingsSection` already gates to lab managers (returns a permission note otherwise),
  so inside the new layout `canManage` is always true.

## Files that change

- `web/app/src/components/portal/workspace-shell.tsx` — drop `<PortalFooter />` + its import.
- `web/app/src/components/portal/portal-footer.tsx` — delete (only consumer is the shell).
- `web/app/src/components/portal/sections/labs-section.tsx` — export the individual cards
  (`LabPurposeCard`, `InviteCard`, `DiscordSyncCard`, `MembersCard`, `ProjectsCard`) so the
  settings surface can compose them; add an optional `grid` layout to `MembersCard` (2-col
  member tiles) without changing its default row rendering used by `LabDetail`.
- `web/app/src/components/portal/sections/lab-settings-section.tsx` — replace the vertical
  stack with the two-column grid; keep the existing `LabLogoCard`.

## Implementation phases

1. **Footer removal.** Remove `<PortalFooter />` and its import from `workspace-shell.tsx`;
   delete `portal-footer.tsx`. Confirm no other references (`grep PortalFooter`).
2. **Expose cards.** Export the five sub-cards from `labs-section.tsx`. Add a `grid?: boolean`
   prop to `MembersCard`; when set, render members as a responsive 2-col tile grid instead of
   the full-width `MemberRow` list.
3. **Compose the layout.** In `lab-settings-section.tsx`, render a `grid` with a narrow left
   column (Logo, Invite, Discord, Projects) and a wide right column (Purpose & Goals, Members
   grid). Collapse to a single column on mobile. Pass `canManage`/`grid` as needed.

## Validation & acceptance

- `npm run lint` and `npm run typecheck` (or the repo-root equivalents) pass for `web/app`.
- Manager view of Lab settings shows: left column = Logo / Invite / Discord / Projects;
  right column = Purpose & Goals (top) + Members tile grid (bottom).
- Non-manager still sees the permission empty state.
- App renders with no footer; no console errors from the removed component.
- Layout collapses cleanly to one column on mobile; existing tokens/cards reused (no new colors).

## Exclusions

- No backend, API, or data-model changes.
- No change to `LabDetail` as used by the "Manage lab" (`LabsSection`) view.
- No copy/product-direction changes beyond removing the retired footer message.
