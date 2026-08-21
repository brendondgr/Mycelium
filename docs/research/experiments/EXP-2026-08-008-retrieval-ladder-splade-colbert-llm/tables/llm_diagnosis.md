### Did the model follow its input, or judge the content?

| Measurement | Value | Reads as |
|---|---:|---|
| Kendall tau, `llm_rerank` output vs the order it was shown | +0.380 | partial agreement, not copying |
| Kendall tau, `llm_rerank_reversed` output vs the order it was shown | -0.072 | no agreement with its input either |
| Kendall tau, `llm_rubric` output vs the base order | +0.820 | mostly the base, surfacing through ties |
| Mean positions changed inside the 20-item window (`llm_rerank`) | 15.97 / 20 | it reorders aggressively |
| Top-10 overlap, forward vs reversed | 0.72 | 28% of the top 10 is decided by presentation order |

### What the orderings score, against two controls nobody called a model for

| Run | nDCG@10 |
|---|---:|
| copy control — window left untouched (= the base) | 0.3051 |
| copy control — window reversed verbatim | 0.1064 |
| `llm_rerank` (shown best-first) | 0.3177 |
| `llm_rerank_reversed` (shown worst-first) | 0.2561 |
| `llm_rubric` | 0.3095 |

### Per-query record against the base

| Arm | better | worse | tied |
|---|---:|---:|---:|
| `llm_rerank` | 29 | 31 | 40 |
| `llm_rubric` | 17 | 7 | 76 |

### Can the rubric tell relevance apart at all?

| Judged relevance grade | mean rubric score (0-3) | n |
|---|---:|---:|
| 0 | 2.423 | 1689 |
| 1 | 2.818 | 137 |
| 2 | 2.759 | 174 |

Distinct rubric values used per 20-candidate window, on average: **1.99** out of 4 available.

Grade 0 here is *unjudged-or-irrelevant* (1689 pairs); in a pooled collection an unjudged document near the top of a good ranking is often relevant but never assessed, so that bucket understates the model. The grade-1-versus-grade-2 comparison is the clean one, because both are judged.
