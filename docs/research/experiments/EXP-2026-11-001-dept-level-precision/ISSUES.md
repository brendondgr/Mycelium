# EXP-2026-11-001 — Issues

- **Judgments are not human.** Every label was assigned by the implementing
  agent (Claude) against the rubric in PROTOCOL.md. A person should relabel
  `data/labels.csv` before C-028 is cited outside this repository.
- **v2 is measured on the sample that motivated it.** Removing the five rules
  that produced the wrong rows makes v2 perfect on these rows by construction.
  The honest figure for an unseen corpus is closer to v1 for the kept rules'
  neighbours; re-measure on the next corpus snapshot (open question).
- **Recall is not measured.** No negatives were labelled, so calls the detector
  misses (for example limited-submission language phrased differently) are
  invisible here. Removing `no_more_than` cost one correct row (the CTSA hub
  limit).
- **R25 is borderline.** R25 research-education awards are labelled correct
  under the rubric (an institutional training programme), but some R25 short
  courses could be run by one investigator's group. Three such rows are noted.
- **Corpus hash unknown.** The snapshot lives in a local database copy, not a
  file; its hash was not taken. The labelled rows themselves are hashed in
  `data/POINTERS.md`.
- `code.dirty: true` at scaffold time: the detector and this folder were being
  written in the same uncommitted change; both are committed together.
