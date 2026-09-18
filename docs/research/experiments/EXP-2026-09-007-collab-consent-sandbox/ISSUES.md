# EXP-2026-09-007 — Issues

1. **The search week is a stand-in for the matcher.** Plan CN-05's matcher does
   not exist yet, so a "search" here returns up to five mutually visible open
   people drawn toward the popular by a Zipf weight. It exercises the cap and
   the visibility rule exactly as the matcher will call them, but its demand
   pattern is invented: 2,000 searches in one week among 240 people, 82 of
   them open, is deliberately heavy.
2. **The reference is independent of the code, not of the author.** H2's
   reference and the code under test were written by the same agent from the
   same design text; a shared misreading of design §7 would pass both.
3. **The world's users were modified in place.** Planting personal addresses
   and unverified accounts changed emails and verification on
   EXP-2026-09-005's sandbox people; later sandbox runs start from this state.
4. **The cap is not transactional.** `may_appear` then `record_appearance` can
   admit one extra seeker when two searches race; the simulation is serial,
   so this is untested here. CN-05 should take the check and the record in one
   transaction.
