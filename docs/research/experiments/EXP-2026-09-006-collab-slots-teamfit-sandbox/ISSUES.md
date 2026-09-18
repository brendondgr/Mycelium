# EXP-2026-09-006 — Issues

1. **Three arms, two amendments.** The protocol was amended twice after a
   failed bar and before the next arm ran (PROTOCOL.md, Amendments 1 and 2):
   arm A (`s1`) failed slot recall and precision, arm B (`s2`) failed the
   required-flag bar, arm C (`s3`) passed. Each failed arm is recorded with its
   numbers. A third amendment adds an exploratory coverage-threshold sweep.
2. **The generator did not always follow its plan.** Call c0003 says teams
   "MUST include" a Kalman filter the plan marked as welcome, and 97 of arm C's
   98 unplanted slots appear verbatim in the generated call text: the
   generator added requirements it was told not to. Both count against the
   extractor here, so precision and required-flag agreement are pessimistic.
3. **The model wrote what it later read**, as in EXP-2026-09-005 (its ISSUES.md
   3): these numbers bound behaviour on cooperative text.
4. **Problem matching is lexical.** A planted problem is matched by exact words
   or ≥ 0.5 word overlap, so a faithful paraphrase ("how complex academic
   literature is condensed" for "scientific text summarisation") is a miss;
   problem recall (0.73 in arm C) is a floor, not an estimate.
5. **Expected coverage is by exact name.** A person or lab holding a genuine
   synonym of a slot's method is expected *not* to cover it, so agreement on
   variant names mixes linker behaviour with the scorer's strictness.
6. **The world was not re-seeded between arms.** Each arm re-created the
   sandbox calls and their scores on top of EXP-2026-09-005's people; the
   sweep re-marked arm C's stored slots without re-reading them.
7. **Tokens were not counted**; the manifest records `null`.
