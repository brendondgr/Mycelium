# EXP-2026-08-013 — Issues

## 1. Pre-registration, and what existed before it

`PROTOCOL.md` was written before either arm was scored. What existed first was
setup knowledge, and it is listed so the pre-registration can be judged rather
than taken on trust: the store's row counts, the shape of `_build_pool`, the
two facts about scoping in §"What production actually does", the target and
interest inventory, and the embedder alignment gate (cosine 0.9999999999999998,
re-run inside `code/run.py` as gate 0). No reachability figure, no pool size, no
entrant count, and no premise measurement had been computed.

The decision rule, its two thresholds, the real-target sensitivity split, and the
asymmetry in §2 of the protocol — that the experiment can prove *inert* but not
*beneficial* — were all fixed in advance.

## 2. A2p was added after the protocol was written, before anything was run

`PROTOCOL.md` names arms A1, A2 and A3. **A2p** (`union_pool_prod`) was added
while writing `code/production_pool.py`, before any arm ran, for a reason worth
recording:

The harness arm `eval/harness/arms.py::fusion_union_pool` — the arm C-008 was
measured with, and therefore the arm this experiment must mirror to be a
replication — truncates its lexical channel at `pool_per_interest`, while
`_build_pool` does not truncate its own (BM25 over the pool returns every
non-zero hit). Mirroring that asymmetry is right for comparability and wrong for
a production decision, so both are run: **A2** is the harness arm verbatim, and
**A2p** is `_build_pool` with a wider pool seed and its own untruncated lexical
channel — what a change to `apps.content` would actually look like.

The surfacing result is quoted from A2p. The reachability result does not depend
on the arm at all: it is a property of the corpus-wide BM25 top-100 and the
dense pool, computed once per interest.

A fourth arm, **A4**, was added for the same reason — see §4.

## 3. The union arms complete a gate the deployed code does not

This is the experiment's central measurement and it needs its mechanics stated
plainly, because it is the one place the arms deliberately do something
production does not.

`fuse_interests_pool` surfaces a candidate when
`best_cosine[id] >= match_threshold`, and `_build_pool` writes `best_cosine`
only from the dense channel's hits. A union-only candidate therefore has no
entry, is read as `0.0`, and is dropped. Every union arm is reported **twice**:

- **deployed gate** — `best_cosine` left exactly as `_build_pool` produces it.
  This is what shipping only the pool change would do. Result: 0 union-only
  entrants, in all four arms, in all 126 pairs.
- **completed gate** — `best_cosine` computed for every pool member from its
  stored embedding (`complete_cosines` in `code/run.py`), which any real fix
  must do. Result: 7,440 union-only entrants for A2p.

Neither number is the "true" one; the pair is the finding. Reporting only the
first would say the fix is worthless and only the second would hide that the fix
as usually described is incomplete.

## 4. The FTS arm needed a second version to not be a strawman

A3 runs the corpus-wide lexical channel `apps/content/search.py` uses for
`/api/search/`, unchanged. It returns nothing for 728 of 798 interest queries,
because `websearch` ANDs unquoted terms and `search_interests` appends the
profile's keyword list to every area.

Condemning Postgres FTS on that basis would be unfair — the fault is the query
construction, not the index — so **A4** runs the same index with OR semantics
(`SearchQuery(" | ".join(tokens), search_type="raw")`) and recovers to 4 empty of
798 and median reachability 0.540. Both are reported. The 91% empty rate is a
statement about **reusing that channel for the feed**; `/api/search/` is fed
user-typed queries and nothing here says it is broken.

## 5. n is small and the regimes are not independent

Six targets and 38 declared interests, because the store has six users. Three of
the targets are development fixtures; the pre-registered real-target split is
reported alongside every headline and moves the primary metric by 0.02.

The 17 R1 regimes reuse the same 38 interests over 17 gather days, so they are
not 646 independent observations. They are presented as a **curve against corpus
size** and never pooled into a single interval, and the day-to-day spread should
not be read as sampling uncertainty.

## 6. `paired_bootstrap` is used on a level, not a contrast

`harness.stats.paired_bootstrap` exists for paired per-query deltas. Reachability
has no baseline arm to be paired against — pairing needs a relevance measure and
there is none on this corpus — so it is used as a one-sample resample and only
`mean` / `ci_low` / `ci_high` are read. The `wins` / `losses` / `sign_p` fields
of the returned `Paired` are meaningless here and are deliberately not shown in
any table. Noted in `code/analyse.py` at the call site as well.

## 7. Cluster-scoped targets are scored through the flat path

One target (`user:brendondgr`, 5 clusters) would dispatch to `fuse_clusters_pool`
in production rather than `fuse_interests_pool`. Every target here is scored
through the flat surfacing logic instead, for tractability.

This does not affect the finding in §3: `fuse_clusters_pool` applies the
**identical** `best_cosine.get(id, 0.0) >= match_threshold` gate
(`pipeline.py`), so a union-only candidate is dropped on both paths. It does mean
the surfaced *counts* for that one target are the flat path's, not the cluster
path's.

## 8. The store

A development store, not a deployment: 35,205 embedded papers, 2,171 grants, 912
conferences, 818 fellowships, 6 users, freshest gather day 2026-07-20. It was
started for this experiment with `docker compose up -d postgres` and nothing was
written to it — every arm reads.

The absence of judgments is not incidental to this store: 9 saved opportunities,
0 collection items, 0 ignored items and 2 relevance events is the whole of the
behavioural signal, which is why `PROTOCOL.md` §2 rules out a labelled
comparison up front rather than discovering it mid-run.

## 9. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder. No file
under `web/backend/apps/` was modified — the two union pool builders live in
`code/production_pool.py` and call the production functions rather than
replacing them, so nothing in this experiment changes deployed behaviour.

## 10. `code/run.py` was run twice

The first run omitted `entrants_deployed_union_only` — the column that turns §3's
central claim from a deduction into a measurement. It was added and the whole run
repeated (≈6 minutes); every summary metric the two runs share was identical.
The first run's outputs were overwritten rather than kept, since they are a
strict subset of the second's.

**Determinism was then checked directly** rather than inferred: one regime
(`R3:conference:corpus`) was re-run a third time and its 6 per-target and 38
per-interest rows compared field-by-field against the recorded run. All 44 rows
matched exactly. Nothing in the pipeline is seeded because nothing in it is
random — the embedder, pgvector's exact scan, BM25Okapi and the fusion are all
deterministic — so this is the right check to run in place of a seed.
