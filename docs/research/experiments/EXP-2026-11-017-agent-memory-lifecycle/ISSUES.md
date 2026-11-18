# Issues

## 1. A harness process hung (Amendment 2)

`--tag main2` stopped making progress at 07:18 UTC during
`delete_thread_production` attempt 5: all 40 threads waited on a futex, no
database query was open. Most likely a lock-order problem between the
harness's derive lock and a lock inside a product pass running in the other
worker thread; not diagnosed further (no stack dump available in the
container). The attempt is counted as an error; the remaining work was
restarted in two processes (`main3`, `main4`). Nothing graded was lost: every
finished run had been written to `logs/lifecycle_main2.jsonl`.

## 2. Round one's grader and clarifying questions (Amendment 1)

See Amendment 1: the first process could not grade a clarifying question;
none of its runs ended on one (`ended_on_question` = 0 in `data/metrics.json`).

- 2026-11-16 (round three, Phase 0): quantisation and server version of round two's two models are unknown. The relay's `/v1/models` exposes neither, and by 2026-11-16 `default-model` served a different model (self-reports MiniCPM) while `default-model-2` was marked `failed`, so they could not be read from the model server.

- 2026-11-18 (Amendment 3, Qwen 3.8 27B): **two chat deletions left a pending edge behind** (`delete_thread` attempts 7 and 9 of process `qwen_a`, 20:03:42 and 20:04:12 UTC, in the first three minutes after all five processes started). In each, two pending edges cited the run's two observations before the deletion and one still did after; the observations, findings, digests and the thread were gone, and Mylo recalled nothing. The rows could not be inspected afterwards (the edges are no longer in `mycelium_agent_eval_r2_lifecycle_qwen`). **Cause not established.** The likeliest one: `DERIVE_LOCK` in `code/lifecycle.py` is a `threading.Lock`, so it serialises `evolve` only within one process, while `evolve._edges` is global (it walks every user's findings and calls `record_conversational` with the finding's evidence). With five processes on one database, another process's `evolve` can read a finding before the deletion commits and write its evidence back onto the edge after `drop_evidence` ran. Round two ran at most three processes; this run ran five. The same window exists in the product between the nightly `evolve` and a person deleting a chat. Opened as Q-097. No hang; 0 errors in every probe.
