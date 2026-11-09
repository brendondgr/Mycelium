# EXP-2026-11-008 — Protocol

Written before the run, on 2026-11-09.

## Question

Through Mycelium's own decision client (`apps/core/decisions.py`, the
`[decision] backend = "port"` path), how many decisions per second does the
local decide server on this host sustain, and does sending requests
concurrently raise that number?

A capacity measurement for planning the nightly rerank, not a quality one.

## Hypothesis

Exploratory. One expectation, stated in advance: GAIFA's decide mod takes a
lease from GAIFA's GPU queue around every model call, so concurrency above 1
should raise latency, not throughput.

## Setup

- **Client:** `manage.py decision_check` on the host (the backend container
  cannot reach the host's `127.0.0.1`), working tree as committed with this
  folder. One fixed hand-written state (no database content), two questions per
  call: a yes/no and a four-level score, the shapes the slate rerank asks.
- **Server:** GAIFA `decide` at `http://127.0.0.1:5107`, protocol detected as
  `decide`, model `d3-lite` revision `03560c26f5199c3c04129a2ccb38960c913635e0`.
- **Warm-up:** one call first, so a model reload after an idle unload does not
  count.

## Data

None: a fixed synthetic state. No judgements, no profile text.

## Metrics

- **Throughput (primary):** successful calls ÷ wall seconds, per concurrency
  level.
- **Latency:** client-side p50 / p95 / max per call, ms.
- **Failures:** calls that raised.

## Baselines

Concurrency 1 is the baseline for 4 and 8.

## Procedure

```bash
export UV_PROJECT_ENVIRONMENT=$HOME/.cache/mycelium-backend-venv
D=docs/research/experiments/EXP-2026-11-008-decision-port-throughput
M="uv run --no-sync --project web/backend python web/backend/manage.py decision_check --url http://127.0.0.1:5107"
$M --calls 1                                   # warm-up, not recorded
for c in 1 4 8; do $M --calls 48 --concurrency $c --json $D/data/run_c$c.json; done
python3 $D/code/collect.py
```

## What would falsify this

- Any failed call → the port path is not reliable enough to measure.
- Throughput at concurrency 8 more than 1.5× concurrency 1 would refute the
  "GPU lease serializes it" expectation (good news, not a problem).
