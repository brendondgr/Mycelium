
## Run 1 — failed: a harness bug in the ranking step

Worktree `d79b9eb`, 06:38–06:45 UTC. The Plan 04 pass and the eight-week
simulation ran; the ranking step then crashed
(`AttributeError: 'tuple' object has no attribute 'item'` — the harness read
fusion's slate entries as objects; they are `(item, score)` pairs). The
harness wrote nothing before the crash, so the simulation's results were lost
with it. No metric from run 1 exists or is reported.

**Fixes (harness only):** slate entries read as pairs; the nights' results are
written to `<out>.nights` before the ranking step starts. **Run 2** reruns the
registered protocol from a worktree pinned at the fix.

## Run 2 — completed; invariants invalid (harness scope), one product gap found

Worktree `5d65e19`, 06:46–06:54 UTC. The run completed, but its invariant
counts are not results:

- `active_without_yes` (1,890) and `evidence_of_deleted` (21) counted edges of
  the 600-person collaboration world that `mycelium_sandbox` already holds,
  whose planted conversational edges exist to test that collaboration search
  never sees them. The checks must be scoped to this experiment's people. A
  harness defect.
- `forgotten_edges_remain` / `forgotten_findings_remain` (3 each) were checked
  on the night of the opt-out, before the next night's retraction pass ran.
  That is not a harness defect alone: it shows "delete my observations" leaves
  a person's conversational edges and findings in place for up to a day, where
  principle 11 says every derived influence goes. **Product change before run
  3:** `reconcile.forget_person` now deletes the person's conversational edges
  and findings and withdraws their open questions at once (unit-tested).
- The registered exploration-slate precision (0.16) is capped by the corpus:
  four papers per topic against a 25-deep slate. Inspecting the slates, every
  one led with all four of its own topic's papers. The registered measure is
  reported as it is; run 3 adds a post-hoc measure, the share of a topic's own
  papers that lead its exploration slate.

Run 2's ranking numbers do not depend on the scope defect and are kept in the
record: at weight 0.15, declared slates Jaccard 0.985 (min 0.852), 0.167
declared items displaced from a top 25 on average (max 1); at weight 1.0, 8.0
(max 13).

**Run 3** reruns the registered protocol with the scoped checks, the added
measure, and the immediate opt-out, from a worktree pinned at that commit.

## Run 3 — registered, valid

Worktree `8d47faf`, 07:11–07:22 UTC. One invariant violation:
`evidence_of_deleted` (1) — on the night a person asked Mylo to forget one
observation, a confirmed edge still cited it until the next night's retraction
pass. Same class as run 2's opt-out gap, for "forget that" and platform
deletions. **Fixed after the run** (`reconcile._drop_derived`: the pointers
leave edges and findings in the same transaction as the observation), with a
unit test; run 4 (post hoc) confirms.

## Run 4 — post hoc

Worktree `45e6477`, 07:41–07:47 UTC: 0 invariant violations; the ranking
numbers match run 3's (0.983 / 0.143 / 7.0). Run 3's H1 verdict stands.
