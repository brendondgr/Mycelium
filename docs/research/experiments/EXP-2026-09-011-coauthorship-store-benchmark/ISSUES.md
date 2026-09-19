# EXP-2026-09-011 — Issues

1. **Arm A ran with other work on the machine.** The pre-registered run
   (1,000 / 5,000 / 20,000 people) shared the host with a full backend test
   suite (single process) and the sandbox world build (mostly waiting on the
   model); load average was about 2 on 20 cores. Latencies are therefore
   slightly pessimistic, for both stores equally.
2. **Arm B (hubs) is exploratory and declared after arm A.** Arm A's graphs
   top out at degree ~30, while real co-authorship has prolific authors with
   hundreds of links. Arm B adds 1% hub people with 100–400 extra links each at
   20,000 people. Not pre-registered; reported as exploratory.
3. **Arm B's first attempt was abandoned for running over time (recorded).**
   Started 2026-09-18 ~21:00 with 300 pairs and no per-query limit, it was
   stopped after 1 h 48 min on the owner's instruction that no experiment run
   longer than an hour. Postgres had finished; Neo4j's natural "shortest path
   to everyone within three hops" query (`ANY SHORTEST … {1,3}`) was taking
   about 15 s per call from hub-adjacent people, and its introduction query
   was planned as an exhaustive shortest-path search. No numbers were kept
   (the harness wrote results only at the end). Rerun with 100 pairs, a 5 s
   server-side timeout per Neo4j query (a timed-out query counts at 5 s and
   is reported as a miss), and a 45-minute wall-clock budget.
4. **Dirty tree.** Arm A ran from `store_bench.py` before it was committed
   (committed unchanged in `4acede2`); arm B ran after the per-query timeout,
   budget and hub cap were added (committed with this record). The hub cap only
   bounds the sample size at small n and leaves every draw at 20,000
   unchanged, so arm A's graphs are reproduced exactly by the committed code.
