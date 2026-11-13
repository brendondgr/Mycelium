# Datasets

Provenance, licence, version, and access for every collection a number in this
record was produced from. One card per dataset in [`cards/`](cards/).

A dataset with no row here cannot be used in an experiment: the manifest's
`data.card` field points at a card, and a reviewer's first question is where the
data came from and whether they can have it.

| Dataset | Version used | Licence / access | Redistributable | Card |
|---|---|---|---|---|
| LongEval-Sci (CLEF) | `longeval-sci-2026/snapshot-1/train`, `longeval-sci/2024-11`, `longeval-sci/2025-01` | Open download via `ir-datasets-longeval`; no registration | Yes — by pointing at the package, not by copying | [`cards/longeval-sci.md`](cards/longeval-sci.md) |
| Mycelium paper corpus | rolling, OpenAlex-derived | CC0 (OpenAlex) | Yes | [`cards/mycelium-papers.md`](cards/mycelium-papers.md) |
| Mycelium opportunity corpus | rolling | Public grant and conference listings (open collector) + Illinois Fellowship Finder scrape | Grants and conferences: largely, per source. Fellowship text: **No** | [`cards/mycelium-opportunities.md`](cards/mycelium-opportunities.md) |

## The redistribution problem

Grants and conference CFPs now come from public sources (W10 in
[`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md)), so results resting on them can
be reproduced by re-running the collector. Fellowships still come from the
Illinois Fellowship Finder, one university's website, whose text cannot be
redistributed; a paper resting on fellowships can ship ids, labels and the
collector, not the records.

## Where the bytes live

Downloaded corpora are **outside the git worktree** by design — a gitignored
directory inside a worktree is deleted when the worktree is removed, and
re-downloading LongEval costs ~2.8 GB and hours of embedding. `eval/` reads them
from a cache path configured outside the repository; see
[`eval/README.md`](../../../eval/README.md).
