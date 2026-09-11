# Protocol — Does the citation verifier agree with a person?

Written before the run. Nothing below has been executed.

## The question

The weekly report removes model-written sentences that fail three deterministic
checks (`apps/content/weekly_verify.py`): an unresolved `[P#]`, a number or date
the evidence packet does not contain, and — when a caller supplies one — an
entailment judgement.

Removing a sentence is a strong action. It is the right one, because a sentence
that is confidently wrong about a project's own research is wrong in the reader's
own domain and takes the surrounding correct sentences down with it. But the
checks have never been measured, and there are two ways they can be wrong:

- **Over-removal.** A correct, supported sentence removed because its phrasing
  tripped a rule. The reader sees a report with holes in it and no explanation.
- **Under-removal.** An unsupported sentence kept because the rules do not cover
  the way it was wrong. This is the failure the whole mechanism exists to
  prevent.

**How often does each happen, and does adding the entailment check help enough
to justify a model call per report?**

## The measure

Against hand labels on a sample of weekly sentences:

- **Removal precision** — of the sentences the verifier removed, the share a
  person also judges unsupported by the packet.
- **Removal recall** — of the sentences a person judges unsupported, the share
  the verifier removed.
- **Agreement** — Cohen's κ between the verifier's keep/remove and the labeller's.

Reported for the deterministic checks alone, and again with an entailment check
added, so the entailment call's marginal value is visible rather than assumed.

## Method

1. **Sample.** 50 hand-labelled claims, per open decision OD4. Drawn from real
   weeklies across at least five projects, stratified so at least fifteen are
   sentences the deterministic checks already remove — otherwise the sample is
   almost all easy keeps and the precision number is uninformative.
2. **Label.** For each sentence, the labeller sees the sentence and the **packet
   only** — never the source paper — and answers one question: *does the packet
   support this sentence?* That is deliberately the verifier's own question, and
   not "is this sentence true": the verifier cannot be blamed for a packet that
   omits something, and measuring it against the world rather than against its
   input would conflate two separate failures.
3. **Blind.** The labeller does not see the verifier's verdict. Labels are
   recorded before any comparison is computed.
4. **Compare.** Deterministic-only, then with entailment, against the labels.

## The bar, stated before the numbers exist

- **Removal precision ≥ 0.9.** Removing a supported sentence one time in ten is
  the most this can cost and stay worth doing; the reader sees the hole and has
  no way to tell it was an error.
- **Removal recall ≥ 0.7** for the deterministic checks. Below that, the checks
  are decorative and the entailment call has to carry the mechanism.
- The entailment check is adopted **only** if it raises recall by ≥ 0.1 without
  dropping precision below 0.9. A model call per report that moves neither is a
  cost with no product behind it, and the local-NLI alternative (OD4) is then
  what to scope.

## What would make this wrong

- **One labeller.** κ against a single person measures agreement with that
  person. If the decision is close, a second labeller on the same 50 is the next
  step, not a larger single-labelled sample.
- **Sampling from a fallback-heavy period.** A weekly written by the
  deterministic fallback has no model-written sentences to check, so those
  reports contribute nothing and must not be counted toward the 50.
- **The packet-only rule cuts both ways.** A sentence the labeller cannot judge
  from the packet alone is labelled *unsupported*, which is the verifier's own
  standard; this will look harsh on sentences that happen to be true, and that
  is the intended reading of the number rather than a flaw in it.

## Entrypoint

Not yet written. It will be `code/run.py` in this folder, reading a labelled CSV
committed under `data/` and the stored `DailyBriefing.verification` records, and
writing `data/metrics.json` and `data/metrics.csv`.
