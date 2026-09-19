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


## Run 2 — post hoc, reader r2 (75b35c9)

H1 0.0081 (1 of 123), H4 model-read 40/40. Two findings:

- The one harmful case was a clarify question answered "It was Project B2, but
  don't worry about it too much for now". The reader picked the project it
  named.
- One decoy tripped the **literal** list: "the sensor might have shut off
  mid-experiment". The pattern `shut (it )?off` was too broad and is now
  `shut (it|them|the questions) off` or `shut off … questions`.
- The two effect mismatches came from the harness: its expectation map treated
  "it's for a project" as confirming the personal edge, when the right effect
  is to reject it. The harness was fixed (a3ac178) and records each mismatch
  from run 3 on.
- A correction that only repeated a choice's label ("mark it down as something
  I'm learning") was being stored as a rename. It is now dropped
  (`_echoes_a_choice`); names of three letters or fewer still count.

## Run 3 — post hoc, reader r3 (2792c59)

Reader r3 adds a rule: "don't bring it up / track it / check in on it, even for
now" is a no. H1 went to 0.0153 (2 of 131), both on the same clarify question
shape. The model-read control tripped on 3 of 40 decoys ("can you stop the
data sync for a second?"), reading them as stop-listening.

Fixed as reader r4 (377fbed):

- naming a choice while saying to drop it, not pursue it, or not track it is a
  no;
- stopping some other thing (a sync, a job, an experiment) is not a setting.

## Run 4 — post hoc, reader r4 (377fbed)

H1 0.0079 (1 of 127): the same clarify shape, "It's Project B2, but don't worry
about it too much for now. Just leave it with me". The shut-off check caught
40/40 with 0/40 decoys tripped. There was one real effect mismatch: "not
really interested right now, so you can stop asking" hit the literal switch
before the answer was read, which muted every question and left this one
open.

Fixed after the run (f2da660): with a question open, a bare "stop asking"
that comes with other words is read as the answer first. It is the switch
only if the reading is unclear or the model is unavailable. "please stop
asking" on its own, and anything naming "questions", is still the switch at
once. Regression tests cover it; no fifth run was made. The next measurement
belongs on a fresh seed (RESULTS §7), so a fifth run on this world would only
add tuning.

The clarify-question harm is left as found. Its effect is attribution to a
named project, not a profile change. Offering buttons only for that question is
the follow-up.
