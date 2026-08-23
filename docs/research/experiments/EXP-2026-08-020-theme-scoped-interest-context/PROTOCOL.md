# Protocol — theme-scoped interest context

## The defect

A reader with five declared research themes opened their report and found the
same knowledge-graph workshop leading the conference list of **all five**,
including Computer Vision & Sensing and Robotics & Emerging Tech. The per-theme
slates introduced by the redesign were not duplicating by accident — each theme
genuinely ranked by its own score, and the five orders did differ from position 2
onward — but the same item won position 1 everywhere.

Root cause, found by reading the stored signals: that item scored exactly
`1.0000` on **all 22 of the reader's interests**, including `nanotechnology` and
`quantum computing in various fields`. `interests_query.search_interests` built
each area's query as `"<area> <every keyword>"`, and
`opportunities.opportunity_search_interests` merged every watch topic into those
keywords first. For this profile that is a 473-character shared suffix on a
24-character label — all 22 queries ~95% identical text, only 11 distinct
suffixes across 22 interests. `fuse_interest` min-max normalises, so the best
match for the shared suffix becomes `1.0` for every interest at once. With every
score tied at 1.0, `combine_interests`' softened CombMNZ reduces to
`1.0 x (1 + beta(n-1))` — the per-theme score becomes a function of **how many
areas the reader typed into each theme**, and nothing else.

## Change under test

`search_interests` takes the profile's themes and pads each area with up to
`INTEREST_CONTEXT_TERMS` (3) of **its own theme's** sibling areas. The
profile-wide keyword suffix and the watch-topic merge are removed. The implicit
cluster contributes no context, because it holds every area and would rebuild the
same suffix under a different name.

## Hypothesis (written before the run)

The five themes stop asking the same question, so no single item can top all of
them. Concretely: the number of *distinct* items across a category's five slates
rises, mean pairwise Jaccard between slates falls, the count of items present in
every slate falls toward zero, and the number of distinct rank-1 items rises from
1 to 5. Recall should also rise — narrower queries retrieve different documents
per theme, so the union pool grows.

Stated as a falsifiable acceptance test, per category:

> **five themes must produce five distinct rank-1 items.**

## Measurement

**Primary — production.** The real `ContentItem` store (35,209 papers, 2,171
grants, 912 conferences, 818 fellowships) against one real profile
(`brendondgr`, 5 themes, 22 areas). Per category: candidate pool size, distinct
items across all five slates, mean pairwise Jaccard between slates, share of
items present in every slate, and the count of distinct rank-1 items. Before is
the run at `9dffa35`; after is the run at `5fb2fee`. Both are full refits
(`run_refitting --user brendondgr`), so both re-rank the whole corpus.

**Secondary — the LongEval harness.** `slate_profile` and `clustered_profile` at
`match_threshold=0.5`, the two arms that exercise the cluster path, re-run at the
same config hashes under the re-run rule.

## What this cannot answer

Whether the *new* rankings are better, only that they are differentiated. The
production corpus carries no relevance judgements, so "the Robotics theme now
leads with a surgical-robotics venue instead of a knowledge-graph workshop" is a
coherence argument, not a measurement. n = 1 profile.

The harness cannot answer it either, and for a structural reason worth recording:
`eval/harness/profiles.py` constructs `SearchInterest` objects directly with
`query_text = label`, so it has **never** called the function this change
rewrites. Every profile-arm number in this record was measured on bare per-area
queries that production did not use.
