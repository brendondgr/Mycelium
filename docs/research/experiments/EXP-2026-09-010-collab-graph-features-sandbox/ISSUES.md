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
