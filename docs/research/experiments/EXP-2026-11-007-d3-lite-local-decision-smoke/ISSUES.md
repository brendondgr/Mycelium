# EXP-2026-11-007 — Issues

1. **Dirty tree.** At run time the working tree held another session's
   uncommitted edits to `docs/changelog.md`, `docs/research/RELATED_WORK.md`
   and `docs/research/related-work/`. None of them is read by this experiment's
   code.
2. **GPU not verified.** The Decisions server reports `device: cuda`,
   `bfloat16`, 6.7 GB. This host has an AMD Radeon 8060S integrated GPU and no
   `nvidia-smi`, so "cuda" is presumably a ROCm build of PyTorch; not checked.
   The server is a separate process not in this repository; its code and
   version are unknown beyond the model revision it reports.
3. **No paired Jev baseline.** The local store holds no `signals["typesafe"]`
   rows, so the production judgements could not be compared on identical
   states, and Jev was deliberately not re-billed for a smoke test.
4. **Profile text kept out.** `states.json` (with the reader's profile) lives
   in a scratch directory; `data/pairs.json` keeps its SHA-256 and length.
