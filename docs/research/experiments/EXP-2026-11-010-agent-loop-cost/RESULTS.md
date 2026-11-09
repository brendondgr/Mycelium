# EXP-2026-11-010 — Results

## 1. Headline

No result. The run was attempted on 2026-11-09 and the model endpoint answered
502 on the first call (the relay's upstream `skynet` was down), so no latency
or token figure exists yet.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
<!-- END GENERATED TABLE -->

No rows: nothing was measured.

## 3. Figures

None.

## 4. Interpretation

C-030 stays **unsupported**. The plan's gate is therefore open: the agent
ships with the plan's defaults (25 steps, 32k window, 4 000-token result cap)
unmeasured on this host. Rerun this experiment before the web chat UI is put
in front of people.

## 5. Threats to validity

For the rerun: scripted results make the context grow more regularly than real
ones; the model may stop before N calls (reported, not padded); a shared relay
adds queueing latency that a dedicated endpoint would not.

## 6. What surprised us

Nothing yet.

## 7. Follow-ups

Rerun when the endpoint is up (`logs/attempt.json` holds the error).
