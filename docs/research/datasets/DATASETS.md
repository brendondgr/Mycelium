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
| Mycelium opportunity corpus | rolling | Pivot-RP (Clarivate, institutional SSO) + Illinois Fellowship Finder scrape | **No** | [`cards/mycelium-opportunities.md`](cards/mycelium-opportunities.md) |

## The redistribution problem

The opportunity corpus is the one that blocks artifact evaluation. Pivot-RP is a
commercial Clarivate product behind institutional SSO and the Illinois Fellowship
Finder is one university's website; neither can be redistributed, and no
experiment resting on them can be independently reproduced.

The route out is known and is tracked as W10 in
[`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md): rebuild the corpus from CORDIS,
NIH RePORTER, NSF Awards, and public university listings. It costs the Pivot
conference CFPs, which have no open equivalent. Any paper resting on grants or
fellowships needs this done first.

## Where the bytes live

Downloaded corpora are **outside the git worktree** by design — a gitignored
directory inside a worktree is deleted when the worktree is removed, and
re-downloading LongEval costs ~2.8 GB and hours of embedding. `eval/` reads them
from a cache path configured outside the repository; see
[`eval/README.md`](../../../eval/README.md).
