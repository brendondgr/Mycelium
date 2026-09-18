# Plan CN-06 — Search Panel and Entry Points

**Status:** draft. **Depends on:** CN-05. **Unblocks:** CN-07.
**Correlation ID:** `20260918-collaboration-network-06`

## Objective

Put the matcher where the need already is, without a new page to navigate to
(`design §8.2`). The opportunity stays visible while the seeker searches. This
plan follows `docs/styles.md`, `web/CLAUDE.md`, and the ui-frontend and
mobile-friendly skills, and reuses the portal primitives.

## Surfaces

1. **Opportunity card.** CN-03's team-fit line gains a "Find collaborators"
   action when at least one slot is a gap, the seeker may search (OD-CN5), and
   `COLLAB_SEARCH_ENABLED` is on. It opens the panel pre-filled with the
   call's slots and coverage.
2. **The panel** — a side sheet on desktop, a full-height sheet on mobile:
   - the slots as editable chips grouped by facet, each marked covered /
     lab-covered / gap; add, remove, rewrite;
   - lane toggles and the scope selector (showing only scopes the seeker may
     use; at launch, institution);
   - **Run**. Nothing searches until pressed;
   - results in two groups, **Fills a gap** and **Shares expertise**, each
     result a coarse pointer with its lane label, evidence tag ("from their
     papers" / "from their profile"), rationale, and **Save** / **Not
     relevant**;
   - honest empty states: "Nobody at your institution who is open to
     collaboration matches this yet" — never a padded list.
3. **Project page.** A **Collaborators** tab opens the same panel pre-filled
   from the project's facets. It is visible only to people who can already see
   the project.
4. **Manual search.** "Find collaborators" in the ⌘K palette and on the
   Projects section opens the panel empty.
5. **Saved people.** A small list under the panel of people the seeker saved,
   with the lane and the query they were found for. Private to the seeker.

## Constraints

6. The panel never shows a count of how many people were filtered out by
   consent or by the appearance cap; that count leaks availability.
7. Mounted is not reachable: each surface is traced route → page → section in
   the change's own description, and checked in a browser at desktop and phone
   width.

## Steps

8. `components/portal/collab/{search-panel,slot-editor,result-card}.tsx`;
   `lib/portal/collab/{types,client,hooks,mutations}.ts`.
9. The card action, the project tab, the palette entry.
10. Browser check (fixture users on a local database only — not the live one);
    changelog; repo map.

## Acceptance

- With `COLLAB_SEARCH_ENABLED` off, no surface shows the action.
- A free-tier seeker sees the team-fit line and an upgrade note, not the
  search.
- Lanes render as separate groups at every width.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.
