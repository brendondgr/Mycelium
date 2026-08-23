# Issues

- **The harness is structurally blind to this change.** `eval/harness/profiles.py`
  builds `SearchInterest` directly rather than through
  `interests_query.search_interests`, so both arms are expected to be — and are —
  byte-identical before and after. Recorded as a finding rather than a null
  result: it means the recorded profile-arm numbers describe a query construction
  production did not run until this change.
- **n = 1 profile.** One real reader, five themes. The effect sizes below are
  large enough that direction is not in doubt, but the magnitudes are this
  profile's, not a population's.
- **No relevance judgements on the production corpus.** Separation is measured;
  quality is not. See PROTOCOL "What this cannot answer".
- **`code.dirty: true`** at scaffold time — the folder was created after the code
  commit `5fb2fee` but before this file was written. The measured code is
  `5fb2fee`, unmodified during both runs.
- **Fellowships had no before-value for Jaccard.** They carried no per-theme
  slates at all before this change (`_persist_fellowships` never wrote
  `cluster_slates`), which the same commit fixes. Their "before" is therefore
  "absent from every theme section", not a measured overlap.
