# Dataset card — LongEval-Sci (CLEF)

## Identity

| Field | Value |
|---|---|
| Name | LongEval-Sci, CLEF LongEval Task 1 (ad-hoc scientific retrieval) |
| Source | CORE open-access publications |
| Access | `pip install ir-datasets-longeval` — open download, no registration |
| Snapshots used | `longeval-sci-2026/snapshot-1/train`, `longeval-sci/2024-11`, `longeval-sci/2025-01` |
| Download size | ~2.8 GB compressed → ~11 GB extracted (registration pulls all three 2026 snapshots) |

## Composition

| Snapshot | Documents | Queries | Judgments |
|---|---:|---:|---|
| `longeval-sci-2026/snapshot-1/train` | 869,902 | 100 | 8,772 (`dctr`) |
| `longeval-sci/2024-11` | 2,014,265 | 99 | `test` |
| `longeval-sci/2025-01` | 1,213,728 | 492 | `test` |

Documents are paper titles plus abstracts, mean 1,610 characters. Queries are
short keyword topics.

## Judgments — read this before quoting a number

LongEval-Sci ships **click-model-derived pseudo-relevance judgments**, not
TREC-grade human assessment. Two variants exist for the training snapshot and
they are not interchangeable:

- `dctr` — Dynamic Bayesian / DCTR click model. 8,772 judgments. The default.
- `raw` — raw click-derived judgments, a much smaller set.

The variant is recorded on every result row and in every manifest, and it must
appear next to every number reported anywhere. Size your confidence to it. See
[`../../DECISIONS.md`](../../DECISIONS.md) D-002.

## Why this collection

It is the only openly downloadable scholarly collection with **temporal
snapshots** and per-snapshot judgments, which makes persistence — whether
effectiveness decays as a corpus grows — measurable at all. It also ships
published BM25 and Qwen3-Embedding-4B baselines, so the comparison costs nothing
extra. Rationale in full: [`../../DECISIONS.md`](../../DECISIONS.md) D-001.

## Limitations for our purposes

**The task does not match the product.** LongEval evaluates *query → documents*.
Mycelium does *declared-interest profile → feed*. The granularity mismatch
between a three-word declared interest and a 200-word abstract is one of the core
difficulties of the real problem and is not tested here. Nothing measured on this
collection licenses a claim about personalization, cluster max-pooling, LLM
scoring, eligibility, or member routing.

## Availability of the 2026 test snapshots

Three 2026 *test* snapshots ship documents and queries but no qrels — CLEF 2026
is an active shared task and the organizers withhold judgments until it closes.
Run files can already be produced for a TIRA submission; only scoring is blocked.
This is a **data-availability block, not a design limitation**:
`eval/collections.toml` already declares them, and enabling them is a config edit
(flip `scoreable`, name the qrels variants), never a code change.

## Citation

CLEF LongEval Lab, Task 1 (LongEval-Sci). Cite the lab overview paper for the
year of the snapshot used, and cite the organizers' baseline runs when quoting
the BM25 or Qwen3-Embedding-4B numbers in `EXP-2026-08-001`.
