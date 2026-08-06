# Negative-result template

A failed, abandoned, or hypothesis-refuting run gets the same folder as any
other experiment. Set `status: failed` (it broke) or `status: complete` with
`refutes_claims` populated (it ran fine and the answer was no), and never delete
the directory.

These entries are the highest-value thing in the record after the claims ledger:
they are what stops the same dead end being walked into in month nine, and they
populate the limitations section that reviewers check for honesty.

## RESULTS.md sections to fill differently

**1. Headline** — state the negative plainly. "RRF fusion did not beat BM25 on
this collection" is a finding. "Results were mixed" is not.

**4. Interpretation** — separate the three explanations and say which the
evidence supports:

- the *idea* is wrong;
- the *implementation* is wrong;
- the *measurement* is wrong (wrong task, wrong collection, wrong metric).

Most abandoned directions die because nobody separated these. If the evidence
cannot separate them, say so and record what would.

**5. Threats to validity** — for a negative result this is where the reviewer's
attention lands. Was the baseline tuned and the proposed method not? Was the
budget matched?

**7. Follow-ups** — the smallest experiment that would distinguish the
explanations above.

## ISSUES.md

For a crashed or aborted run, record impact on n, cause, resolution, and the
paper implication. See `templates/experiment/` and the ISSUES entry format:

```markdown
## YYYY-MM-DD — <what happened>
**Impact:** which cells lost runs, and what n becomes.
**Cause:** the actual cause, not the symptom.
**Resolution:** what was done, or "abandoned".
**Paper implication:** what must be stated because of this.
```
