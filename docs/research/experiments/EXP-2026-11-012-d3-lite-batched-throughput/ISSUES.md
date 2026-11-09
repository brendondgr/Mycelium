# EXP-2026-11-012 — Issues

1. **Dirty tree at scaffold.** Uncommitted files belonged to another session:
   a `docs/changelog.md` line, `docs/plans/mylo-agent/README.md`,
   `docs/plans/mylo-surfaces/`, `docs/research/RELATED_WORK.md` and
   `docs/research/related-work/`. None of them touches the code this
   experiment ran (`apps/core/decisions.py`, `typesafe_rerank.py`,
   `decision_check.py`, all committed at `6b37f03`).
2. **States not committed.** `states.json` and `bodies.json` carry the
   reader's profile text and stay in scratch. `data/bench.json` keeps only
   ids, timings and answer probabilities.
3. **Real-state parity above the bar** (0.035 vs 1e-3), see RESULTS §5. Not
   investigated.
4. **Arm B added after arm A** (PROTOCOL Amendment).
