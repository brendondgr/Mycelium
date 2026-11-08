# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Before run, production pool | `eval/runs/longeval-sci-2026_snapshot-1_train__fusion_dense_pool__pooled__7e5e78390ba31ecd__47a8565.txt.gz` | sha256:c897ed5e064a0c4902bf11b8490c22f9a0bd2175d7c6eba63e2013ad9fb5786c | Hash of the decompressed file (`zcat \| sha256sum`); gzip stores an mtime, so the compressed bytes differ run to run. Gitignored, regenerable. |
| Before run, BM25 | `eval/runs/longeval-sci-2026_snapshot-1_train__bm25_only__full__5f2d1ee62f4661d5__47a8565.txt.gz` | sha256:2966316d8eeda8a138c191ba5f8d94cabb825b5b1a58d20cc1d2f61aad998f3a | As above. |
| Before result, production pool | `eval/results/longeval-sci-2026_snapshot-1_train__fusion_dense_pool__pooled__dctr__7e5e78390ba31ecd__47a8565.json` | sha256:c371121a26cc0140acff260b7ead64198d9eeec169dcb7920d48902837a36865 | R@100 0.5988, nDCG@10 0.2937. |
| Before result, BM25 | `eval/results/longeval-sci-2026_snapshot-1_train__bm25_only__full__dctr__5f2d1ee62f4661d5__47a8565.json` | sha256:233916e353a27005bd1ed8f0f905919eea2f371996fd094b97cb692dc0821b5b | R@100 0.6854, nDCG@10 0.3282. |
| After phase 2 (retrieval extracted), production pool | `eval/runs/longeval-sci-2026_snapshot-1_train__fusion_dense_pool__pooled__7e5e78390ba31ecd__9980298.txt.gz` | sha256:c897ed5e064a0c4902bf11b8490c22f9a0bd2175d7c6eba63e2013ad9fb5786c | Decompressed hash; identical to the before run. Produced from the uncommitted phase-2 tree on top of `9980298` (see ISSUES.md). |
| After phase 2, BM25 | `eval/runs/longeval-sci-2026_snapshot-1_train__bm25_only__full__5f2d1ee62f4661d5__9980298.txt.gz` | sha256:2966316d8eeda8a138c191ba5f8d94cabb825b5b1a58d20cc1d2f61aad998f3a | Identical to the before run. |
| After phase 2 result, production pool | `eval/results/longeval-sci-2026_snapshot-1_train__fusion_dense_pool__pooled__dctr__7e5e78390ba31ecd__9980298.json` | sha256:260b819e33cb9ee7d3406774bde306edc7321c7f63e1ed9e335fec9d047087d3 | R@100 0.5988, nDCG@10 0.2937. |
| After phase 2 result, BM25 | `eval/results/longeval-sci-2026_snapshot-1_train__bm25_only__full__dctr__5f2d1ee62f4661d5__9980298.json` | sha256:c49f661e3f2bcdaad8bf321b1ef37e62c72d594b7ef203812ece9ac2c88bf417 | R@100 0.6854, nDCG@10 0.3282. |
