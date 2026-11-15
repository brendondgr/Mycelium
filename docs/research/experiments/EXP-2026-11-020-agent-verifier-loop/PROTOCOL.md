# EXP-2026-11-020 — Protocol

Written 2026-11-15, before any run of this experiment; committed with the
harness, the frozen forced-draft sample (`data/forced_sample.jsonl`), the
calibration sheet (`data/sheets/calibration.csv`), the scoring script
(`code/analyse.py`) and the claim rows C-047 to C-049 (plus a C-035 note).
Phase 5 of `docs/plans/20261115-mylo-evaluation-round-two.md`.

## Question

Round one (`EXP-2026-11-013`) measured what Mylo's answer checker
(`tools/agent/verify.py`) *flags*. This measures what the loop then *does*
with a flagged draft (5a), whether the `unread` check fires when a thread
surfaced a reference without reading it (5b, O9), and how often real answers
carry a detail their evidence does not support, as judged by a second model
(5c).

## Hypothesis

- **C-047 (a)** A flagged detail never reaches the final answer: 0 of the
  forced drafts whose injected error the checker flags.
- **C-048 (b)** The repair turns at least half of flagged drafts into an
  answer the checker accepts (repaired) rather than a removal.
- **C-049 (c)** The `unread` check flags at least 18 of 20 surfaced-but-unread
  references, and none of 20 controls where the reference was read.

Prediction from reading the code, written down before the run: (c) will be
**refuted**. `verify.seen_refs` counts a reference as seen when any function
result in view returned it, and a search listing returns its items' numbers;
in a personal thread every earlier turn stays in view. So a reference a search
listed is "seen" and `unread` cannot fire on it. It can fire only once the
result that listed it has left view (cleared or compacted). The exploratory
`cleared` arm checks that it does fire there.

## Setup

- System under test: `tools/agent/loop.py` and `verify.py` at the commit in
  `manifest.yaml` (contains `60ae301`); instance model `default-model` (see
  `env/hardware.md`: identified only by its self-report, which changed since
  round one). `AGENT_PARALLEL_CALLS=0`.
- Demo threads as the demo PI (`demo_visitor="EXP-2026-11-020"`), deleted at
  the end; nothing else is written to the live database.
- Harness hooks, in this process only (`code/harness.py`): a scripted port
  that answers the loop's first model calls and then forwards to the instance
  model; and a wrapper on `dispatch.run` that returns a stored function result
  for a call id starting `replay-`. No product code changes.

## 5a — forced drafts

- **Sample** (`code/sample_drafts.py`, already drawn and committed): from
  round one's injected copies of `rep2` and `rep3` that round one's checker
  flagged, 30 per class: `cite` (invented citation number), `figure`
  (invented figure in running text), `factline` (wrong value on a
  `Label: value` line: amount, date, author or venue). A copy is eligible only
  when its error token is absent from the clean answer and from its evidence.
  Seed `random.Random("20261115:<class>")`. Eligible pools: 220 / 106 / 355.
- **Run** (`code/forced_drafts.py`, 3 in flight): a fresh demo thread asks
  round one's question with its tags; the thread's reference table is set to
  the one the original answer was written with; the loop's first model call is
  answered by one replayed call per stored function result (identical content
  and reference numbers), its second by the corrupted copy. Everything after
  that — the checker's verdict, the repair note, the instance model's repair
  (which may call real functions), the final check and strip — is the
  product's code.
- **Outcome per draft** (`code/analyse.py`), from the first verdict (on the
  forced draft) and the final answer:
  - `not_flagged`: the current checker does not flag the injected error
    (it changed since round one: Amendments 3–4) — reported, outside the
    denominators below;
  - `still_in_final`: the error token is in the final answer (`cite`: the
    invented `#k` appears and resolves to nothing; if `#k` appears but now
    resolves to an item read during the repair it is `rebound`, reported
    separately and not counted as still in);
  - `removed_with_notice`: the final verdict's action is `stripped`;
  - `repaired`: the repair ran and the final verdict is clean (`none`);
  - `other`: anything else (listed).
- Tokens and seconds of the instance model's calls after the draft, per draft.

## 5b — the `unread` check (O9)

