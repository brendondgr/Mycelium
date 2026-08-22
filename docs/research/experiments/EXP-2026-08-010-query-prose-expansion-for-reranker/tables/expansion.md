*Snapshot `longeval-sci/2025-01`, qrels `test`, 492 queries. Every arm retrieves with `bm25_only` over the **original** query and reranks the same top 50; only the reranker's input text differs. 10,000 paired bootstrap resamples, seed 20260821.*

### Overall

| Arm | nDCG@10 | Δ vs BM25 | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|---:|---:|---|:--:|---|---:|
| bm25_only (baseline) | 0.2486 | — | — | — | — | — |
| xenc, raw query | 0.2047 | -0.0439 | [-0.0597, -0.0283] | **yes** | 139/218/135 | 3.41e-05 |
| xenc, ~8w prose | 0.1696 | -0.0790 | [-0.0980, -0.0606] | **yes** | 118/251/123 | 3.73e-12 |
| xenc, ~16w prose | 0.1611 | -0.0875 | [-0.1067, -0.0683] | **yes** | 110/263/119 | 1.41e-15 |
| xenc, ~20w prose | 0.1564 | -0.0921 | [-0.1113, -0.0728] | **yes** | 112/256/124 | 4.29e-14 |
| xenc, ~40w prose | 0.1547 | -0.0939 | [-0.1133, -0.0742] | **yes** | 110/256/126 | 1.56e-14 |

### Δ vs BM25, split by the length of the **original** query

| Arm | 1 word (n=231) | 2 words (n=181) | 3-4 words (n=48) | 5+ words (n=32) |
|---|---:|---:|---:|---:|
| xenc, raw query | -0.0422 | -0.0401 | -0.0969 | +0.0016 |
| xenc, ~8w prose | -0.0597 | -0.0944 | -0.1437 | -0.0344 |
| xenc, ~16w prose | -0.0689 | -0.1047 | -0.1329 | -0.0566 |
| xenc, ~20w prose | -0.0698 | -0.1065 | -0.1708 | -0.0539 |
| xenc, ~40w prose | -0.0717 | -0.1062 | -0.1800 | -0.0552 |
