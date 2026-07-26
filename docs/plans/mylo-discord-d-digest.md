# Phase D — Cluster-first digests + the lab channel

**Status:** As built.
**Correlation ID:** `20260726-cluster-digests-lab-channel`
**Umbrella:** [`mylo-discord-pipeline.md`](mylo-discord-pipeline.md)

## Objective

Close L5/L7: attribute every content type to a research theme, organise the report
by theme, and finally post a lab's digest to the updates channel it already binds.

## What the build actually found

**Cluster attribution for opportunities was a dispatch, not a rewrite.**
`pipeline.fuse_clusters_pool` was already generic over `content_type` and already
accepted a match threshold; `opportunities._prepare_match` simply never called it.
That is why the cluster badge on a grant card — built during the cluster sprint, and
documented in `types.ts` as *"reserved"* — had never had a value to show. The change
is the same `len(clusters) >= 2` dispatch papers use, plus lifting the three cluster
reader methods into `ClusterAttributionMixin` so a grant and a paper resolve a
renamed cluster identically.

## Decisions

| # | Decision | Why |
|---|---|---|
| D-a | **A half-attributed report keeps the old category-first shape.** | Organising by theme when only some items carry one would strand the rest somewhere the reader cannot account for. Better unchanged than quietly incomplete. |
| D-b | **Fewer than two clusters keeps the flat path byte-for-byte.** | The invariant every cluster feature here preserves: nobody's feed or report changes shape because a capability now exists. |
| D-c | **Idempotency is the outbox dedupe key**, `lab_digest:<lab>:<date>`. | A database uniqueness constraint, so re-running the daily chain is a no-op. No separate ledger and no "have I sent today?" query to race. |
| D-d | **A quiet day posts nothing.** | A daily "I found nothing" teaches people to ignore the channel. |
| D-e | **Nobody is tagged.** | It is an update, not a summons. `allowed_mentions.parse` stays empty. |
| D-f | **Bounded by construction** — 8 themes × 3 items. | Inside Discord's 25-field / 6000-character embed limits without truncation logic. |
| D-g | **Every precondition checked at delivery**, not trusted from setup. | Add-on live, guild active, channel bound. A blank channel stays a silent opt-out. |

## Where it lives

`apps/content/opportunities.py` (dispatch), `serializers.py` (mixin),
`briefing_agents.py` (`group_by_cluster`, `_cluster_first_body`),
`apps/content/lab_digest.py`, `management/commands/send_lab_digests.py`,
`manual_all.py` (new final stage).

## Validation

`test_opportunity_clusters.py` (4, Postgres-gated), `test_briefing_clusters.py` (7),
`test_lab_digest.py` (13).
