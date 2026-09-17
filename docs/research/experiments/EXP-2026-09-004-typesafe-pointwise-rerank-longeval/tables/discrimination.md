# Discrimination — the C-016 measurements on the TypeSafe arms

## `typesafe_noul` over `bm25_only`, window 20, `jev-1.13.0`

| measure | value |
|---|---:|
| pairs answered / failed | 2000 / 0 |
| distinct values per query (mean) | 12.61 |
| adjacent within-window pairs the model ordered | 0.611 |
| mean value by grade | {'0': 0.6615, '1': 0.8656, '2': 0.83} (n {'0': 1686, '1': 138, '2': 176}) |
| monotonic in grade | **no** |
| input tokens / cost at list price | 1,001,263 / $0.0421 |

## `typesafe_score` over `bm25_only`, window 20, `jev-1.13.0`

| measure | value |
|---|---:|
| pairs answered / failed | 2000 / 0 |
| distinct values per query (mean) | 17.38 |
| adjacent within-window pairs the model ordered | 0.862 |
| mean value by grade | {'0': 2.0464, '1': 2.577, '2': 2.4353} (n {'0': 1686, '1': 138, '2': 176}) |
| monotonic in grade | **no** |
| input tokens / cost at list price | 1,065,263 / $0.0447 |

## Agreement between the two framings

Mean top-10 Jaccard, `typesafe_noul` vs `typesafe_score`: **0.805** over 100 queries.

