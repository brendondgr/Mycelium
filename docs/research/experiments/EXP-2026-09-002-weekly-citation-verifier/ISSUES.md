# Issues

- `code.dirty: true` is correct as recorded: the folder was created in the same
  change that shipped the verifier it will measure, so the tree held uncommitted
  work at scaffold time.
- **Not run.** This is a protocol, not a result. It needs 50 hand-labelled
  claims over real weeklies, which needs weeklies to exist in production first;
  `status` stays `planned` until the labelling is done.
- 2026-11-12 (Amendment 1): census, rebuild and injection run. **No human
  labelling sheet was produced**: 64 of 71 weeklies are fallback-written, the 7
  model-written ones report 0 removals, and none of the 7 packets could be
  rebuilt faithfully (the packet is not stored with the weekly). See RESULTS.
- The injection's first launch crashed at the paraphrase step (the raw model
  reply's text is `content`, not `text`) before writing anything; fixed and
  rerun.
- Only 2 kept cited sentences contained a number that could be changed in
  place, so `number_inplace` (n=2) carries no weight.
