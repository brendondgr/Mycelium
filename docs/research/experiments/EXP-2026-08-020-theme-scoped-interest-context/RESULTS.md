# Results — theme-scoped interest context

**Status:** complete. **Verdict:** the acceptance test passes in all four
categories. Five themes now produce five distinct leads where they previously
produced one, and slate overlap collapses by an order of magnitude.

## Primary — production, one real profile, five themes

| Category | Pool | Distinct items across 5 slates | Mean pairwise Jaccard | In *every* slate | Distinct rank-1 items |
| --- | ---: | ---: | ---: | ---: | ---: |
| Papers | 119 → **162** | 31 → **70** | 0.75 → **0.20** | 55% → **0%** | 1 → **5** |
| Grants | 161 → **311** | 15 → **44** | 0.69 → **0.04** | 47% → **0%** | 1 → **5** |
| Conferences | 145 → **307** | 12 → **45** | 0.87 → **0.03** | 75% → **0%** | 1 → **5** |
| Fellowships | 182 → **319** | — → **21** | — → **0.04** | — → **0%** | — → **5** |

Every prediction in the protocol held, including the secondary one: the candidate
pool roughly doubles on the three opportunity categories, because five different
questions retrieve five different sets where one repeated question did not.

Fellowships have no before-column because they carried no per-theme slates at all
until the same commit added them — their "before" is absence from every theme
section, not a measured overlap.

### The qualitative read

Not a measurement, and recorded as such — but the leads changed from one venue
five times to five venues that belong where they sit:

| Theme | Conference now leading |
| --- | --- |
| Knowledge Graphs & Retrieval | The Second Workshop on Generative Information Retrieval |
| Agentic AI & Orchestration | 2nd Workshop on Agentic AI Benchmarks and Applications |
| AI for Healthcare & Biomedicine | AI Agents for Biomedical Imaging and Multimodal Clinical … |
| Computer Vision & Sensing | Indian Conference on Computer Vision, Graphics & Image P… |
| Robotics & Emerging Tech | The Evolving Landscape of Surgical Robotics: Surgical Au… |

## Secondary — the LongEval harness

`clustered_profile` and `slate_profile` at the same config hashes:
**byte-identical**, before and after (nDCG@10 0.1752, R@100 0.2521 on both).

This is not a null result, it is a structural fact:
`eval/harness/profiles.py` builds `SearchInterest` objects directly, with
`query_text = label`, and has never called `interests_query.search_interests`.
The harness therefore *cannot* observe this change — and, read the other way,
**every profile-arm number in this record was measured on bare per-area queries
that production did not run**. Production has been on the 473-character-suffix
configuration the whole time. This change moves production toward what the
harness has always measured, which is the first time those two have agreed.

## Interpretation

The redesign's per-theme slates were doing their job all along; they were being
fed a degenerate ranking. Both facts are worth keeping separate:

1. The per-theme machinery was correct — the five slate *orders* already differed
   from position 2 onward before this change. Only position 1 collapsed.
2. The collapse came from query construction, two layers upstream, in code the
   redesign plan explicitly declared healthy and out of scope ("Retrieve → fuse
   per interest → combine within cluster. Unchanged. This part of the system is
   healthy."). It was not.

The lesson generalises past this fix: a scale-free per-theme ranking cannot
rescue themes that are all asking the same question, and nothing downstream of
retrieval can detect that they are.

## Threats to validity

1. **n = 1 profile.** Effect sizes are this reader's. Direction is not in doubt at
   these magnitudes; magnitude is not transferable.
2. **No relevance judgements.** Separation is measured, quality is not. The
   category-appropriate leads above are a coherence argument.
3. **The cap is untuned.** `INTEREST_CONTEXT_TERMS = 3` was chosen to be small
   enough that a six-area theme cannot rebuild the old suffix, not by measurement.
   0 (bare areas, the harness configuration) is untested in production.
4. **Absolute cosines fell.** A one-token query scores a three-token document at
   1/sqrt(3) where the padded query scored it higher, so fixed thresholds bite
   harder. Three test fixtures needed their thresholds lowered from 0.6 to 0.5 for
   exactly this reason. **The deployed `*_MATCH_THRESHOLD` settings were not
   retuned** and may now be admitting less than intended — that is the most likely
   place for this change to have caused unintended harm, and it is unmeasured.

## What would change the verdict

A second and third profile, ideally one whose themes genuinely overlap (where
some duplication is *correct*) and one with a single theme (where the change
should be a no-op). And a threshold sweep against the new cosine distribution,
which threat 4 makes the first follow-up worth running.
