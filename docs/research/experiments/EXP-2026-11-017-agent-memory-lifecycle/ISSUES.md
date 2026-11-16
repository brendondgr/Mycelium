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
