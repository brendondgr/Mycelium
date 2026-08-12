# The Research Record

Every experiment, baseline, ablation, failure, and figure that will ever appear
in a paper is written here, at the time it happens. A result in a chat log, a
commit message, or a notebook cell does not exist.

Read [`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md) before running an
experiment. It is the contract, and `make validate-research` checks it.

## Where to start

| File | What it answers |
|---|---|
| [`INDEX.md`](INDEX.md) | What experiments exist? *(generated — never hand-edit)* |
| [`CLAIMS.md`](CLAIMS.md) | What can we actually claim, and what is still vapour? |
| [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) | What is unresolved, and what is it blocked on? |
| [`DECISIONS.md`](DECISIONS.md) | Why did we choose this metric / collection / baseline? |
| [`RELATED_WORK.md`](RELATED_WORK.md) | Who else has done this, and has anyone scooped us? |
| [`datasets/DATASETS.md`](datasets/DATASETS.md) | What data, what licence, how to get it? |
| [`paper/OUTLINE.md`](paper/OUTLINE.md) | What is the paper, and which venue? |

`CLAIMS.md` is the highest-value file here. Its `unsupported` rows are the
experiment backlog.

## Adding an experiment

```bash
make new-experiment SLUG=cluster-scoping-ablation TITLE="Cluster-scoped vs flat ranking"
```

1. Fill `PROTOCOL.md` **before** running anything. Pre-registering is what
   separates an experiment from a fishing expedition.
2. Run via the entrypoint recorded in `manifest.yaml`.
3. Write the numbers to `data/metrics.json` and `data/metrics.csv`.
4. Fill `RESULTS.md`. Write `figures/make_figures.py` so it reads those files —
   never hardcode a number into a plotting script.
5. `make figures && make research-index && make validate-research`
6. Commit the experiment folder in the same change as any code it depends on.

A finished experiment folder is immutable. Corrections are appended to the
`AMENDMENTS` section of `RESULTS.md` or recorded as a new experiment.

## Commands

| Command | What it does |
|---|---|
| `make new-experiment SLUG=x` | Scaffold from `templates/experiment/`, pre-filling date, commit, branch, and dirty status |
| `make validate-research` | Check every experiment folder and the index |
| `make research-index` | Regenerate `INDEX.md` from the manifests |
| `make figures` | Re-run every `make_figures.py` and re-promote paper figures |
| `make research-ci` | The full check — validation plus index and figure staleness |

Tooling lives in [`../../scripts/research/`](../../scripts/research/) as its own
small `uv` project, so validation stays fast enough for a pre-commit hook.

## What does *not* live here

Raw run outputs. Checkpoints, large CSVs, downloaded corpora, and full logs stay
where they are; the experiment records a path plus a hash in `data/POINTERS.md`.
Nothing above 10 MB enters this directory — the validator enforces it, so that
`docs/research/` stays cloneable in seconds.

For ranking experiments the capture layer already exists: the harness in
[`../../eval/`](../../eval/README.md) writes git SHA, dirty flag, config hash,
corpus size, qrels variant, wall-clock, and embedding model into
`eval/results/*.json` with an `ir-metadata.yml` sidecar on every run. An
experiment folder points at those files and mirrors the numbers.

## Directory layout

```
docs/research/
├── README.md               # this file
├── AGENT_INSTRUCTIONS.md   # the contract
├── INDEX.md                # generated table of every experiment
├── CLAIMS.md               # claim → experiment → figure ledger
├── DECISIONS.md            # dated ADR-style research decisions
├── OPEN_QUESTIONS.md       # unresolved threads and known weaknesses
├── RELATED_WORK.md         # bibliography + scoop watch
├── templates/              # copied by `make new-experiment`
├── experiments/            # the record itself, one directory per experiment
├── figures/                # publication-ready figures only, + their generators
├── tables/                 # publication-ready generated tables
├── datasets/               # provenance, licence, access; one card per dataset
└── paper/                  # outline, venue targets, venue checklists
```
