# Agent Instructions — the research record

The contract every agent and every human follows when producing a number in this
repository. If an instruction elsewhere conflicts with a principle below, the
principle wins.

## Principles

1. **One canonical location.** `docs/research/` is the only place a research
   finding lives. A result in a chat log, a commit message, a notebook cell, or
   a Discord thread does not exist.
2. **The unit of record is the experiment, not the file.** An experiment is a
   directory with a fixed internal contract, not a markdown file dropped into a
   pile.
3. **Every number in the paper traces to an experiment ID.** No orphan numbers.
   A claim with no traceable experiment is a claim that gets cut.
4. **Figures are generated, never hand-placed.** If one command cannot rebuild
   a figure from recorded results, it does not go in the paper.
5. **Failures are recorded with equal weight.** Negative results, crashed runs,
   and abandoned directions are first-class entries.
6. **Record at write-time, not at paper-time.** The pipeline writes the record;
   the human reviews it. Anything depending on human diligence at the end will
   not happen.
7. **Append-only for completed experiments.** A finished experiment folder is
   immutable. Corrections go in a new experiment or the `AMENDMENTS` section of
   `RESULTS.md`, never a silent edit.

## Rules for agents

- Any experiment, benchmark, baseline, ablation, or evaluation run **must** be
  recorded under `docs/research/experiments/`.
- Never report a metric in chat or a commit message without also writing it to
  the experiment's `manifest.yaml` and `RESULTS.md`.
- Never hand-edit a figure. Never hardcode a number in a plotting script — the
  script reads `data/metrics.json` or `data/metrics.csv`.
- Failed and abandoned runs are recorded, not deleted.
- If asked to "just quickly check" a number, still create the experiment folder.
- **Do not fabricate a manifest field.** `unknown` plus an `ISSUES.md` line is
  correct; a plausible invented value is not.
- Commit the experiment folder in the same change as the code it depends on.

## Adding an experiment

```bash
make new-experiment SLUG=cluster-scoping-ablation TITLE="Cluster-scoped vs flat ranking"
```

1. Fill `PROTOCOL.md` **before** running anything.
2. Run via the entrypoint recorded in `code.entrypoint`.
3. Write metrics to `data/metrics.json` and `data/metrics.csv`.
4. Fill `RESULTS.md`; write `figures/make_figures.py` so it reads those files.
5. `make figures && make research-index && make validate-research`.
6. Commit.

## The directory contract

```
EXP-<YYYY>-<MM>-<NNN>-<kebab-slug>/
├── manifest.yaml     # REQUIRED — machine-readable, schema-validated
├── PROTOCOL.md       # REQUIRED — written BEFORE the run
├── RESULTS.md        # REQUIRED — written after
├── figures/          # REQUIRED if any figure exists; .svg + .pdf + make_figures.py
├── tables/           # generated .md / .tex fragments
├── data/             # metrics.json, metrics.csv, POINTERS.md (path + hash)
├── env/              # lockfile pointer, hardware.md
├── logs/             # trimmed logs, or pointers
└── ISSUES.md         # bugs, anomalies, aborted runs, gotchas
```

The ID is permanent. It is the only handle used in code comments, figure
filenames, commit messages, ledger rows, and paper drafts.

**Large artifacts do not live here.** Nothing above 10 MB enters
`docs/research/` — the validator enforces it. Checkpoints, raw logs, and large
corpora stay where they are (`eval/results/`, `data/`, or object storage) and the
experiment records a path plus a hash in `data/POINTERS.md`.

## What the validator enforces

`make validate-research` fails on: a missing required file; a manifest that
fails schema validation; `status: complete` with empty `metrics.values`; a
figure listed but absent or present but unlisted; a figure with no generating
script; a `data/POINTERS.md` row with no hash; a claim ID absent from
`CLAIMS.md`; and a stale `INDEX.md`. Nothing runs it automatically — run it
yourself before finishing a change to the record.

## The ledgers

| File | What it holds | Edited by |
|---|---|---|
| `INDEX.md` | Every experiment, generated from the manifests | the generator only |
| `CLAIMS.md` | Every claim the paper will make, and its evidence status | hand |
| `DECISIONS.md` | Dated ADR-style record of research decisions | hand, append-only |
| `OPEN_QUESTIONS.md` | Follow-ups from every `RESULTS.md`, and known weaknesses | hand |
| `RELATED_WORK.md` | Running bibliography and scoop watch | hand |

Write claims into `CLAIMS.md` **before** they are supported and mark them
`unsupported`. That table is the experiment backlog, and it is the highest-value
artifact in this directory.

## Repository-specific notes

- The retrieval harness in [`eval/`](../../eval/README.md) is the capture layer
  for ranking experiments: it already records git SHA, dirty flag, config hash,
  corpus size, qrels variant, wall-clock, and embedding model into
  `eval/results/*.json` and an `ir-metadata.yml` sidecar. An experiment folder
  points at those run files and mirrors the numbers; it does not copy the corpus.
- [`docs/evaluation.md`](../evaluation.md) remains the operator's guide to
  running the harness and the standing claims boundary. The numbers themselves
  live in the experiment folders.
- The re-run rule in [`docs/skills/global.md`](../skills/global.md) stands: a
  change to `tools/retrieval/index.py`, `tools/retrieval/lexical.py`, `fusion.py`, `ranking.py`, or
  `pipeline.py`'s pool construction needs a fresh run — and now a fresh
  experiment folder.
