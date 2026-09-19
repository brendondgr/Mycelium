1. **A smoke run on the 240-person world, before the registered run (not the
   result).** `graph --people 240` (data/sandbox/exp010-smoke240.json): zero
   invariant violations over 138 searches at three scopes, 32 teams and every
   introduction asked; but team cover precision 0.556 on 99 covers, below the
   0.80 bar, and a mean team of 1.3 people for three- or four-method needs —
   one person credited with several methods they do not hold. Every wrong
   cover was a concept-phrase match ("finite element analysis" to "image
   processing", "particle filter" to "pixel-wise segmentation"). Across the
   world's method names, 12.75% of distinct-method pairs reach the lane
   threshold 0.70 and none reach 0.80; same-method names keep 65% at 0.80
   (the linker's aliases, not the matcher, join synonyms). Fixed before the
   registered run by a separate concept threshold,
   `COLLAB_CONCEPT_MATCH_COSINE = 0.80`. The smoke also ran concurrently with
   EXP-2026-09-008's rebuild and broke it at seeding — see that folder.
2. **Run 1 failed H2; run 2 is post hoc.** The registered run
   (`data/exp010-run1.json`, concept threshold 0.80) held every H1 invariant
   but team cover precision was 0.742 (< 0.80). Of the wrong covers sampled
   afterwards on the same database, 13 of 14 were slot-against-sentence
   matches at the sentence threshold 0.70 ("random forest" meeting a sentence
   about a hierarchical Bayesian model); every correct cover in the sample was
   a concept match. Team covers now come from concept matches only (`b0bd4f2`).
   Run 2 repeats the run on the same database copy with the first run's
   search logs and appearances cleared. H2 is judged on run 1 and reported as
   failed; run 2 is the post-hoc check of the fix.
