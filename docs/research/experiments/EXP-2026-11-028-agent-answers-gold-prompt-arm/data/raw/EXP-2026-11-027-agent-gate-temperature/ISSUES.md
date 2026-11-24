# EXP-2026-11-027 — Issues

- 2026-11-24: the model's quantisation and GPU were not stated by the
  operator for this run; `env/hardware.md` records them as unknown.
- 2026-11-24: this experiment was scaffolded, removed before anything was
  registered or run (the maintainer dropped it), and scaffolded again the
  same day when the maintainer restored it. No measured turn and no smoke
  turn was sent in between; the only model requests were two self-report
  checks (`default-model`, `default-model-2`), which wrote nothing to the
  record.
