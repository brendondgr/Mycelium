# EXP-2026-11-020 — Issues

- 2026-11-15, **defect, predicted before the run and confirmed by 5b (Q-076).**
  The `unread` check cannot fire on a reference that a search listed while the
  listing is still in view: `verify.seen_refs` counts every reference number a
  visible function result returned as seen, and `corpus_search` returns the
  numbers of what it lists. In a personal thread every earlier turn stays in
  view, so "surfaced but never read" is "seen" by the code's definition. 0 of
  20 surfaced references were flagged; 20 of 20 were flagged once the listing
  was marked cleared (the exploratory `cleared` arm). Not fixed (plan rule).
- 2026-11-15, **observed in 5b's exploratory arm, not counted in any claim
  (Q-077).** When `unread` does fire, the loop asks for one repair and, if the
  repair repeats the citation, posts the answer with the unread citation and
  its detail still in it: the final pass strips `unmatched` citations and
  `unsupported` claims but never `unread` ones (round one's protocol predicted
  this from the code). In 5b the repair was scripted to repeat the draft, so
  this shows the mechanism, not how often a real model leaves the citation in.
- The forced drafts of 5a were made by rule on round one's answers by round
  one's model (recorded as Qwen 3.8 27B); tonight's instance model, which
  writes the repairs, self-reports as a different (Google-trained) model. The
  replayed evidence is identical; the model reading it is not.
- The current checker changed after round one flagged these copies
  (EXP-2026-11-013 Amendments 3–4), so a sampled copy can be `not_flagged`
  in the replay; those are reported and left out of the C-047/C-048
  denominators, as the protocol fixed.
- 2026-11-15, **5c reader truncation (Amendment 1).** The reader is a
  reasoning model and its reasoning counts against `max_tokens`; at the
  pre-registered 6,000, 48 of 100 replies were cut before the JSON list closed
  (the identical retry was cut too). Re-read at 16,000: 46 parsed, 2 still
  failed. Both gradings are reported.
- The relay's response names the model `default-model` even when
  `default-model-2` was requested (the reply's own text
  says it is Qwen, Alibaba). Which upstream served the reader therefore rests
  on the request and the self-report, not on the response field.
- **5c reader noise.** The reader counts evaluative statements ("the best
  fit is …") and words echoed from the question ("three papers", "PhD
  student") as stated details; its unsupported counts are an upper bound on
  factual errors. Nobody has filled `data/sheets/calibration.csv`, so its
  agreement with a person is unknown (Q-081).
- 5a: in figure-03 the repair called `projects_get(project_id=…)` (wrong
  argument name), then answered that it could not retrieve the project. The
  replayed calls showed the model `{"replay": i}` as their arguments; this may
  have contributed. Counted as `repaired` by the pre-registered rule (the
  checker accepted the final answer).
- Threads: 150 demo threads (90 in 5a, 60 in 5b) were deleted at 07:10 UTC by
  `EXP-2026-11-018/code/cleanup.py`; audit rows counted there.

- 2026-11-16 (round three, Phase 0): quantisation and server version of round two's two models are unknown. The relay's `/v1/models` exposes neither, and by 2026-11-16 `default-model` served a different model (self-reports MiniCPM) while `default-model-2` was marked `failed`, so they could not be read from the model server.
