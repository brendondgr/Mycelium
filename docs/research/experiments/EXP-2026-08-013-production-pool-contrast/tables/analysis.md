### 1. `bm25_reachability@100` — is there anything for a wider pool to reach?

*Of the corpus-wide BM25 top-100 for one declared interest, the fraction already inside the dense pool the deployed builder would have used. `1.0` ⇒ the union pool can add nothing and the C-008 fix is inert; `0.0` ⇒ everything lexically strong is unreachable today. The pre-registered thresholds are **≥ 0.90 inert** and **≤ 0.50 live**.*

| Group | n | median | mean | 95% CI (bootstrap) | p10 | p90 | verdict |
|---|---:|---:|---:|---|---:|---:|:--:|
| all regimes, all targets | 795 | **0.595** | 0.575 | [0.563, 0.587] | 0.33 | 0.78 | between |
| deployed regimes (R1+R3), all targets | 757 | **0.610** | 0.583 | [0.571, 0.595] | 0.33 | 0.78 | between |
| deployed regimes, real targets only | 697 | **0.630** | 0.603 | [0.592, 0.615] | 0.38 | 0.78 | between |
| R1 papers (day-scoped, deployed) | 646 | **0.640** | 0.600 | [0.587, 0.613] | 0.33 | 0.78 | between |
| R3 opportunities (corpus-scoped, deployed) | 111 | **0.440** | 0.482 | [0.455, 0.511] | 0.35 | 0.65 | **live** |
| R2 papers corpus-wide (not deployed) | 38 | **0.490** | 0.427 | [0.389, 0.461] | 0.24 | 0.53 | **live** |

### 2. Reachability against corpus size

*The deficit is arithmetic before it is anything else: a dense pool of 100 per interest covers a small gather batch and cannot cover a corpus. Every row is the same 38 declared interests.*

| Regime | corpus | BM25 reach (median) | FTS-OR reach | emitted after the 0.15 floor |
|---|---:|---:|---:|---:|
| `R1:papers:2026-07-06` | 303 | 0.810 | 0.760 | 100 |
| `R1:papers:2026-07-20` | 313 | 0.780 | 0.820 | 93 |
| `R1:papers:2026-07-13` | 485 | 0.730 | 0.790 | 102 |
| `R1:papers:2026-07-14` | 782 | 0.700 | 0.680 | 109 |
| `R3:fellowship:corpus` | 818 | 0.420 | 0.385 | 98 |
| `R3:conference:corpus` | 912 | 0.605 | 0.680 | 109 |
| `R1:papers:2026-07-19` | 1,254 | 0.590 | 0.535 | 114 |
| `R1:papers:2026-07-07` | 1,311 | 0.720 | 0.645 | 110 |
| `R1:papers:2026-07-18` | 1,348 | 0.665 | 0.630 | 108 |
| `R1:papers:2026-07-11` | 1,504 | 0.585 | 0.585 | 114 |
| `R1:papers:2026-07-17` | 1,737 | 0.740 | 0.715 | 118 |
| `R1:papers:2026-07-08` | 2,065 | 0.685 | 0.555 | 114 |
| `R3:grant:corpus` | 2,171 | 0.430 | 0.500 | 113 |
| `R1:papers:2026-07-10` | 2,810 | 0.665 | 0.650 | 124 |
| `R1:papers:2026-07-16` | 3,033 | 0.650 | 0.520 | 123 |
| `R1:papers:2026-07-12` | 3,079 | 0.660 | 0.655 | 121 |
| `R1:papers:2026-06-30` | 3,219 | 0.550 | 0.510 | 124 |
| `R1:papers:2026-07-01` | 3,574 | 0.640 | 0.535 | 124 |
| `R1:papers:2026-07-03` | 3,913 | 0.560 | 0.420 | 122 |
| `R1:papers:2026-07-05` | 4,475 | 0.510 | 0.460 | 124 |
| `R2:papers:corpus` | 35,205 | 0.490 | 0.430 | 150 |

### 3. Does any of it reach the reader?

*Entrants are documents in the union arm's surfaced list that the deployed arm never surfaced, over all 126 (regime, target) pairs. **Deployed gate** is the code as it stands, where `best_cosine` is populated only by the dense channel. **Completed gate** additionally computes the cosine for union-only candidates, which any real fix must do.*

| Arm | entrants, deployed gate | of which union-only | entrants, completed gate | of which union-only | pairs with ≥1 union-only entrant |
|---|---:|---:|---:|---:|---:|
| A2 union (harness arm) | 22 | **0** | 3,912 | 3,885 | 126/126 |
| A2p union (shippable) | 419 | **0** | 7,866 | 7,440 | 126/126 |
| A3 union via FTS (`websearch`) | 23 | **0** | 358 | 328 | 19/126 |
| A4 union via FTS (OR) | 407 | **0** | 6,100 | 5,686 | 126/126 |

### 4. `Q-018` companion — where the cut actually falls

| Quantity | value |
|---|---:|
| dense pool per target (median) | 170 (min 100, max 403) |
| candidates emitted per interest after the 0.15 floor (median) | 113 (p10 61, p90 128) |
| share of the target's pool surviving one interest's floor (median) | 61% |
| surfaced per target after the cosine threshold (median) | 150 (max 382) |
| (regime, target) pairs hitting the 250 backstop | 3/126 |
| — of which in the deployed paper feed (R1) | 1/102 (median surfaced 148) |
| pool growth, union over dense (median) | 1.54× |
| share of the union pool the dense channel never saw (median) | 35% |

### 5. The Postgres FTS channel `/api/search/` already runs

- `websearch` (production syntax): **728 of 798** (91%) interest queries return **nothing at all**. `websearch` ANDs unquoted terms, and a declared interest carries the profile's shared keyword suffix, so every term has to appear in one document.
- Same index, OR semantics: 4 of 798 return nothing, and median reachability is 0.540.