`code/unread.py`, fully scripted (no model call), 20 topics from the demo
lab's interests, each as three two-turn threads:

- `surfaced` (the claim's test): turn one runs the real `corpus_search`
  (papers, 5 results) and answers with the listing; turn two's forced draft
  cites `#k` — the first listed paper after the top one that has authors —
  and names its first author in a sentence. Pass: `k` in the first verdict's
  `unread`.
- `read` (control): turn one also runs the real `corpus_item` on `#k`. Pass:
  `k` not in `unread`.
- `cleared` (exploratory, in no claim): as `surfaced`, then turn one's search
  result is marked cleared exactly as compaction marks it before turn two.

## 5c — unsupported details in real answers (second model)

- Input: EXP-2026-11-013 Amendment 5's 100 answers (`fix1`: 50 Mylo, 50 single
  call), each with the evidence file its producer had (`data/sheets_fix1/`).
- Reader: the second model (`default-model-2` on the same relay; a different
  family by its self-report), temperature 0, fixed prompt in `code/reader.py`,
  one retry on an unparseable reply. It lists every stated detail with where
  it sits (`sentence`, `fact_line`, `figure`, `claim`) and whether the
  evidence supports it. The reader never sees the arm.
- Checker on the same text and evidence: `verify.unsupported` and citation
  numbers that match nothing. A reader-unsupported detail counts as flagged
  when a checker snippet contains it or is contained in it (folded), or they
  share a number of two or more characters.
- Reported per arm: unsupported details per answer (mean), answers with at
  least one (Wilson), and by kind; the checker's model-judged recall (flagged
  / reader-unsupported). Mylo's final answers already passed the checker, so
  every unsupported detail left in them is a miss by construction; the single
  call's answers were never checked and give the unbiased recall estimate.
  These numbers are **model-judged** and are labelled so wherever they appear.
- Calibration: `data/sheets/calibration.csv`, 30 of the 100 answer ids drawn
  with `random.Random(20261115)` from the sorted ids, for one person to mark
  the same way (`CALIBRATION_INSTRUCTIONS.md`). Agreement (any-unsupported
  yes/no, Cohen's κ) is computed by `analyse.py` when it is filled; until then
  5c is "not checked by a person".

## Decision rules (fixed now)

- **C-047** supported if `still_in_final` is 0 across all flagged drafts
  (one-sided exact 95% upper bound reported); refuted by any one.
- **C-048** supported if `repaired / flagged` ≥ 0.5 over all three classes
  pooled (Wilson interval and per class reported).
- **C-049** supported if `surfaced` flags `k` in ≥ 18 of 20 valid runs **and**
  `read` flags it in 0 of 20; refuted otherwise. A run with a harness error is
  rerun once; if it fails again the claim is reported on the valid runs and
  marked partial.
- **C-035**: 5c adds a model-judged recall figure to its recall half; its
  status does not change on model judgement alone.

## Procedure

```bash
R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp -e AGENT_PARALLEL_CALLS=0 -v $PWD/docs/research:/app/docs/research backend uv run --no-sync --project web/backend python"
E=docs/research/experiments/EXP-2026-11-020-agent-verifier-loop
python3 $E/code/sample_drafts.py              # done before this protocol was committed
python3 $E/code/reader.py --sheet-only        # calibration sheet, done before commit
$R $E/code/unread.py                          # 5b, no model
$R $E/code/forced_drafts.py --conc 3          # 5a
export EVAL2_LLM_API_KEY=…                    # the instance's LLM_API_KEY, never written down
$R -e EVAL2_LLM_BASE_URL=http://llm-tunnel:9090/v1 -e EVAL2_LLM_MODEL=default-model-2 -e EVAL2_LLM_API_KEY \
   $E/code/reader.py --conc 3                 # 5c
python3 $E/code/analyse.py
python3 $E/figures/make_figures.py
```

## What would falsify this

Any flagged injected error in a final answer refutes C-047. Fewer than half
of flagged drafts repaired refutes C-048. Fewer than 18 of 20 surfaced
references flagged, or any control flagged, refutes C-049.

## What it cannot show

5a's drafts are rule-built errors on round one's answers, not errors the
model made; the repair is the real model's. 5c is one model's judgement of
another's answers, not people's. One fictional lab, one instance model.
