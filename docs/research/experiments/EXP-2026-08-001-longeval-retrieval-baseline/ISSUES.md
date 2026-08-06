# EXP-2026-08-001 — Issues

## 2026-08-06 — Back-filled record; what could not be recovered

**Impact:** The manifest is honest but incomplete. Do not read a blank field as
"not applicable".

**Not recoverable from the committed run files:**

- **Exact Python patch version.** Recorded as `3.13`. The `ir-metadata` sidecar
  that carries `platform.python_version()` is written to `eval/runs/`, which is
  gitignored and regenerable, so the patch version was not committed alongside
  the results.
- **Per-run config hashes.** `config.hash` records a hash of
  `eval/collections.toml`. Each run file carries its own `config_hash`
  (a 16-hex digest of the arm's resolved parameters) and those are preserved in
  `data/metrics.csv` via the source run files, but there is no single hash over
  `eval/configs/`.
- **Cost.** No dollar figure. Everything ran on an owned CPU host, so there is no
  billing record to recover.
- **Corpus hash.** `data.hash` is null. The collection is pinned by name and
  version through `ir-datasets-longeval`, which is itself pinned in
  `eval/uv.lock`; no independent checksum of the extracted corpus was taken.

**Resolution:** left blank rather than reconstructed. A back-filled experiment
with honest gaps is more useful than one with plausible invented values.

**Paper implication:** state that this experiment predates the record and that
its protocol was reconstructed. The numbers themselves are fully traceable — two
git SHAs, committed run files, deterministic arms.

## 2026-08-06 — Two commits, not one

**Impact:** Rows in the results table carry either `de31887` or `5b66bc2`. They
are not a single run.

**Cause:** the full-corpus dense and fusion arms on the 2026 snapshot were run
first, at `5b66bc2`; the remaining runs at `de31887`. The two commits differ only
in harness plumbing (embedding cache location, and scoping the dirty flag to code
that can change a number), not in ranking logic.

**Resolution:** the SHA is recorded per row and rendered in the generated table.
No row mixes commits.

**Paper implication:** if a table in the paper mixes SHAs, say so in the caption.

## 2026-08-06 — No dirty runs in the final set

**Impact:** none — recorded because its absence is meaningful.

Earlier exploratory runs were produced with a dirty working tree and were
discarded before the committed set; `de31887` also fixed the harness flagging its
own output as a dirty tree. Every committed run carries `dirty: false`. The
generated table still renders a ⚠️ column for dirty runs so a future one cannot
slip through unmarked.
