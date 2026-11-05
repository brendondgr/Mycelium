# EXP-2026-11-002 — Issues

- **Protocol after a dry run.** The metrics command was run once to check it
  worked before PROTOCOL.md was written; no lab-fit label had been assigned and
  no decision taken. The output of that run was identical to `data/metrics.json`.
- **Judgments are not human.** The lab-fit labels in `data/labfit_labels.csv` are
  the implementing agent's, from each call's description. A person should relabel
  them, over every lab of a real department, before C-029 is cited.
- **Engagement is test activity.** Every reaction in the window was made by the
  implementer in the Discord test server (Phases 4–7). The `remind` and
  `link_click` reaction kinds were added in this phase, so earlier Remind me
  choices and link clicks are not counted.
- **The department posts were partly manual.** Two of its three posts went through
  the smoke script's stand-in for a manager's manual announce (recorded as
  `manual`); the third was recorded as `nightly` by the same script. None came
  from the nightly seed, which correctly held the slate's only department-level
  call (its deadline had passed).
- **Corpus hash unknown**, as in EXP-2026-11-001: the snapshot lives in a local
  database copy. The two data files are hashed in `data/POINTERS.md`.
- `code.dirty: true` at scaffold time: the metrics command and this folder were
  written in the same uncommitted change; both are committed together.
