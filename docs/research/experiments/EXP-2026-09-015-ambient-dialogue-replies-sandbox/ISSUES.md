# EXP-2026-09-015 — Issues

## Run 1 — registered: H1 fails (stop condition), H4 fails

Worktree `60fd1c3`, 07:30–07:40 UTC, 16 workers. 44 questions (32 interest,
11 skill, 1 clarify), 220 replies, none unread. **H1 fails: 32 of 133
no / not-now / ambiguous / off-topic replies read as a yes (0.24).** H2 fails
(overall 0.51; no 0.17; ambiguous read as unclear 0.0). H3: 1 effect mismatch
of 30. **H4 fails: the literal list caught 0 of 40 requests to stop asking**
("could you chill with the questions", "you can skip the personal
questions") and tripped on 0 of 40 decoys. H5 holds.

Reading the 40 saved examples, two different things are mixed in H1:

1. **The truth, not the reader.** Most "off-topic" replies the model wrote
   opened with an answer — "yeah, sounds good. also did you see the email about
   the lab meeting?" — and reading that as a yes is right. Most "ambiguous"
   replies ("not sure yet, let me look into it") were read as *not now*, which
   changes nothing and is not harm. The harness's writer prompt did not forbid
   answering.
2. **The reader, for real.** The reader accepted the model's own verdict
   alongside its choice, so a model saying "confirmed" while picking "no"
   could turn a no into a yes; and the literal shut-off list is no match for
   how people say it.

The stop condition in PROTOCOL.md applies: until fixed, free-text yeses would
have to be refused. **Fixed before any use** (commit after this note):

- the reader (`READ_VERSION` r2) asks only *which choice*, with rules for soft
  noes, not-now and unclear, and derives the verdict from the choice; and
  `dialogue.answer` records the chosen option's verdict whatever a caller
  passes, so no path can record a chosen no as a yes;
- a model-read control intent (`read_control`) for requests in the person's own
  words, called only for messages with a word such a request would use, and
  only when the message is not answering a question (or the answer read as
  unclear); the literal list still answers first, and no longer fires on
  "stop asking about it", which answers one question;
- regression tests for each.

**Run 2 (post hoc)** reruns with the fixed reader, and with the harness's writer
told plainly that off-topic and undecided replies must not answer; every row is
saved; a keyword screen reports replies whose own words still contradict their
intent, and the harm rate is reported with and without them.
