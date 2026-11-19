# EXP-2026-11-025 — Issues

- **`code.dirty` at scaffold time** was this folder itself (untracked); the
  change had been committed (`77166b9e`) and each arm ran from a `git archive`
  of its commit. The manifest records `dirty: false`.
- **Protocol time first written wrong.** The protocol said "about 19:40Z"; it
  was written at about 19:12Z, before the first call at 19:13:11Z. Corrected
  before the results were read.
- **The copy carries EXP-2026-11-024's searches.** Each arm deleted the 14
  seekers' search logs and appearances first (14 logs, 21 appearances each
  time), as 024 did; nothing else in the copy changed between 024 and this run.
- **The model's name is a self-report** ("trained by Google"); not stated by the
  maintainer for this run.
