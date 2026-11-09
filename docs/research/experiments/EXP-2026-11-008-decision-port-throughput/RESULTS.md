# EXP-2026-11-008 — Results

Every number is read from `data/metrics.json`, written by `code/collect.py` from
the three `decision_check --json` summaries in `data/`.

## 1. Headline

The decide port answered all 144 calls. It does one decision at a time: **7.13
calls/s** with one request in flight and only **8.56** with eight (1.20×),
while median latency rose from 131 ms to 919 ms. The expectation that the GPU
lease serializes calls held.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
| In flight | Calls | Failures | Calls/s | p50 ms | p95 ms |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 48 | 0 | 7.132 | 131.0 | 181.6 |
| 4 | 48 | 0 | 7.993 | 501.8 | 517.2 |
| 8 | 48 | 0 | 8.56 | 918.7 | 940.5 |
<!-- END GENERATED TABLE -->

## 3. Figures

None.

## 4. Interpretation

- For this server, extra concurrency only queues. The nightly rerank's
  `[nightly] rerank_concurrency` (default 12, sized for the hosted Jev API)
  buys nothing against it; 1–2 in flight gives the same throughput with honest
  per-call latencies and timeouts that do not fire on queueing.
- The state here is short (~400 characters). On production-sized states
  (~2,300 characters) `EXP-2026-11-007` measured p50 367 ms per call, about
  2.7 calls/s sequential. A target with 5 themes × 4 content types × 20 window
  pairs (400 pairs) is then about 2.5 minutes before fingerprint reuse.
- Throughput of a llama.cpp or vLLM server behind the same switch is
  unmeasured: none was running on this host, and vLLM in particular batches
  concurrent requests, so its curve should look different.

## 5. Threats to validity

- One synthetic state, repeated: no variation in length, so the numbers are a
  ceiling for short inputs, not the nightly mix.
- GAIFA's GPU queue is shared with GAIFA's other mods; anything else holding the
  GPU during the run would lower these numbers. Nothing was observed, but it was
  not controlled.
- Client-side latency includes HTTP and JSON on localhost.

## 6. What surprised us

Nothing: the expectation held. The only surprise was outside the measured runs:
the very first call after an idle period took about 6 s while the server
reloaded the model, which `decision_check` showed in an unrecorded check.

## 7. Follow-ups

- Q-061: Measure the same sweep against a llama.cpp `llama-server` and a vLLM
  server through the `openai` protocol, at production-sized states, and set
  `rerank_concurrency` per backend from it.

## 8. Reproduction

See `PROTOCOL.md` §Procedure. Needs GAIFA's decide running on
`127.0.0.1:5107`.
